"""Groq provider — frontier slot in $0-budget bakeoff (default).

Endpoint: https://api.groq.com/openai/v1 (OpenAI-compatible).
Free tier: very generous; serves best open models (Llama 3.3 70B, Mixtral)
on Groq's own LPU silicon — order-of-magnitude faster inference than GPU
clouds, which gives us realistic latency numbers in the bakeoff.

Default model: llama-3.3-70b-versatile. Picked over GPT-4o-mini-via-GitHub
because GitHub Models requires a fine-grained PAT with models:read scope
that not every account is provisioned with; Groq runs on a plain API key.
"""

from __future__ import annotations

from openai import OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)


class GroqProvider:
    name: str = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        if not api_key:
            raise ProviderError("GroqProvider requires non-empty api_key")
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        return chat_complete(self._client, self.model, req)
