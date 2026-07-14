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


class ClaudeCliProvider:
    name: str = "claude_cli"

    def __init__(
        self,
        cli_path: str = "claude",
        model: str = "claude-sonnet-5",
        timeout_seconds: float = 600.0,
        max_turns: int = 4,
    ) -> None:
        self.model = model
        self._cli_path = cli_path
        self._timeout = timeout_seconds
        self._max_turns = max_turns

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
        if req.system:
            # Replace, not append: this is what strips the agent persona.
            argv += ["--system-prompt", req.system]
        return argv

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="claude-gen-") as tmp:
            try:
                proc = subprocess.run(
                    self._argv(req),
                    input=req.prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self._timeout,
                    cwd=tmp,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ProviderError(f"claude CLI not found at {self._cli_path!r}") from exc
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(
                    f"claude CLI timed out after {self._timeout}s for model={self.model}"
                ) from exc

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
