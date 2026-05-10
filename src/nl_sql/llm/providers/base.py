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
