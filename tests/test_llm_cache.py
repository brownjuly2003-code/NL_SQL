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
    LLMProvider,
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


class _EmptyThenAnswer:
    """Provider double that fails empty once, then answers. Models the reasoning-
    model truncation seen on Zen: content='' when reasoning eats max_tokens."""

    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.calls += 1
        text = "" if self.calls == 1 else "SELECT 1;"
        return GenerateResponse(text=text, model=self.model)


def test_caching_llm_does_not_persist_empty_completions(cache_dir: Path) -> None:
    """An empty completion is a failure, not an answer.

    Caching one poisons the key forever: every later run replays the empty string
    and the model looks broken. Cost of the rule is one wasted call; cost of
    breaking it is a silently dead provider (2026-07-14: a reasoning-budget bug
    cached 10 empty responses and the re-run reproduced them exactly).
    """
    inner = _EmptyThenAnswer()
    cached = CachingLLMProvider(inner, cache_dir=cache_dir)
    req = GenerateRequest(prompt="hello")

    first = cached.generate(req)
    second = cached.generate(req)

    assert first.text == ""
    assert second.text == "SELECT 1;", "empty response must not have been cached"
    assert inner.calls == 2, "the empty completion must not short-circuit the retry"
    cached.close()


def test_caching_llm_key_distinguishes_inputs(cache_dir: Path) -> None:
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner, cache_dir=cache_dir)

    cached.generate(GenerateRequest(prompt="A", temperature=0.0, max_tokens=64))
    cached.generate(GenerateRequest(prompt="B", temperature=0.0, max_tokens=64))
    cached.generate(GenerateRequest(prompt="A", temperature=0.7, max_tokens=64))
    cached.generate(GenerateRequest(prompt="A", temperature=0.0, max_tokens=128))
    cached.generate(GenerateRequest(prompt="A", system="sys-1", temperature=0.0, max_tokens=64))

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


class _EffortLLM(_CountingLLM):
    """A provider that carries a reasoning-effort dial, like the two agent CLIs."""

    def __init__(self, effort: str | None) -> None:
        super().__init__()
        self.effort = effort


def _generate_once(inner: LLMProvider, cache_dir: Path) -> None:
    """One cached call, cache closed afterwards — an unclosed diskcache leaves a live
    sqlite handle and Windows raises it as an unraisable ResourceWarning in teardown."""
    cached = CachingLLMProvider(inner, cache_dir=cache_dir)
    cached.generate(GenerateRequest(prompt="write SQL"))
    cached.close()


def test_caching_llm_key_separates_efforts(cache_dir: Path) -> None:
    """Same model at max effort is a different generator than at its default. If the
    two shared a key, an effort ablation would replay the earlier run's answers and
    'reproduce' exactly the number it was meant to test."""
    default = _EffortLLM(effort=None)
    _generate_once(default, cache_dir)
    assert len(default.calls) == 1

    maxed = _EffortLLM(effort="max")
    _generate_once(maxed, cache_dir)
    assert len(maxed.calls) == 1, "max effort must not be served the default's cached answer"

    again = _EffortLLM(effort="max")
    _generate_once(again, cache_dir)
    assert again.calls == [], "a second max-effort call should hit the cache"


def test_caching_llm_key_unchanged_for_providers_without_effort(cache_dir: Path) -> None:
    """Effort joins the key only when set, so every entry cached before efforts
    existed (all of codestral, all of Sonnet) keeps its key instead of being orphaned."""
    plain = _CountingLLM()  # no `effort` attribute at all
    _generate_once(plain, cache_dir)

    explicit_none = _EffortLLM(effort=None)  # has the attribute, set to None
    _generate_once(explicit_none, cache_dir)

    assert explicit_none.calls == [], "effort=None must land on the same key as no effort"
