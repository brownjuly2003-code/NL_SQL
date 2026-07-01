"""GraceKelly orchestrate provider — routes generation through a local
GraceKelly instance that drives a frontier model via its browser adapter.

This is the AgentFlow-branch model slot (see AgentFlow ADR 0008): AgentFlow
adopts this engine but runs NL->SQL on **Claude Sonnet 5 via GraceKelly**, not
Mistral. The portfolio NL_SQL default provider stays `mistral`; this provider is
selected explicitly (`build_provider("gracekelly")`).

Difference from `PerplexityProvider`: that one predates the V2 API and posts to
`/api/v1/pipeline` reading `answer`. This provider posts to `/api/v1/orchestrate`
reading `output_text`, which is the contract AgentFlow's serving layer already
standardised on (`serving/semantic_layer/nl_engine._llm_translate`). GraceKelly
owns model selection/execution — this provider never talks to a model API
directly. The default model `claude-sonnet-5` resolves through GraceKelly's live
catalog to "Claude Sonnet 5.0".

Latency is ~20-40s per call (browser path), so this provider is for evaluation
runs and one-off probes, not an interactive chat surface.
"""

from __future__ import annotations

import json
import time
from urllib import error as urlerror
from urllib import request as urlrequest

from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)

# Reuse the hardened Perplexity/GraceKelly output parsing: strip terminal ANSI
# codes the Markdown pipeline can leave behind, and unwrap the
# `{"sql": "...", "rationale": "..."}` envelope Sonnet sometimes emits instead
# of a bare statement. Same browser backend => same output quirks.
from nl_sql.llm.providers.perplexity import _ANSI_RE, _unwrap_sql_json


class GraceKellyProvider:
    """LLMProvider that proxies generate() to a local GraceKelly orchestrate API."""

    name: str = "gracekelly"

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-5",
        base_url: str = "http://127.0.0.1:8011",
        timeout_seconds: float = 180.0,
    ) -> None:
        if not model.strip():
            raise ProviderError("GraceKellyProvider requires non-empty model")
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        prompt = req.prompt
        if req.system:
            prompt = f"{req.system}\n\n{prompt}"
        payload = json.dumps({"prompt": prompt, "model": self.model}).encode("utf-8")

        http_request = urlrequest.Request(
            f"{self._base_url}/api/v1/orchestrate",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urlrequest.urlopen(http_request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raise ProviderError(
                f"GraceKelly /api/v1/orchestrate returned {exc.code}: "
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

        failure = parsed.get("failure_message") or parsed.get("failure_code")
        if failure and not parsed.get("output_text"):
            raise ProviderError(f"GraceKelly orchestrate failed: {failure}")

        answer = _ANSI_RE.sub("", str(parsed.get("output_text") or ""))
        answer = _unwrap_sql_json(answer)

        model_field = parsed.get("model")
        model_id = model_field.get("id") if isinstance(model_field, dict) else model_field
        # Browser path does not surface token counts; use a word-count proxy so
        # eval reports show something plausible without faking billing units.
        approx_in = max(1, len(prompt.split()))
        approx_out = max(1, len(answer.split()))
        return GenerateResponse(
            text=answer,
            model=str(model_id or self.model),
            input_tokens=approx_in,
            output_tokens=approx_out,
            latency_ms=elapsed_ms,
        )
