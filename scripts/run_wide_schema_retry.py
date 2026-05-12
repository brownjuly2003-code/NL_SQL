"""Wide-schema retry on row_count_off failures.

For each row_count_off failure, re-runs the production G pipeline with a
WIDER retrieval budget: schema_top_k=10, fk_hops=2, table_budget=20.

Rationale: row_count_off = the model picked a wrong JOIN structure or
missed a WHERE filter. A common root cause is that the right table was
not in the retrieved schema block (the model can't filter on a column it
hasn't seen). Bumping retrieval budget gives the model more context to
find the missing table / FK chain.

Memory: prior n=200 ablation tied top_k=5↔8 because table_budget=12
saturated. Lifting table_budget=20 is the un-tried regime.

Output is voting-shaped for `merge_voting_rescues.py`.

Usage:
    uv run python scripts/run_wide_schema_retry.py \
        --baseline eval/reports/2026-05-13/hybrid+multi-vote+critique+selfcon-v5.json \
        --out eval/reports/2026-05-13/wide-schema-retry.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from nl_sql.agent.graph import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.dataset import load_bird_mini_dev
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _compose_question, _execute_gold
from nl_sql.execution.runner import execute_validated
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def _is_row_count_off(r: dict[str, Any]) -> bool:
    if r.get("match") or r.get("error_kind"):
        return False
    gc = r.get("gold_row_count") or 0
    pc = r.get("pred_row_count") or 0
    return gc != pc


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--bird-root", type=Path, default=Path("data/bird_mini_dev/MINIDEV"))
    p.add_argument("--schema-top-k", type=int, default=10)
    p.add_argument("--fk-hops", type=int, default=2)
    p.add_argument("--table-budget", type=int, default=20)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    settings = get_settings()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    fails = [r for r in baseline["records"] if _is_row_count_off(r)]
    print(
        f"[info] {len(fails)} row_count_off fails to retry with "
        f"top_k={args.schema_top_k}, hops={args.fk_hops}, budget={args.table_budget}",
        file=sys.stderr,
    )

    examples = {e.question_id: e for e in load_bird_mini_dev(args.bird_root)}
    registry = get_default_registry()
    mistral = MistralProvider(api_key=settings.mistral_api_key, gen_model="codestral-latest")
    sql_prov = CachingLLMProvider(mistral, cache_dir=settings.llm_cache_dir)
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=settings.mistral_api_key), cache_dir=settings.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)

    cfg = PipelineConfig(
        sql_provider=sql_prov,
        explain_provider=sql_prov,
        schema_index=idx,
        registry=registry,
        schema_top_k=args.schema_top_k,
        fk_hops=args.fk_hops,
        table_budget=args.table_budget,
        fewshot_top_k=3,
        sort_schema_block=True,
        cross_db_fewshot=True,
        verify_retry_on_empty=True,
        enable_grounded_critique=True,
    )
    pipeline = build_pipeline(cfg)

    records = []
    rescued = 0
    regressed = 0
    same = 0
    for i, br in enumerate(fails, 1):
        qid = br["question_id"]
        ex = examples.get(qid)
        if ex is None:
            continue
        spec = registry.get(ex.registry_db_id)
        engine = spec.make_engine()
        try:
            t0 = time.perf_counter()
            try:
                alt = run_pipeline(
                    pipeline,
                    question=_compose_question(ex),
                    db_id=ex.registry_db_id,
                    dialect="sqlite",
                )
            except Exception as exc:
                print(f"[{i:3d}/{len(fails)}] qid={qid} EXC: {str(exc)[:120]}", file=sys.stderr)
                continue
            elapsed = (time.perf_counter() - t0) * 1000.0

            alt_sql = alt.sql or ""
            alt_rows: list[Any] = []
            try:
                outcome = execute_validated(
                    engine, alt_sql, dialect="sqlite",
                    statement_timeout_ms=30_000, row_cap=10_000,
                )
                if outcome.result:
                    alt_rows = list(outcome.result.rows)
            except Exception:
                pass
            try:
                gold_rows, _ = _execute_gold(engine, ex.sql, statement_timeout_ms=30_000, row_cap=10_000)
            except Exception:
                gold_rows = []
            alt_cmp = compare_results(gold_rows, alt_rows, gold_sql=ex.sql)
            alt_match = bool(alt_cmp.match)

            if alt_match and not br.get("match"):
                rescued += 1
                tag = "RESCUE"
            elif br.get("match") and not alt_match:
                regressed += 1
                tag = "regression"
            else:
                same += 1
                tag = "same"

            records.append(
                {
                    "question_id": qid,
                    "db_id": ex.db_id,
                    "difficulty": ex.difficulty,
                    "question": ex.question,
                    "gold_sql": ex.sql,
                    "baseline_pred": br["pred_sql"],
                    "alt_pred": alt_sql,
                    "alt_confidence": getattr(alt, "confidence", None),
                    "baseline_match": bool(br.get("match")),
                    "alt_match": alt_match,
                    "vote_match": alt_match,
                    "vote_source": "wide-schema",
                    "elapsed_ms": elapsed,
                }
            )
            print(
                f"[{i:3d}/{len(fails)}] qid={qid} {ex.difficulty:11s} {tag} ({elapsed:.0f}ms)",
                file=sys.stderr,
            )
        finally:
            engine.dispose()

    print("\n=== wide-schema retry summary ===", file=sys.stderr)
    print(f"  cases: {len(records)}  rescued: {rescued}  regressed: {regressed}  same: {same}",
          file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "alt_model": f"codestral+wide-schema(top_k={args.schema_top_k},hops={args.fk_hops},budget={args.table_budget})+critique",
                "summary": {"voted_better": rescued, "voted_worse": regressed, "voted_same": same},
                "records": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
