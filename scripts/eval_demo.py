"""Evaluate the pipeline on the curated demo benchmark.

Unlike `eval_baseline.py`, which measures BIRD Mini-Dev (research baseline
~50% ceiling), this script measures a *product workload*: 30 realistic
business questions on Chinook where we target ≥90% Execution Accuracy.

Usage:
    uv run python scripts/eval_demo.py
    uv run python scripts/eval_demo.py --benchmark eval/demo_benchmark.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import chromadb

from nl_sql.agent import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.connection import Dialect, execute_readonly
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex

DEFAULT_BENCHMARK = Path(__file__).parent.parent / "eval" / "demo_benchmark.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark", type=Path, default=DEFAULT_BENCHMARK,
        help=f"path to benchmark JSON (default: {DEFAULT_BENCHMARK})",
    )
    parser.add_argument("--persist", default="chroma_data")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--report", type=Path,
        help="optional output JSON path for the full per-question report",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.mistral_api_key:
        print("[error] MISTRAL_API_KEY not set in .env", file=sys.stderr)
        return 2

    bench = json.loads(args.benchmark.read_text(encoding="utf-8"))
    db_id = bench["db_id"]
    dialect: Dialect = bench.get("dialect", "sqlite")
    questions = bench["questions"]
    print(f"[info] benchmark: {bench['name']} ({len(questions)} questions on {db_id!r})")

    persist = Path(args.persist)
    if not persist.is_dir():
        print(f"[error] index not found at {persist}; run scripts/build_index.py first")
        return 3

    client = chromadb.PersistentClient(path=str(persist))
    raw_embed = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    raw_sql = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    raw_explain = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model="mistral-large-latest",
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    embedder = raw_embed if args.no_cache else CachingEmbeddingProvider(
        raw_embed, cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    sql_provider = raw_sql if args.no_cache else CachingLLMProvider(
        raw_sql, cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    explain_provider = raw_explain if args.no_cache else CachingLLMProvider(
        raw_explain, cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )

    index = SchemaIndex(persist_dir=persist, embedder=embedder, client=client)
    registry = get_default_registry()
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_provider,
            explain_provider=explain_provider,
            schema_index=index,
            registry=registry,
            schema_top_k=5,
            fewshot_top_k=0,
            fk_hops=1,
            table_budget=12,
            sort_schema_block=True,
            primary_sample_size=3,
        )
    )

    spec = registry.get(db_id)
    gold_engine = spec.make_engine()

    records: list[dict[str, Any]] = []
    started_all = time.perf_counter()
    try:
        for i, q in enumerate(questions, start=1):
            t0 = time.perf_counter()
            try:
                result = run_pipeline(pipeline, question=q["question"], db_id=db_id, dialect=dialect)
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                records.append({
                    "id": q["id"], "category": q.get("category", ""),
                    "difficulty": q.get("difficulty", ""),
                    "split": q.get("split", "dev"),
                    "question": q["question"], "gold_sql": q["gold_sql"],
                    "pred_sql": "", "match": False,
                    "reason": f"pipeline raised: {exc!r}",
                    "latency_ms": elapsed,
                })
                print(f"  [{i:>2}/{len(questions)}] EXCEPTION {q['id']}: {exc}")
                continue

            with execute_readonly(gold_engine, q["gold_sql"], statement_timeout_ms=30_000, row_cap=10_000) as gold:
                gold_rows = list(gold.rows)

            if result.outcome is not None and result.outcome.result is not None:
                cmp = compare_results(gold_rows, result.outcome.result.rows, gold_sql=q["gold_sql"])
                match = cmp.match
                reason = cmp.reason
            else:
                match = False
                reason = f"pred failed: {result.error_kind.value if result.error_kind else 'unknown'}"

            elapsed = (time.perf_counter() - t0) * 1000
            flag = "OK  " if match else "MISS"
            print(f"  [{i:>2}/{len(questions)}] {flag} ({elapsed:5.0f}ms) {q['id']} — {q['question'][:70]}")
            if not match:
                print(f"        gold: {q['gold_sql'][:140]}")
                print(f"        pred: {result.sql[:140]}")
                print(f"        why:  {reason}")
            records.append({
                "id": q["id"], "category": q.get("category", ""),
                "difficulty": q.get("difficulty", ""),
                "split": q.get("split", "dev"),
                "question": q["question"], "gold_sql": q["gold_sql"],
                "pred_sql": result.sql, "match": match, "reason": reason,
                "latency_ms": elapsed,
            })
    finally:
        gold_engine.dispose()

    elapsed_total = time.perf_counter() - started_all
    matches = sum(1 for r in records if r["match"])
    ea = matches / len(records) if records else 0.0
    print()
    print("=" * 78)
    print(f"Demo benchmark: {bench['name']}")
    print(f"DB:             {db_id} ({dialect})")
    print(f"Questions:      {len(records)}")
    print(f"Match:          {matches}/{len(records)} = {ea * 100:.1f}%")
    by_cat: dict[str, list[bool]] = defaultdict(list)
    by_diff: dict[str, list[bool]] = defaultdict(list)
    by_split: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        by_cat[r["category"]].append(r["match"])
        by_diff[r["difficulty"]].append(r["match"])
        by_split[r["split"]].append(r["match"])
    print("per category:")
    for cat, ms in sorted(by_cat.items()):
        print(f"  {cat:14s} {sum(ms):>2}/{len(ms):<2} ({sum(ms) / len(ms) * 100:5.1f}%)")
    print("per difficulty:")
    for d, ms in sorted(by_diff.items()):
        print(f"  {d:14s} {sum(ms):>2}/{len(ms):<2} ({sum(ms) / len(ms) * 100:5.1f}%)")
    print("per split:")
    for s, ms in sorted(by_split.items()):
        print(f"  {s:14s} {sum(ms):>2}/{len(ms):<2} ({sum(ms) / len(ms) * 100:5.1f}%)")
    print(f"Wall time: {elapsed_total:.1f}s")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps({
                "benchmark": bench["name"], "db_id": db_id, "dialect": dialect,
                "n": len(records), "matches": matches, "ea": ea,
                "records": records,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[report] {args.report}")

    return 0 if ea >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
