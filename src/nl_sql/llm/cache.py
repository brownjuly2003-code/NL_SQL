"""Disk-backed cache wrappers for LLMProvider / EmbeddingProvider.

Per `docs/02_architecture_v2.md §6.5`: each unique (provider, model,
prompt) goes to the upstream API exactly once. Repeat calls hit a local
`diskcache.Cache` and return in microseconds with zero quota burn.

This buys two things that matter for portfolio-grade ablations:

1.  **Determinism.** Mistral codestral at temperature=0 is *near*
    deterministic but not exactly so — config E showed +4pp over C at
    n=50 with literally identical execution paths and repair fired
    0/50. With cache, the second run reads the same response bytes.
2.  **Free re-runs.** Bumping `schema_top_k` or `fk_hops` and rerunning
    config C only pays the API for the prompts that actually changed.

Cache key for generate:
    sha256(provider.name | provider.model | system | prompt | temperature | max_tokens)

Cache key for embed (per text, not per batch — so reordering inputs hits
the same entries):
    sha256(provider.name | provider.embed_model | text)

Cached values are pydantic-serialised dicts; `latency_ms` on a hit is
reset to 0.0 so eval reports don't accidentally average cache hits with
live API latency.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import diskcache

from nl_sql.llm.providers.base import (
    EmbeddingProvider,
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
)


def _hash_key(parts: list[Any]) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _open_cache(root: Path | str, *, size_limit_gb: int) -> diskcache.Cache:
    Path(root).mkdir(parents=True, exist_ok=True)
    return diskcache.Cache(directory=str(root), size_limit=size_limit_gb * 1024**3)


class CachingLLMProvider:
    """Wrap an `LLMProvider` so repeat `generate()` calls are served from disk.

    The wrapper preserves `name` and `model` so downstream code that reads
    `getattr(provider, "model", "?")` (e.g. eval reports) keeps working.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        cache_dir: Path | str,
        size_limit_gb: int = 4,
    ) -> None:
        self._inner = inner
        self.name = inner.name
        self.model = inner.model
        self._cache = _open_cache(Path(cache_dir) / "gen", size_limit_gb=size_limit_gb)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        key = _hash_key(
            [
                "gen.v1",
                self._inner.name,
                self._inner.model,
                req.system or "",
                req.prompt,
                req.temperature,
                req.max_tokens,
            ]
        )
        hit = self._cache.get(key)
        if hit is not None:
            data = dict(hit)
            data["latency_ms"] = 0.0  # honest signal: this didn't hit the wire
            return GenerateResponse(**data)

        resp = self._inner.generate(req)
        self._cache.set(key, resp.model_dump())
        return resp

    def close(self) -> None:
        self._cache.close()


class CachingEmbeddingProvider:
    """Wrap an `EmbeddingProvider` so per-text embeddings are cached.

    Batched calls are split into per-text cache lookups; only the missing
    texts are forwarded to the upstream provider in a single batch. This
    means re-indexing the same schema chunks is free, and partial overlaps
    (e.g. one new column added) only pay for the delta.
    """

    def __init__(
        self,
        inner: EmbeddingProvider,
        *,
        cache_dir: Path | str,
        size_limit_gb: int = 4,
    ) -> None:
        self._inner = inner
        self.name = inner.name
        self.embed_model = inner.embed_model
        self._cache = _open_cache(Path(cache_dir) / "embed", size_limit_gb=size_limit_gb)

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        keys = [self._key_for(text) for text in req.texts]
        cached: list[list[float] | None] = [self._cache.get(k) for k in keys]
        missing_idx = [i for i, v in enumerate(cached) if v is None]

        if not missing_idx:
            vectors = [v for v in cached if v is not None]
            return EmbedResponse(vectors=vectors, model=self._inner.embed_model)

        missing_texts = [req.texts[i] for i in missing_idx]
        fresh = self._inner.embed(EmbedRequest(texts=missing_texts))
        if len(fresh.vectors) != len(missing_idx):
            raise RuntimeError(
                "embed batch length mismatch: "
                f"requested {len(missing_idx)}, got {len(fresh.vectors)}"
            )
        for j, vec in zip(missing_idx, fresh.vectors, strict=True):
            self._cache.set(keys[j], list(vec))
            cached[j] = list(vec)

        vectors = [v for v in cached if v is not None]
        return EmbedResponse(vectors=vectors, model=fresh.model)

    def _key_for(self, text: str) -> str:
        return _hash_key(
            [
                "embed.v1",
                self._inner.name,
                self._inner.embed_model,
                text,
            ]
        )

    def close(self) -> None:
        self._cache.close()


def wrap_with_cache(
    provider: LLMProvider,
    *,
    cache_dir: Path | str,
    size_limit_gb: int = 4,
) -> CachingLLMProvider:
    """Convenience wrapper for the common case (LLMProvider only)."""
    return CachingLLMProvider(provider, cache_dir=cache_dir, size_limit_gb=size_limit_gb)
