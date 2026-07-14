"""Claude Code CLI provider — subscription-metered frontier slot.

Drives the locally-installed `claude` CLI in print mode (`-p`) and reads its JSON
envelope. Like GraceKelly and grok_cli this rides a subscription rather than an
API key: no bill, but the run draws on the user's plan limits. The envelope reports
`total_cost_usd`, so the draw is measurable rather than guessed — a BIRD generation
prompt (~6.7k fresh tokens, ~155 out) costs about $0.03 of plan-equivalent, so an
n=200 run is roughly $6.

Why this exists: Sonnet's only previous number on this benchmark (58.5%, closed as
"worse than codestral") was measured through the browser bridge **on the compact
prompt**, not the product prompt. That is a confound, not a result. This slot lets a
frontier model run the same config E as every other generator, so the comparison is
finally like-for-like.

Two details that matter:
- **`--system-prompt` replaces the harness prompt** (`--append-system-prompt` would
  add to it). Replacing it strips the agent persona, so the model answers as a
  completion rather than as an agent. grok_cli cannot do this — there the scaffolding
  is unavoidable.
- **One turn is still not enough.** Even toolless and de-personified, the model
  sometimes reaches for a tool, gets denied, and spends the turn on it — the CLI then
  returns `error_max_turns` and the question scores as a pipeline exception. Same trap
  as grok_cli, different CLI: *disallowing tools stops an agent from touching the
  machine, it does not stop it from behaving like an agent.* Give it turns to spare.
- **The prompt goes over stdin**, not argv: it runs ~40k characters, past the Windows
  command-line limit.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time

from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)

# A generator has no business touching the machine, and a stray tool turn costs
# plan quota. Names are the Claude Code tool names, not the grok ones.
_DISALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite,NotebookEdit"

# A dropped process spawn is not an answer. See the retry loop in generate().
_SPAWN_ATTEMPTS = 3
_SPAWN_BACKOFF_SECONDS = 2.0


class ClaudeCliProvider:
    name: str = "claude_cli"

    def __init__(
        self,
        cli_path: str = "claude",
        model: str = "claude-sonnet-5",
        timeout_seconds: float = 600.0,
        max_turns: int = 4,
        effort: str | None = None,
    ) -> None:
        self.model = model
        # Read by the cache wrapper: two runs of the same model at different
        # efforts are different experiments and must not share a cache entry.
        self.effort = effort
        self._cli_path = cli_path
        self._timeout = timeout_seconds
        self._max_turns = max_turns
        self._cwd: str | None = None

    def _argv(self, req: GenerateRequest) -> list[str]:
        argv = [
            self._cli_path,
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--max-turns",
            str(self._max_turns),
            "--disallowedTools",
            _DISALLOWED_TOOLS,
        ]
        if self.effort:
            # The spawned CLI does not inherit the caller's session effort, so an
            # effort ablation only happens if it is passed explicitly here.
            argv += ["--effort", self.effort]
        if req.system:
            # Replace, not append: this is what strips the agent persona.
            argv += ["--system-prompt", req.system]
        return argv

    def _workdir(self) -> str:
        """One scratch directory for the whole run, created once.

        It used to be a fresh `TemporaryDirectory` per call, and that was the bug behind
        the "claude CLI not found" misses. The CLI outlives `subprocess.run` — cmd.exe
        hands off to node.exe, which keeps the cwd handle open a moment longer — so the
        context manager's cleanup hit `WinError 32: being used by another process`, and
        the NEXT call then tried to spawn into a directory Windows was still tearing
        down and got `WinError 2: cannot find the file`. Python raises that as
        FileNotFoundError, and this module blamed the CLI path in the message, which is
        why the failure read as "the binary is missing" when the binary was fine and the
        cwd was not. Retrying could not help: each attempt rebuilt the same race.

        A directory that is created once and never deleted mid-run has no race to lose.
        It stays a scratch dir, so the model still cannot see the repository (no
        CLAUDE.md, no source) — which is the only reason cwd is redirected at all.
        """
        if self._cwd is None:
            self._cwd = tempfile.mkdtemp(prefix="claude-gen-")
        return self._cwd

    def _run_once(self, req: GenerateRequest) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._argv(req),
            input=req.prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self._timeout,
            cwd=self._workdir(),
            check=False,
        )

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        started = time.perf_counter()
        proc: subprocess.CompletedProcess[str] | None = None
        last_error = ""
        # A spawn can still fail transiently (the machine is busy, the shim is slow), so
        # the retry stays — but it is no longer papering over a race we caused ourselves.
        for attempt in range(_SPAWN_ATTEMPTS):
            try:
                proc = self._run_once(req)
            except FileNotFoundError as exc:
                # Could be the CLI, could be the cwd. Say both rather than guess — the
                # old message asserted the first and sent us hunting the wrong bug.
                last_error = (
                    f"spawn failed (cli={self._cli_path!r}, cwd={self._cwd!r}): {exc}"
                )
                proc = None
            except OSError as exc:
                last_error = f"claude CLI failed to spawn: {exc}"
                proc = None
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(
                    f"claude CLI timed out after {self._timeout}s for model={self.model}"
                ) from exc
            if proc is not None and proc.stdout and proc.stdout.lstrip().startswith("{"):
                break
            if proc is not None:
                last_error = (proc.stderr or proc.stdout or "").strip()[:200]
                proc = None
            if attempt < _SPAWN_ATTEMPTS - 1:
                time.sleep(_SPAWN_BACKOFF_SECONDS * (attempt + 1))

        if proc is None:
            raise ProviderError(
                f"claude CLI produced no usable output after {_SPAWN_ATTEMPTS} attempts: "
                f"{last_error}"
            )

        stdout = proc.stdout or ""
        try:
            payload = json.loads(stdout)
        except ValueError as exc:
            tail = (proc.stderr or stdout).strip()[:300]
            raise ProviderError(
                f"claude CLI returned no JSON (rc={proc.returncode}): {tail}"
            ) from exc

        if payload.get("is_error"):
            reason = payload.get("result") or payload.get("subtype") or "unknown"
            raise ProviderError(f"claude CLI error: {str(reason)[:300]}")

        usage = payload.get("usage") or {}
        model_usage = payload.get("modelUsage") or {}
        served = next(iter(model_usage), self.model)
        # Cached prefix reads are input the model saw; counting only `input_tokens`
        # would report ~2 tokens per call and make the run look free.
        input_tokens = (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
        )

        return GenerateResponse(
            text=str(payload.get("result") or ""),
            model=served,
            input_tokens=input_tokens,
            output_tokens=int(usage.get("output_tokens") or 0),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
