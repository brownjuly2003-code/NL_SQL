"""Perplexity browser provider — routes generation through a local GraceKelly
instance which drives the Perplexity Pro web UI via Playwright.

Why this exists:
- Project budget is $0. Direct Anthropic / OpenAI APIs are paid.
- A live Perplexity Pro subscription exposes frontier models (Claude Sonnet
  4.6 + reasoning, GPT-5.4, Gemini Pro, Kimi K2.5) at no incremental cost
  per request.
- GraceKelly (D:\\GraceKelly) is an existing local FastAPI service that
  already handles Playwright session management, model selection, the
  "thinking" toggle, and prompt submit/parse against the Perplexity UI.

We just hit `POST /api/v1/pipeline` with `{prompt, model}` and read the
plain-text `answer` back. Latency is ~20-40s per call (browser path), so
this provider is intended for evaluation runs and one-off probes, not for
the interactive Streamlit chat surface.
"""

from __future__ import annotations

import json
import re
import time
from urllib import error as urlerror
from urllib import request as urlrequest

from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)

# ANSI escape sequences (terminal colour / formatting codes). Perplexity's
# web UI sometimes renders model output through a Markdown pipeline that
# leaves these codes in the copy-back text — e.g. `[4m`/`[0m` (underline
# on/off) around tool argument quotes. They break downstream JSON parsing.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[[0-9;]+m")

# Sonnet routed through Perplexity sometimes returns its answer as the
# rendered JSON of the `generate_sql` output contract — a literal
# `{"sql": "...", "rationale": "..."}` string instead of a bare SQL
# statement. The downstream `_strip_to_sql` parser doesn't recognise this
# shape and falls back to grabbing everything after the first `SELECT`,
# trailing `","rationale":...` and all — which then 400s in sqlglot as
# invalid SQL. Pre-unwrap the JSON here so the parser sees clean SQL.
_SQL_JSON_HINT = re.compile(r'^\s*\{.*"sql"\s*:', re.DOTALL)


def _unwrap_sql_json(text: str) -> str:
    """If `text` is the JSON output-contract envelope, return just the SQL."""
    if not _SQL_JSON_HINT.match(text):
        return text
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Tolerate trailing prose after the JSON object by snipping at the
        # final balanced brace and retrying.
        last = text.rfind("}")
        if last == -1:
            return text
        try:
            obj = json.loads(text[: last + 1])
        except json.JSONDecodeError:
            return text
    sql = obj.get("sql") if isinstance(obj, dict) else None
    if isinstance(sql, str) and sql.strip():
        return sql.strip()
    return text


class PerplexityProvider:
    """LLMProvider that proxies generate() calls to a local GraceKelly server.

    GraceKelly drives the Perplexity web UI via Playwright with a logged-in
    Chrome profile, so the model behind the scenes is whichever the caller
    picked in Perplexity's model menu (default `claude-sonnet-4-6` here,
    which corresponds to Claude Sonnet 4.6 with reasoning enabled).
    """

    name: str = "perplexity"

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        base_url: str = "http://127.0.0.1:8011",
        timeout_seconds: float = 180.0,
    ) -> None:
        if not model.strip():
            raise ProviderError("PerplexityProvider requires non-empty model")
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        prompt = req.prompt
        if req.system:
            prompt = f"{req.system}\n\n{prompt}"
        payload = json.dumps({
            "prompt": prompt,
            "model": self.model,
            "reliability_level": "quick",
            "multi_model": False,
            "dry_run": False,
        }).encode("utf-8")

        http_request = urlrequest.Request(
            f"{self._base_url}/api/v1/pipeline",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urlrequest.urlopen(http_request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raise ProviderError(
                f"GraceKelly /api/v1/pipeline returned {exc.code}: "
                f"{exc.read().decode('utf-8', errors='replace')[:400]}"
            ) from exc
        except (urlerror.URLError, TimeoutError) as exc:
            raise ProviderError(
                f"GraceKelly unreachable at {self._base_url}: {exc!r}. "
                "Start it with `python -m uvicorn gracekelly.main:create_app "
                "--factory --host 127.0.0.1 --port 8011` "
                "and set GRACEKELLY_EXECUTION_PROFILE=hybrid."
            ) from exc

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        parsed = json.loads(body)
        answer = _ANSI_RE.sub("", str(parsed.get("answer") or ""))
        answer = _unwrap_sql_json(answer)
        # Perplexity browser path does not surface token counts. Use word
        # count as a coarse proxy so the eval reports show something
        # plausible without misrepresenting actual billing units.
        approx_in = max(1, len(prompt.split()))
        approx_out = max(1, len(answer.split()))
        return GenerateResponse(
            text=answer,
            model=str(parsed.get("model_id") or self.model),
            input_tokens=approx_in,
            output_tokens=approx_out,
            latency_ms=elapsed_ms,
        )
