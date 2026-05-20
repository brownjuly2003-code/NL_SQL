"""OpenRouter provider — heterogeneous voting slot.

Endpoint: https://openrouter.ai/api/v1 (OpenAI-compatible). OpenRouter
multiplexes many model families (Anthropic / Google / Qwen / DeepSeek /
GLM / Llama) behind a single API; the `:free` model variants are
rate-limited but cost $0. Used here to give the self-consistency
ensemble a generator from a different family than codestral (Mistral),
which is the heterogeneity that plain config F was missing — see
`docs/v18_residue_patterns.md` § "Patch P4 — CSC merge-revision".

Auth: API key from `OPENROUTER_API_KEY` (or `NL_SQL_OPENROUTER_API_KEY`).
"""

from __future__ import annotations

from openai import OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)


class OpenRouterProvider:
    name: str = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek/deepseek-v4-flash:free",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        if not api_key:
            raise ProviderError("OpenRouterProvider requires non-empty api_key")
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        return chat_complete(self._client, self.model, req)
