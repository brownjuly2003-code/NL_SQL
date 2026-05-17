"""Targeted grounded-critique retry on baseline failures.

Re-runs the production G pipeline (codestral + fewshot + verify-retry) BUT
with `enable_grounded_critique=True`, ONLY on the questions where the
multi-vote baseline still failed. The grounded_critique node detects
row-shape mismatches (e.g. question asks "how many X" expecting 1 row but
SQL returns 12) and re-prompts with the shape feedback as a hint.

Output is a voting-shaped report so `merge_voting_rescues.py` can fold
the rescues back into the multi-vote baseline.

Usage:
    uv run python scripts/run_critique_retry.py \
        --baseline eval/reports/2026-05-13/hybrid+multi-vote-v3.json \
        --bird-root data/bird_mini_dev/MINIDEV \
        --out eval/reports/2026-05-13/critique-retry.json
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
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers.groq import GroqProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--bird-root", type=Path, default=Path("data/bird_mini_dev/MINIDEV"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-cases", type=int, default=200)
    p.add_argument(
        "--fewshot-top-k",
        type=int,
        default=3,
        help="PipelineConfig.fewshot_top_k (default 3 = G prod). "
        "Use 5 for P2.B selective expansion experiment.",
    )
    p.add_argument(
        "--gen-model",
        type=str,
        default="codestral-latest",
        help="Mistral gen model id (default codestral-latest = G prod). "
        "Use mistral-large-latest for cross-model voting on residue.",
    )
    p.add_argument(
        "--sleep-between",
        type=float,
        default=0.0,
        help="Sleep N seconds between cases — required for mistral-large "
        "on free tier (rate-limited ~2 req/s).",
    )
    p.add_argument(
        "--provider",
        type=str,
        choices=("mistral", "groq"),
        default="mistral",
        help="SQL provider: mistral (default, uses --gen-model) or groq "
        "(uses --gen-model as Groq model id, e.g. qwen/qwen3-32b).",
    )
    p.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Override OpenAI-compatible base_url for the SQL provider. "
        "Use with --provider groq to redirect to OpenRouter "
        "(https://openrouter.ai/api/v1) or Gemini OpenAI compat "
        "(https://generativelanguage.googleapis.com/v1beta/openai). "
        "Requires GROQ_API_KEY env to actually hold the alt-provider key.",
    )
    p.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Override API key for the SQL provider (otherwise read from "
        "settings.groq_api_key / settings.mistral_api_key).",
    )
    args = p.parse_args()

    settings = get_settings()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    fails = [r for r in baseline["records"] if not r.get("match")]
    fails = fails[: args.max_cases]
    print(f"[info] {len(fails)} failures to retry with grounded_critique", file=sys.stderr)

    examples = {e.question_id: e for e in load_bird_mini_dev(args.bird_root)}
    registry = get_default_registry()

    if args.provider == "mistral":
        gen_provider = MistralProvider(api_key=settings.mistral_api_key, gen_model=args.gen_model)
    else:
        groq_kwargs = {
            "api_key": args.api_key or settings.groq_api_key,
            "model": args.gen_model,
        }
        if args.base_url:
            groq_kwargs["base_url"] = args.base_url
        gen_provider = GroqProvider(**groq_kwargs)
    sql_prov = CachingLLMProvider(gen_provider, cache_dir=settings.llm_cache_dir)
    expl_prov = sql_prov  # same provider for explain
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=settings.mistral_api_key), cache_dir=settings.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)

    cfg = PipelineConfig(
        sql_provider=sql_prov,
        explain_provider=expl_prov,
        schema_index=idx,
        registry=registry,
        fewshot_top_k=args.fewshot_top_k,
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
                    verify_retry_on_empty=True,
                )
            except Exception as exc:
                print(f"[{i:3d}/{len(fails)}] EXC qid={qid}: {exc}", file=sys.stderr)
                continue
            elapsed = (time.perf_counter() - t0) * 1000.0

            # Execute alt's pred against the DB and compare with gold.
            alt_rows = []
            if alt.outcome and alt.outcome.result:
                alt_rows = list(alt.outcome.result.rows)
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
            elif br.get("match") and not alt_match:
                regressed += 1
            else:
                same += 1

            records.append(
                {
                    "question_id": qid,
                    "db_id": ex.db_id,
                    "difficulty": ex.difficulty,
                    "question": ex.question,
                    "gold_sql": ex.sql,
                    "baseline_pred": br["pred_sql"],
                    "alt_pred": alt.sql,
                    "alt_confidence": getattr(alt, "confidence", None),
                    "baseline_match": bool(br.get("match")),
                    "alt_match": alt_match,
                    # Shape: rescue is what merge_voting_rescues.py looks for.
                    "vote_match": alt_match,
                    "vote_source": "critique-retry",
                    "elapsed_ms": elapsed,
                }
            )
            tag = (
                "RESCUE"
                if (alt_match and not br.get("match"))
                else ("regression" if (br.get("match") and not alt_match) else "same")
            )
            print(
                f"[{i:3d}/{len(fails)}] qid={qid} {ex.difficulty:11s} {tag} ({elapsed:.0f}ms)",
                file=sys.stderr,
            )
        finally:
            engine.dispose()
        if args.sleep_between > 0:
            time.sleep(args.sleep_between)

    print("\n=== critique-retry summary ===", file=sys.stderr)
    print(f"  cases: {len(records)}", file=sys.stderr)
    print(f"  rescued: {rescued}", file=sys.stderr)
    print(f"  regressed: {regressed}", file=sys.stderr)
    print(f"  same: {same}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "alt_model": f"{args.provider}:{args.gen_model}+grounded_critique+fewshot{args.fewshot_top_k}",
                "summary": {
                    "voted_better": rescued,
                    "voted_worse": regressed,
                    "voted_same": same,
                },
                "records": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
