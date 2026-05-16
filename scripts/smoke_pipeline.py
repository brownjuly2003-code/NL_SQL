"""Live smoke-test of the full LangGraph pipeline on Chinook.

Runs 5 hand-picked questions through the compiled graph with real Mistral
providers (codestral-latest for SQL + repair, mistral-large-latest for the
NL caption). Requires:
- `chroma_data/` populated for `chinook` (run `scripts/build_index.py --db chinook`)
- `MISTRAL_API_KEY` set in `.env`

Usage:
    uv run python scripts/smoke_pipeline.py
    uv run python scripts/smoke_pipeline.py --question "list AC/DC albums"

Output per question: SQL + result (truncated) + caption + timing + error
kind if any. The `--verbose` flag dumps the full LangGraph trace per question.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import chromadb

from nl_sql.agent import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


@dataclass(frozen=True)
class SmokeQuestion:
    text: str
    expected_tables: frozenset[str] = frozenset()


CHINOOK_QUESTIONS: tuple[SmokeQuestion, ...] = (
    SmokeQuestion(
        text="How many albums are in the catalog?",
        expected_tables=frozenset({"Album"}),
    ),
    SmokeQuestion(
        text="List the names of all artists who have at least one album.",
        expected_tables=frozenset({"Artist", "Album"}),
    ),
    SmokeQuestion(
        text="What are the 5 longest tracks and which genre are they?",
        expected_tables=frozenset({"Track", "Genre"}),
    ),
    SmokeQuestion(
        text="Which country has the most customers?",
        expected_tables=frozenset({"Customer"}),
    ),
    SmokeQuestion(
        text="Total revenue per sales agent (Employee).",
        expected_tables=frozenset({"Employee", "Customer", "Invoice"}),
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="chinook", help="db_id (default: chinook)")
    parser.add_argument("--persist", default="chroma_data")
    parser.add_argument("--question", help="Run one ad-hoc question instead of the bundled set.")
    parser.add_argument("--verbose", action="store_true", help="Dump LangGraph trace per question.")
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
    index = SchemaIndex(persist_dir=persist, embedder=embedder, client=client)

    sql_provider = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    explain_provider = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model="mistral-large-latest",
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )

    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_provider,
            explain_provider=explain_provider,
            schema_index=index,
            registry=get_default_registry(),
            schema_top_k=5,
            fewshot_top_k=0,  # no fewshot pool yet (stage 4 v1)
            fk_hops=1,
            table_budget=10,
        )
    )

    questions: tuple[SmokeQuestion, ...]
    questions = (SmokeQuestion(text=args.question),) if args.question else CHINOOK_QUESTIONS

    ok_count = 0
    print(f"\nLive pipeline smoke against db_id={args.db!r}\n{'=' * 78}\n")
    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q.text}")
        started = time.perf_counter()
        try:
            result = run_pipeline(pipeline, question=q.text, db_id=args.db)
        except Exception as exc:
            print(f"  EXCEPTION: {exc}\n")
            continue
        elapsed = time.perf_counter() - started

        status = "OK " if result.ok else "FAIL"
        print(f"  status      : {status} ({elapsed:.1f}s)")
        print(f"  SQL         : {result.sql}")
        if result.rationale:
            print(f"  rationale   : {result.rationale}")
        print(f"  confidence  : {result.confidence:.2f}")
        print(f"  repaired    : {result.repair_attempted}")
        if result.outcome and result.outcome.result:
            res = result.outcome.result
            preview = res.rows[:3]
            print(f"  rows        : {res.row_count} | preview: {preview}")
        if result.error_kind:
            print(f"  error       : {result.error_kind.value} — {result.error_message}")
        print(f"  caption     : {result.caption}")

        if q.expected_tables:
            sql_lc = result.sql.lower()
            covered = all(t.lower() in sql_lc for t in q.expected_tables)
            tag = "OK" if covered else "MISS"
            print(f"  table cover : {tag} (expected: {sorted(q.expected_tables)})")

        if args.verbose:
            print("  trace:")
            for step in result.trace:
                print(f"    - {step}")

        if result.ok:
            ok_count += 1
        print()

    total = len(questions)
    print("=" * 78)
    print(f"summary: {ok_count}/{total} succeeded")
    return 0 if ok_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
