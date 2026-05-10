"""Mistral La Plateforme provider.

Implements both LLMProvider (codestral-latest for SQL, mistral-large-latest for NL)
and EmbeddingProvider (mistral-embed). All three models go through the OpenAI-
compatible /v1 endpoint at api.mistral.ai.
"""

from __future__ import annotations

from openai import APIError, OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)


class MistralProvider:
    name: str = "mistral"

    def __init__(
        self,
        api_key: str,
        gen_model: str = "codestral-latest",
        embed_model: str = "mistral-embed",
        base_url: str = "https://api.mistral.ai/v1",
    ) -> None:
        if not api_key:
            raise ProviderError("MistralProvider requires non-empty api_key")
        self.model = gen_model
        self.embed_model = embed_model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        return chat_complete(self._client, self.model, req)

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        try:
            response = self._client.embeddings.create(
                model=self.embed_model,
                input=req.texts,
            )
        except APIError as exc:
            raise ProviderError(
                f"embeddings.create failed for model={self.embed_model}: {exc}"
            ) from exc

        vectors = [item.embedding for item in response.data]
        return EmbedResponse(vectors=vectors, model=response.model or self.embed_model)
