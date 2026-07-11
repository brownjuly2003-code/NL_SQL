"""Drop-in eval driver for plan-then-SQL ablation.

Why a dedicated script instead of `scripts/eval_baseline.py --config G`:
we need the `enable_planner=True` knob on PipelineConfig which the
existing driver doesn't surface yet, and we want robust progress logging
+ resumable JSON output without the background-shell-pipe issues we hit
when running long evals via the harness.

Usage:
    uv run python scripts/run_planner_eval.py \\
        --difficulty moderate --n 200 --seed 0 \\
        --out eval/reports/2026-05-11/G_planner-moderate-n99.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from nl_sql.agent.graph import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.dataset import dev_split, load_bird_mini_dev
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _compose_question, _execute_gold
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers import build_provider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--difficulty", choices=["simple", "moderate", "challenging"], default=None)
    p.add_argument("--n", type=int, default=200, help="prefix size BEFORE difficulty filter")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="per-example progress log; default <out>.progress.log",
    )
    p.add_argument("--enable-planner", action="store_true", default=False)
    p.add_argument("--no-planner", dest="enable_planner", action="store_false")
    p.add_argument("--enable-grounded-critique", action="store_true", default=False)
    p.add_argument("--bird-root", default="data/bird_mini_dev/MINIDEV")
    p.add_argument("--provider", default="mistral")
    p.add_argument("--limit", type=int, default=0, help="cap examples after filtering (0=all)")
    args = p.parse_args()

    log_path = args.log or args.out.with_suffix(".progress.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    s = get_settings()
    sql_prov = CachingLLMProvider(
        build_provider(args.provider, settings=s), cache_dir=s.llm_cache_dir
    )
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=s.mistral_api_key), cache_dir=s.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)
    registry = get_default_registry()

    examples = load_bird_mini_dev(Path(args.bird_root))
    sample = dev_split(examples, n=args.n, seed=args.seed)
    if args.difficulty:
        sample = [e for e in sample if e.difficulty == args.difficulty]
    if args.limit:
        sample = sample[: args.limit]

    cfg = PipelineConfig(
        sql_provider=sql_prov,
        explain_provider=sql_prov,
        schema_index=idx,
        registry=registry,
        fewshot_top_k=3,
        sort_schema_block=True,
        cross_db_fewshot=True,
        verify_retry_on_empty=True,
        enable_planner=args.enable_planner,
        enable_grounded_critique=args.enable_grounded_critique,
        statement_timeout_ms=30_000,
        row_cap=10_000,
    )
    pipe = build_pipeline(cfg)

    def log(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        log_path.open("a", encoding="utf-8").write(line)
        sys.stderr.write(line)
        sys.stderr.flush()

    log(
        f"start: n={len(sample)} difficulty={args.difficulty} enable_planner={args.enable_planner} out={args.out}"
    )

    records: list[dict] = []
    matched = 0
    for i, ex in enumerate(sample, 1):
        started = time.perf_counter()
        spec = registry.get(ex.registry_db_id)
        gold_engine = spec.make_engine()
        try:
            try:
                res = run_pipeline(
                    pipe,
                    question=_compose_question(ex),
                    db_id=ex.registry_db_id,
                    dialect="sqlite",
                    verify_retry_on_empty=True,
                )
            except Exception as exc:
                log(f"[{i:3d}/{len(sample)}] EXC qid={ex.question_id}: {type(exc).__name__}: {exc}")
                traceback.print_exc(file=sys.stderr)
                continue
            try:
                gold_rows, _ = _execute_gold(
                    gold_engine, ex.sql, statement_timeout_ms=30_000, row_cap=10_000
                )
            except Exception:
                gold_rows = []
            if res.outcome is not None and res.outcome.result is not None:
                cmp = compare_results(gold_rows, res.outcome.result.rows, gold_sql=ex.sql)
                ok = cmp.match
                reason = cmp.reason
                gc, pc = cmp.gold_rows, cmp.pred_rows
            else:
                ok = False
                reason = res.error_kind.value if res.error_kind else "no result"
                gc, pc = len(gold_rows), 0
            if ok:
                matched += 1
            records.append(
                {
                    "question_id": ex.question_id,
                    "db_id": ex.db_id,
                    "difficulty": ex.difficulty,
                    "dialect": ex.dialect,
                    "question": ex.question,
                    "gold_sql": ex.sql,
                    "pred_sql": res.sql,
                    "match": bool(ok),
                    "comparison_reason": reason,
                    "gold_row_count": gc,
                    "pred_row_count": pc,
                    "error_kind": res.error_kind.value if res.error_kind else None,
                    "confidence": res.confidence,
                    "repair_attempted": res.repair_attempted,
                }
            )
            elapsed = (time.perf_counter() - started) * 1000.0
            log(
                f"[{i:3d}/{len(sample)}] {'OK ' if ok else '   '} ({elapsed:6.0f}ms) "
                f"qid={ex.question_id} {ex.registry_db_id}/{ex.difficulty} — "
                f"{ex.question[:60]}"
            )

            # incremental dump every 10 to survive crashes
            if i % 10 == 0:
                args.out.write_text(
                    json.dumps(
                        {
                            "configuration": "G_planner",
                            "sql_model": "codestral-latest",
                            "overall": {"ea": matched / len(records), "n": len(records)},
                            "records": records,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
        finally:
            gold_engine.dispose()

    ea = matched / len(records) if records else 0.0
    args.out.write_text(
        json.dumps(
            {
                "configuration": "G_planner",
                "sql_model": "codestral-latest",
                "overall": {"ea": ea, "n": len(records), "matched": matched},
                "records": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log(f"done: EA={matched}/{len(records)} = {100 * ea:.1f}% → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
