"""Helallao Perplexity provider — direct reverse-engineered Perplexity Pro client.

Bypasses GraceKelly's broken browser adapter. Uses the user's existing logged-in
Perplexity Pro session via `__Secure-next-auth.session-token` cookie.

Why this exists:
- GraceKelly's Playwright adapter is broken by Perplexity UI drift (2026-05-18).
- helallao/perplexity-ai uses Perplexity's reverse-engineered HTTPS endpoints
  directly with curl-cffi (Chrome impersonation) — no browser, no Playwright.
- Pro models exposed: sonar, gpt-5.2, claude-4.5-sonnet, grok-4.1
  (+ -thinking / -reasoning variants).

Latency: 4-8s per call (HTTPS path), faster than browser bridge.
Budget: $0 via user's existing Perplexity Pro subscription.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)
from nl_sql.llm.providers.perplexity import _ANSI_RE, _unwrap_sql_json

DEFAULT_COOKIE_PATH = Path("D:/NL_SQL/.tmp/pplx_cookies.json")

_REASONING_MODELS = frozenset(
    {
        "grok-4.1-reasoning",
        "gpt-5.2-thinking",
        "claude-4.5-sonnet-thinking",
        "gemini-3.0-pro",
        "kimi-k2-thinking",
    }
)


class HelallaoPerplexityProvider:
    """LLMProvider that calls Perplexity Pro via helallao/perplexity-ai library.

    The model param routes to Perplexity's Pro model picker. Valid values:
    - pro mode: sonar / gpt-5.2 / claude-4.5-sonnet / grok-4.1
    - reasoning mode: grok-4.1-reasoning / gpt-5.2-thinking /
      claude-4.5-sonnet-thinking / gemini-3.0-pro / kimi-k2-thinking
    Mode auto-detected from model name; explicit `mode` arg wins.
    """

    name: str = "helallao-perplexity"

    def __init__(
        self,
        *,
        model: str = "grok-4.1",
        cookies_path: Path | str = DEFAULT_COOKIE_PATH,
        timeout_seconds: float = 180.0,
        mode: str | None = None,
    ) -> None:
        if not model.strip():
            raise ProviderError("HelallaoPerplexityProvider requires non-empty model")
        try:
            import perplexity as _pplx  # type: ignore[import-untyped]
        except ImportError as e:
            raise ProviderError(
                "helallao perplexity-ai not installed. Run: "
                "uv pip install 'git+https://github.com/helallao/perplexity-ai'"
            ) from e
        cookies_path = Path(cookies_path)
        if not cookies_path.exists():
            raise ProviderError(
                f"Perplexity cookies file not found at {cookies_path}. "
                "Extract via .tmp/extract_pplx_cookies.py (Playwright + chrome-profile)."
            )
        cookies_list = json.loads(cookies_path.read_text(encoding="utf-8"))
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}
        self._client = _pplx.Client(cookies_dict)
        self.model = model
        self.mode = mode if mode else ("reasoning" if model in _REASONING_MODELS else "pro")
        self._timeout = timeout_seconds

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        prompt = req.prompt
        if req.system:
            prompt = f"{req.system}\n\n{prompt}"
        t0 = time.perf_counter()
        try:
            resp = self._client.search(prompt, mode=self.mode, model=self.model)
        except Exception as exc:
            raise ProviderError(
                f"helallao perplexity.search failed for model={self.model}: {exc!r}"
            ) from exc
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if not isinstance(resp, dict):
            raise ProviderError(f"helallao returned non-dict: {type(resp).__name__}")
        answer_raw = str(resp.get("answer") or resp.get("text") or "")
        answer = _ANSI_RE.sub("", answer_raw)
        answer = _unwrap_sql_json(answer)
        approx_in = max(1, len(prompt.split()))
        approx_out = max(1, len(answer.split()))
        return GenerateResponse(
            text=answer,
            model=str(resp.get("display_model") or self.model),
            input_tokens=approx_in,
            output_tokens=approx_out,
            latency_ms=elapsed_ms,
        )


def _smoke() -> int:
    """`uv run python -m nl_sql.llm.providers.helallao_perplexity` smoke."""
    from nl_sql.llm.providers.base import GenerateRequest

    provider = HelallaoPerplexityProvider(model="grok-4.1")
    resp = provider.generate(
        GenerateRequest(prompt="Return ONLY: SELECT 1 as ok;", temperature=0.0)
    )
    print(f"model={resp.model} latency={resp.latency_ms:.0f}ms")
    print(f"text: {resp.text[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_smoke())
