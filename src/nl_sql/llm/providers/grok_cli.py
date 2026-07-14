"""Grok Build CLI provider — subscription-metered frontier slot.

Drives the locally-installed `grok` CLI (Grok Build) in headless single-turn mode
and reads its JSON envelope. Like GraceKelly this is a *subscription* path, not an
API: there is no key and no per-token bill, but there IS a weekly quota that
belongs to the user, so an n=200 run is a deliberate spend, not a free probe.

Three things the 2026-07-14 probe established, all of which shape this module:
- **The catalogue lies.** `grok models` advertises `grok-4.20-0309-reasoning`;
  the backend answers `unknown model id` for it. The tier actually serves
  `grok-composer-2.5-fast`, which is what `modelUsage` reports. So the default
  here is the model that exists, and pinning another one is expected to fail.
- **The agent scaffolding is not removable.** Even with `--system-prompt-override`,
  every call carries ~13k tokens of harness (tool definitions, reminders) on top of
  the generation prompt. This is an agent CLI wearing an LLM costume; the SQL prompt
  still dominates the task, but the comparison against a bare API provider is not
  perfectly like-for-like, and the report should say so.
- **The prompt cannot go through argv.** The generation prompt runs ~40k characters,
  well past the Windows command-line limit, so it goes to a file and we pass
  `--prompt-file`.

The agent is stripped of tools (`--disallowed-tools`, `--no-memory`, `--no-plan`) and
pointed at a scratch cwd, so it cannot wander the repository.

**But it must not be stripped of turns.** `--max-turns 1` looks like the way to make
an agent behave as a text completion, and it is a trap: Grok spends its first turn
announcing what it is about to do ("Проверю, есть ли в workspace база…") and reaching
for a tool. Cutting it there returns that preamble as the answer — `stopReason:
Cancelled`, prose where SQL should be. The first n=200 run scored 47.0% with 31%
invalid SQL and measured this bug, not the model. With four turns it talks past the
preamble and emits a fenced SQL block (`stopReason: EndTurn`), which the pipeline's
extractor reads normally. `--json-schema` does not help: the model ignores it and the
CLI reports `structuredOutputError`.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)

# Every built-in that could touch the machine. A generator has no business
# reading files or searching the web, and a stray tool turn burns weekly quota.
_DISALLOWED_TOOLS = "bash,edit,read,write,glob,grep,webfetch,websearch,task,todowrite"


class GrokCliProvider:
    name: str = "grok_cli"

    def __init__(
        self,
        cli_path: str = "grok",
        model: str = "grok-composer-2.5-fast",
        timeout_seconds: float = 600.0,
        max_turns: int = 4,
        effort: str | None = None,
    ) -> None:
        self.model = model
        # Read by the cache wrapper: same model at a different effort is a
        # different experiment and must not replay the other one's answers.
        self.effort = effort
        self._cli_path = cli_path
        self._timeout = timeout_seconds
        self._max_turns = max_turns

    def _argv(self, prompt_file: Path, req: GenerateRequest) -> list[str]:
        argv = [
            self._cli_path,
            "--prompt-file",
            str(prompt_file),
            # Until 2026-07-14 this was missing, so `model` only ever labelled the
            # report while the CLI silently served its own default. Asking for a
            # model and not passing it is how you "measure" one and run another.
            "--model",
            self.model,
            "--output-format",
            "json",
            "--verbatim",
            "--max-turns",
            str(self._max_turns),
            "--disallowed-tools",
            _DISALLOWED_TOOLS,
            "--no-memory",
            "--no-plan",
            "--no-subagents",
            "--disable-web-search",
            "--permission-mode",
            "dontAsk",
        ]
        if self.effort:
            argv += ["--reasoning-effort", self.effort]
        if req.system:
            argv += ["--system-prompt-override", req.system]
        return argv

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="grok-gen-") as tmp:
            prompt_file = Path(tmp) / "prompt.txt"
            prompt_file.write_text(req.prompt, encoding="utf-8")
            try:
                proc = subprocess.run(
                    self._argv(prompt_file, req),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self._timeout,
                    cwd=tmp,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ProviderError(f"grok CLI not found at {self._cli_path!r}") from exc
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(
                    f"grok CLI timed out after {self._timeout}s for model={self.model}"
                ) from exc

        stdout = proc.stdout or ""
        try:
            # A failed run prints the JSON error envelope and then a plain-text
            # `Error: ...` line, so parse the first document rather than the file.
            payload, _ = json.JSONDecoder().raw_decode(stdout.lstrip())
        except ValueError as exc:
            tail = (proc.stderr or stdout).strip()[:300]
            raise ProviderError(
                f"grok CLI returned no JSON (rc={proc.returncode}): {tail}"
            ) from exc

        if payload.get("type") == "error":
            raise ProviderError(f"grok CLI error: {str(payload.get('message'))[:300]}")

        usage = payload.get("usage") or {}
        model_usage = payload.get("modelUsage") or {}
        # modelUsage names the model the tier actually routed to, which is the honest
        # label for a report — `--model` is a request, not a guarantee.
        served = next(iter(model_usage), self.model)

        return GenerateResponse(
            text=str(payload.get("text") or ""),
            model=served,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
