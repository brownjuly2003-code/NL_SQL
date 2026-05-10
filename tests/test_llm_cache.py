"""Tests for nl_sql.llm.cache: disk-backed wrappers around providers."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl_sql.llm.cache import (
    CachingEmbeddingProvider,
    CachingLLMProvider,
    wrap_with_cache,
)
from nl_sql.llm.providers.base import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
)


class _CountingLLM:
    """Minimal LLMProvider double that records every generate() call."""

    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[GenerateRequest] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.calls.append(req)
        return GenerateResponse(
            text=f"echo:{req.prompt}",
            model=self.model,
            input_tokens=len(req.prompt),
            output_tokens=5,
            latency_ms=12.5,
        )


class _CountingEmbedder:
    name = "fake"
    embed_model = "fake-embed"

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        self.batches.append(list(req.texts))
        # Pseudo-vector: deterministic per-text so we can assert content.
        vectors = [[float(len(t)), float(sum(ord(c) for c in t))] for t in req.texts]
        return EmbedResponse(vectors=vectors, model=self.embed_model)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "llm-cache"


def test_caching_llm_first_call_misses_then_hits(cache_dir: Path) -> None:
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner, cache_dir=cache_dir)

    req = GenerateRequest(prompt="hello", temperature=0.0, max_tokens=64)
    a = cached.generate(req)
    b = cached.generate(req)

    assert a.text == "echo:hello"
    assert b.text == "echo:hello"
    assert len(inner.calls) == 1, "second call must come from cache"
    assert b.latency_ms == 0.0, "cache hits report 0 latency to keep eval signal honest"
    assert b.input_tokens == a.input_tokens  # tokens preserved
    cached.close()


def test_caching_llm_key_distinguishes_inputs(cache_dir: Path) -> None:
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner, cache_dir=cache_dir)

    cached.generate(GenerateRequest(prompt="A", temperature=0.0, max_tokens=64))
    cached.generate(GenerateRequest(prompt="B", temperature=0.0, max_tokens=64))
    cached.generate(GenerateRequest(prompt="A", temperature=0.7, max_tokens=64))
    cached.generate(GenerateRequest(prompt="A", temperature=0.0, max_tokens=128))
    cached.generate(
        GenerateRequest(prompt="A", system="sys-1", temperature=0.0, max_tokens=64)
    )

    assert len(inner.calls) == 5
    cached.close()


def test_caching_llm_persists_across_instances(cache_dir: Path) -> None:
    inner1 = _CountingLLM()
    cached1 = CachingLLMProvider(inner1, cache_dir=cache_dir)
    cached1.generate(GenerateRequest(prompt="persist-me"))
    cached1.close()

    inner2 = _CountingLLM()
    cached2 = CachingLLMProvider(inner2, cache_dir=cache_dir)
    resp = cached2.generate(GenerateRequest(prompt="persist-me"))
    assert resp.text == "echo:persist-me"
    assert inner2.calls == [], "cache must survive between Cache instances"
    cached2.close()


def test_caching_llm_preserves_provider_identity(cache_dir: Path) -> None:
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner, cache_dir=cache_dir)
    assert cached.name == "fake"
    assert cached.model == "fake-model"
    cached.close()


def test_wrap_with_cache_helper(cache_dir: Path) -> None:
    inner = _CountingLLM()
    cached = wrap_with_cache(inner, cache_dir=cache_dir)
    assert isinstance(cached, CachingLLMProvider)
    cached.generate(GenerateRequest(prompt="x"))
    cached.generate(GenerateRequest(prompt="x"))
    assert len(inner.calls) == 1
    cached.close()


def test_caching_embedder_per_text_partial_hit(cache_dir: Path) -> None:
    inner = _CountingEmbedder()
    cached = CachingEmbeddingProvider(inner, cache_dir=cache_dir)

    first = cached.embed(EmbedRequest(texts=["alpha", "beta"]))
    assert inner.batches == [["alpha", "beta"]]
    assert len(first.vectors) == 2

    # Second call: "alpha" is cached, "gamma" is new → only "gamma" is forwarded.
    second = cached.embed(EmbedRequest(texts=["alpha", "gamma"]))
    assert inner.batches == [["alpha", "beta"], ["gamma"]]
    assert len(second.vectors) == 2

    # Vectors must line up with the *requested* order, not the upstream order.
    assert second.vectors[0] == first.vectors[0]
    cached.close()


def test_caching_embedder_full_hit_skips_inner(cache_dir: Path) -> None:
    inner = _CountingEmbedder()
    cached = CachingEmbeddingProvider(inner, cache_dir=cache_dir)

    cached.embed(EmbedRequest(texts=["one", "two", "three"]))
    inner.batches.clear()

    again = cached.embed(EmbedRequest(texts=["three", "one", "two"]))
    assert inner.batches == [], "all three texts already cached"
    assert len(again.vectors) == 3
    cached.close()


def test_caching_embedder_persists_across_instances(cache_dir: Path) -> None:
    inner1 = _CountingEmbedder()
    cached1 = CachingEmbeddingProvider(inner1, cache_dir=cache_dir)
    cached1.embed(EmbedRequest(texts=["persist"]))
    cached1.close()

    inner2 = _CountingEmbedder()
    cached2 = CachingEmbeddingProvider(inner2, cache_dir=cache_dir)
    cached2.embed(EmbedRequest(texts=["persist"]))
    assert inner2.batches == []
    cached2.close()
