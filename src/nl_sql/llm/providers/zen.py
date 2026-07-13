"""OpenCode Zen provider — free-tier generator slot.

Endpoint: https://opencode.ai/zen/v1 (OpenAI-compatible). Zen fronts many model
families behind one key; the catalogue splits into paid ids and a `*-free` set.
The workspace behind our keys has **no payment method attached**, so paid ids
answer `CreditsError` and only the free set is reachable — the spend gate is
enforced by the vendor, not by a flag here.

Why it exists: the generator was the last untested axis (`docs/BACKLOG.md` —
"смена генератора"), and every earlier candidate was gated behind a key or a
browser. Zen unblocks it for $0.

Two operational notes, both learned on the 2026-07-14 probe:
- **Every free Zen model is a reasoning model**, and reasoning tokens are billed
  against `max_tokens`. The caller's 2048 is a budget for *answer* text, so on
  the real generation prompt the model thinks past it and returns an empty
  `content` — 4/5 on the first n=5 smoke, each one stopping at exactly 2048
  output tokens (the same failure that killed `z-ai/glm-4.5-air:free` on
  OpenRouter — see settings). Hence `min_max_tokens`: the provider floors the
  budget, rather than the shared default rising, because the LLM cache keys on
  `max_tokens` and raising it globally would invalidate every cached codestral
  response behind the product number.
- **Free tiers meter per key.** We hold several, so `chat_complete` rotates
  through them on 429 before it sleeps.

Auth: `OPENCODE_API_KEY`, comma-separated for the rotation ring.
"""

from __future__ import annotations

from openai import OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)


class ZenProvider:
    name: str = "zen"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash-free",
        base_url: str = "https://opencode.ai/zen/v1",
        timeout_seconds: float = 180.0,
        min_max_tokens: int = 16384,
    ) -> None:
        keys = [part.strip() for part in api_key.split(",") if part.strip()]
        if not keys:
            raise ProviderError("ZenProvider requires non-empty api_key")
        self.model = model
        self._min_max_tokens = min_max_tokens
        clients = [OpenAI(api_key=key, base_url=base_url, timeout=timeout_seconds) for key in keys]
        self._client = clients[0]
        self._fallback_clients = tuple(clients[1:])

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        if req.max_tokens < self._min_max_tokens:
            req = req.model_copy(update={"max_tokens": self._min_max_tokens})
        return chat_complete(
            self._client,
            self.model,
            req,
            fallback_clients=self._fallback_clients,
        )
