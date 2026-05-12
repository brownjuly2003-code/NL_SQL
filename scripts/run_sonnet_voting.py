"""Sonnet 4.6 voting via GraceKelly Perplexity bridge on baseline failures.

For each failing qid, re-runs the production G pipeline through the
PerplexityProvider (Claude Sonnet 4.6 thinking via Perplexity Pro web UI).
Executes the alt SQL against the live engine and writes a voting-shaped
report compatible with `merge_voting_rescues.py`.

Latency: 20-40s per question (browser path), so this is a slow run. Budget:
free via Perplexity Pro subscription, no Groq quota consumed.

Usage:
    uv run python scripts/run_sonnet_voting.py \
        --baseline eval/reports/2026-05-13/hybrid+multi-vote+critique-v4.json \
        --out eval/reports/2026-05-13/sonnet-voting.json
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
from nl_sql.llm.cache import CachingEmbeddingProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.perplexity import PerplexityProvider
from nl_sql.schema_index.indexer import SchemaIndex


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--bird-root", type=Path, default=Path("data/bird_mini_dev/MINIDEV"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-cases", type=int, default=200)
    p.add_argument("--skip-qids", default="")
    p.add_argument("--model", default="claude-sonnet-4-6")
    args = p.parse_args()

    settings = get_settings()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    fails = [r for r in baseline["records"] if not r.get("match")]
    skip = {int(x) for x in args.skip_qids.split(",") if x.strip()}
    fails = [r for r in fails if r["question_id"] not in skip][: args.max_cases]
    print(f"[info] {len(fails)} failures to retry with {args.model}", file=sys.stderr)

    examples = {e.question_id: e for e in load_bird_mini_dev(args.bird_root)}
    registry = get_default_registry()
    sonnet = PerplexityProvider(model=args.model, timeout_seconds=180.0)
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=settings.mistral_api_key), cache_dir=settings.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)

    cfg = PipelineConfig(
        sql_provider=sonnet,
        explain_provider=sonnet,
        schema_index=idx,
        registry=registry,
        fewshot_top_k=3,
        sort_schema_block=True,
        cross_db_fewshot=True,
        verify_retry_on_empty=False,
        enable_grounded_critique=False,
    )
    pipeline = build_pipeline(cfg)

    records = []
    rescued = 0
    regressed = 0
    same = 0
    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

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
                print(f"[{i:3d}/{len(fails)}] qid={qid} EXC: {str(exc)[:150]}", file=sys.stderr)
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
                    "vote_source": "sonnet-bridge",
                    "elapsed_ms": elapsed,
                }
            )
            print(
                f"[{i:3d}/{len(fails)}] qid={qid} {ex.difficulty:11s} {tag} ({elapsed/1000:.1f}s)",
                file=sys.stderr,
            )

            # Snapshot after every record — browser bridge is slow and may
            # die mid-run. We don't want to lose progress.
            out_path.write_text(
                json.dumps(
                    {
                        "alt_model": f"perplexity:{args.model}",
                        "summary": {"voted_better": rescued, "voted_worse": regressed, "voted_same": same},
                        "records": records,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        finally:
            engine.dispose()

    print("\n=== sonnet-bridge summary ===", file=sys.stderr)
    print(f"  cases: {len(records)}", file=sys.stderr)
    print(f"  rescued: {rescued}", file=sys.stderr)
    print(f"  regressed: {regressed}", file=sys.stderr)
    print(f"  same: {same}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
