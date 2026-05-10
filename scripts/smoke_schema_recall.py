"""Live smoke-test: schema recall@5 on Chinook (5 hand-picked questions).

Runs against the persisted Chroma index built by `scripts/build_index.py` —
no DB introspection here, just retrieval. Each question has a set of
"required" tables (must appear in top-K) and "bonus" tables (preferred).

Output is a per-question table + recall@5 = (#hits with all required tables
present in top-K) / (#questions). With a working semantic embedder this
should score 5/5 on Chinook; with a broken embedder it'll show < 1.0.

Usage:
    uv run python scripts/build_index.py --db chinook
    uv run python scripts/smoke_schema_recall.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import chromadb

from nl_sql.config import get_settings
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.retriever import retrieve_context


@dataclass(frozen=True)
class RecallCase:
    question: str
    required_tables: frozenset[str]


CHINOOK_CASES: tuple[RecallCase, ...] = (
    RecallCase(
        question="Which artists have released the most albums?",
        required_tables=frozenset({"Artist", "Album"}),
    ),
    RecallCase(
        question="Top-spending customers per country.",
        required_tables=frozenset({"Customer", "Invoice"}),
    ),
    RecallCase(
        question="Which tracks are longest, and what genre are they?",
        required_tables=frozenset({"Track", "Genre"}),
    ),
    RecallCase(
        question="How many tracks does each playlist contain?",
        required_tables=frozenset({"Playlist", "PlaylistTrack"}),
    ),
    RecallCase(
        question="Sales agents and the customers they support.",
        required_tables=frozenset({"Employee", "Customer"}),
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="chinook", help="db_id to query (default: chinook)")
    parser.add_argument("--persist", default="chroma_data")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fk-hops", type=int, default=0, help="Set 0 to measure pure dense recall")
    args = parser.parse_args(argv)

    settings = get_settings()
    persist = Path(args.persist)
    if not persist.is_dir():
        print(f"[error] index not found at {persist}; run scripts/build_index.py first")
        return 2
    client = chromadb.PersistentClient(path=str(persist))
    embedder = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    idx = SchemaIndex(persist_dir=persist, embedder=embedder, client=client)

    print(f"\nSchema recall@{args.top_k} on db_id={args.db!r} (fk_hops={args.fk_hops})\n")
    print(f"{'#':>2}  {'required':<30}  {'top-k tables':<40}  hit?")
    print("-" * 90)

    hits = 0
    for i, case in enumerate(CHINOOK_CASES, start=1):
        bundle = retrieve_context(
            idx,
            case.question,
            db_id=args.db,
            schema_top_k=args.top_k,
            fk_hops=args.fk_hops,
            fewshot_top_k=0,
        )
        retrieved = [h.table_name for h in bundle.schema_hits]
        ok = case.required_tables.issubset(set(retrieved))
        hits += int(ok)
        marker = "OK " if ok else "MISS"
        req = ", ".join(sorted(case.required_tables))
        ret = ", ".join(retrieved)
        print(f"{i:>2}  {req:<30}  {ret:<40}  {marker}")
        if not ok:
            print(f"     question: {case.question}")
            print(f"     missing : {sorted(case.required_tables - set(retrieved))}")

    print("-" * 90)
    print(f"recall@{args.top_k} = {hits}/{len(CHINOOK_CASES)} = {hits / len(CHINOOK_CASES):.0%}")
    return 0 if hits == len(CHINOOK_CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
