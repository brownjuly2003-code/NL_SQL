"""Targeted self-consistency retry on baseline failures with Mistral codestral.

For each failing question, runs the production G pipeline N times at distinct
temperatures (0.2, 0.4, 0.6, 0.8 by default), executes each candidate, and
votes via the largest fingerprint cluster (ties → highest confidence). Output
is voting-shaped for `merge_voting_rescues.py`.

Same model (Mistral codestral) — wins beyond ~1-2 are unlikely because
voting same-model against itself plateaus, but it's a free-tier sanity probe.

Usage:
    uv run python scripts/run_selfcon_retry.py \
        --baseline eval/reports/2026-05-13/hybrid+multi-vote+critique-v4.json \
        --out eval/reports/2026-05-13/selfcon-retry.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from nl_sql.agent.graph import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.dataset import load_bird_mini_dev
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _compose_question, _execute_gold
from nl_sql.eval.self_consistency import Candidate, vote
from nl_sql.execution.runner import execute_validated
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--bird-root", type=Path, default=Path("data/bird_mini_dev/MINIDEV"))
    p.add_argument("--temperatures", nargs="+", type=float, default=[0.2, 0.4, 0.6, 0.8])
    p.add_argument("--gen-model", default="codestral-latest", help="Mistral model id")
    p.add_argument("--sleep-between", type=float, default=0.0, help="seconds between pipeline calls (use for mistral-large rate limits)")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    settings = get_settings()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    fails = [r for r in baseline["records"] if not r.get("match")]
    print(f"[info] {len(fails)} failures, temps={args.temperatures}, model={args.gen_model}", file=sys.stderr)

    examples = {e.question_id: e for e in load_bird_mini_dev(args.bird_root)}
    registry = get_default_registry()
    mistral = MistralProvider(api_key=settings.mistral_api_key, gen_model=args.gen_model)
    sql_prov = CachingLLMProvider(mistral, cache_dir=settings.llm_cache_dir)
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=settings.mistral_api_key), cache_dir=settings.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)

    pipelines = [
        build_pipeline(
            PipelineConfig(
                sql_provider=sql_prov,
                explain_provider=sql_prov,
                schema_index=idx,
                registry=registry,
                fewshot_top_k=3,
                sort_schema_block=True,
                cross_db_fewshot=True,
                verify_retry_on_empty=False,
                sql_temperature=t,
            )
        )
        for t in args.temperatures
    ]

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
            candidates = []
            for pipeline, temp in zip(pipelines, args.temperatures, strict=True):
                try:
                    r = run_pipeline(
                        pipeline,
                        question=_compose_question(ex),
                        db_id=ex.registry_db_id,
                        dialect="sqlite",
                    )
                    candidates.append(Candidate(result=r, temperature=temp))
                except Exception as exc:
                    print(f"[{i:3d}/{len(fails)}] qid={qid} T={temp} EXC: {exc}", file=sys.stderr)
                if args.sleep_between > 0:
                    time.sleep(args.sleep_between)
            if not candidates:
                continue

            winner = vote(candidates)
            elapsed = (time.perf_counter() - t0) * 1000.0

            alt_sql = winner.result.sql or ""
            try:
                outcome = execute_validated(
                    engine,
                    alt_sql,
                    dialect="sqlite",
                    statement_timeout_ms=30_000,
                    row_cap=10_000,
                )
                alt_rows = list(outcome.result.rows) if outcome.result else []
            except Exception:
                alt_rows = []
            try:
                gold_rows, _ = _execute_gold(
                    engine, ex.sql, statement_timeout_ms=30_000, row_cap=10_000
                )
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
                    "alt_confidence": getattr(winner.result, "confidence", None),
                    "winner_temperature": winner.temperature,
                    "baseline_match": bool(br.get("match")),
                    "alt_match": alt_match,
                    "vote_match": alt_match,
                    "vote_source": "self-consistency",
                    "elapsed_ms": elapsed,
                }
            )
            print(
                f"[{i:3d}/{len(fails)}] qid={qid} {ex.difficulty:11s} {tag} T_win={winner.temperature:.1f} ({elapsed:.0f}ms)",
                file=sys.stderr,
            )
        finally:
            engine.dispose()

    print("\n=== self-consistency retry summary ===", file=sys.stderr)
    print(f"  cases: {len(records)}", file=sys.stderr)
    print(f"  rescued: {rescued}", file=sys.stderr)
    print(f"  regressed: {regressed}", file=sys.stderr)
    print(f"  same: {same}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "alt_model": "codestral+self-consistency",
                "temperatures": list(args.temperatures),
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
