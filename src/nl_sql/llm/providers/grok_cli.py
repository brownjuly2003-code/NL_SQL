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

The agent is stripped down to a single toolless turn (`--max-turns 1`,
`--disallowed-tools`, `--no-memory`, `--no-plan`) and pointed at a scratch cwd, so
it behaves as a text completion rather than wandering the repository.
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
    ) -> None:
        self.model = model
        self._cli_path = cli_path
        self._timeout = timeout_seconds

    def _argv(self, prompt_file: Path, req: GenerateRequest) -> list[str]:
        argv = [
            self._cli_path,
            "--prompt-file",
            str(prompt_file),
            "--output-format",
            "json",
            "--verbatim",
            "--max-turns",
            "1",
            "--disallowed-tools",
            _DISALLOWED_TOOLS,
            "--no-memory",
            "--no-plan",
            "--no-subagents",
            "--disable-web-search",
            "--permission-mode",
            "dontAsk",
        ]
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
