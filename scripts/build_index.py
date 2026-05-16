"""Build the Chroma schema index for one (or all) registered databases.

Live tool — calls Mistral `mistral-embed` for vectors. Idempotent: re-runs
upsert chunks under the same `chunk_id` (db::table), so vectors get refreshed
in place and stale chunks for renamed tables are NOT auto-pruned (run with
``--reset`` to clear the collection first if you have schema deletions).

The default ``--sample-size`` is imported from ``PipelineConfig.primary_sample_size``
so the index is built with the same density runtime expects. Pass an explicit
value only if you want to rebuild for a non-default runtime configuration.

Usage:
    uv run python scripts/build_index.py --db chinook
    uv run python scripts/build_index.py --db all --persist chroma_data
    uv run python scripts/build_index.py --db chinook --reset
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from pathlib import Path

import chromadb

from nl_sql.agent.graph import PipelineConfig
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.llm.cache import CachingEmbeddingProvider
from nl_sql.llm.providers.base import EmbeddingProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.indexer import SCHEMA_COLLECTION, SchemaIndex
from nl_sql.schema_index.introspector import introspect


def _runtime_sample_size_default() -> int:
    """Read `PipelineConfig.primary_sample_size` default without constructing
    the dataclass (it requires live providers/registry we don't have here)."""
    for field_ in fields(PipelineConfig):
        if field_.name == "primary_sample_size":
            default = field_.default
            if isinstance(default, int):
                return default
    raise RuntimeError("PipelineConfig.primary_sample_size default missing")


DEFAULT_SAMPLE_SIZE: int = _runtime_sample_size_default()
"""Source of truth for the sample density baked into Chroma chunks.
Runtime expects this to equal `PipelineConfig.primary_sample_size`; the
mixture appendix breaks if the index is built with more samples than
runtime advertises."""


def build_for_db(idx: SchemaIndex, db_id: str, *, sample_size: int = DEFAULT_SAMPLE_SIZE) -> int:
    registry = get_default_registry()
    spec = registry.get(db_id)
    print(f"[introspect] {db_id} ({spec.url})")
    tables = introspect(spec.make_engine(), sample_size=sample_size)
    print(f"[chunk] {len(tables)} tables → chunks")
    chunks = to_chunks(tables, db_id=db_id)
    print(f"[index] embedding + upserting {len(chunks)} chunks")
    n = idx.index_schema(chunks)
    print(f"[done] {db_id}: {n} chunks indexed")
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        required=True,
        help="Database id (e.g. 'chinook', 'bird_california_schools') or 'all'.",
    )
    parser.add_argument(
        "--persist",
        default="chroma_data",
        help="Chroma persist directory (default: chroma_data/)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=(
            "Top-K sample values per column to bake into each chunk "
            f"(default: {DEFAULT_SAMPLE_SIZE} = PipelineConfig.primary_sample_size). "
            "Keep aligned with runtime or the sample-mixture appendix breaks."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop the schema_chunks collection before indexing.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable diskcache wrapper around the embedding provider.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    settings = get_settings()
    persist = Path(args.persist)
    persist.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist))
    if args.reset:
        try:
            client.delete_collection(SCHEMA_COLLECTION)
            print(f"[reset] dropped {SCHEMA_COLLECTION}")
        except Exception as exc:
            print(f"[reset] no existing {SCHEMA_COLLECTION} to drop ({exc})")

    raw_embedder = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    embedder: EmbeddingProvider = (
        raw_embedder
        if args.no_cache
        else CachingEmbeddingProvider(
            raw_embedder,
            cache_dir=settings.llm_cache_dir,
            size_limit_gb=settings.llm_cache_size_limit_gb,
        )
    )
    idx = SchemaIndex(persist_dir=persist, embedder=embedder, client=client)

    registry = get_default_registry()
    targets = registry.ids() if args.db == "all" else [args.db]

    total = 0
    for db_id in targets:
        total += build_for_db(idx, db_id, sample_size=args.sample_size)
    print(f"[summary] indexed {total} chunks across {len(targets)} db(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
