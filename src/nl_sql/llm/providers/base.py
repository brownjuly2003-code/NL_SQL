"""Provider Protocols and shared request/response models.

The codebase has two orthogonal capabilities:
- LLMProvider: chat-completion / SQL generation. All three slots implement it.
- EmbeddingProvider: vector embeddings. Only Mistral implements it for now —
  schema-RAG and few-shot retrieval are pinned to mistral-embed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str
    system: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2048
    json_mode: bool = False
    """When True and the provider supports it, ask the API to constrain
    output to a JSON object (OpenAI/Groq response_format=json_object).
    Mistral codestral's chat endpoint does NOT support response_format
    server-side, so we just send the request — the caller still owns
    parsing. Set ON for Groq/GitHub-Models to dramatically reduce the
    "model wrapped JSON in prose" failure rate that costs us 60% of
    valid pred_sql in the n=50 Groq smoke (2026-05-12)."""


class GenerateResponse(BaseModel):
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1)


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str


class ProviderError(RuntimeError):
    """Raised when a provider call fails for any non-network reason we surface."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, req: GenerateRequest) -> GenerateResponse: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    embed_model: str

    def embed(self, req: EmbedRequest) -> EmbedResponse: ...
