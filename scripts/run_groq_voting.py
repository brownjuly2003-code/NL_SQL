"""Cross-provider voting on hard BIRD failures.

For each question where the codestral baseline got the answer wrong,
re-run with an alternate Groq model (qwen3-32b or gpt-oss-120b), execute
both pred SQLs, fingerprint result rows, and accept the winning cluster.
Targeted at the `filter_or_value` bucket where row shape was right but
logic was wrong — voting is the right tool when same-shape disagreement
is the failure mode.

Token-aware: Groq free tier is 100K TPD per model. The script processes
at most --max-cases per provider and reports the actual token spend.

Usage:
    uv run python scripts/run_groq_voting.py \
        --baseline eval/baselines/hybrid_n200_v0.json \
        --provider-model qwen/qwen3-32b \
        --max-cases 20 \
        --out eval/reports/2026-05-12/qwen3-voting.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

from nl_sql.agent.graph import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.dataset import load_bird_mini_dev
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _compose_question, _execute_gold
from nl_sql.eval.self_consistency import fingerprint_rows
from nl_sql.execution.runner import execute_validated
from nl_sql.llm.cache import CachingEmbeddingProvider
from nl_sql.llm.providers.base import GenerateRequest
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex

_RE_AGG = re.compile(r"\b(sum|avg|count|min|max|cast)\s*\(", re.IGNORECASE)


def _is_filter_or_value(r: dict) -> bool:
    """Same row count, both ran, no execution error, value mismatch."""
    if r.get("match") or r.get("error_kind"):
        return False
    gc = r.get("gold_row_count") or 0
    pc = r.get("pred_row_count") or 0
    return gc == pc and gc > 0


def _is_row_count_off(r: dict) -> bool:
    """Both queries ran, row counts differ — wrong WHERE / GROUP BY / JOIN."""
    if r.get("match") or r.get("error_kind"):
        return False
    gc = r.get("gold_row_count") or 0
    pc = r.get("pred_row_count") or 0
    return gc != pc


def _is_order_by_off(r: dict) -> bool:
    """Same row count, but ordered-row mismatch — different sort or top item."""
    if r.get("match") or r.get("error_kind"):
        return False
    gc = r.get("gold_row_count") or 0
    pc = r.get("pred_row_count") or 0
    if gc != pc:
        return False
    reason = (r.get("comparison_reason") or "").lower()
    return reason.startswith("ordered row")


_BUCKETS = {
    "filter_or_value": _is_filter_or_value,
    "row_count_off": _is_row_count_off,
    "order_by_off": _is_order_by_off,
    "any_failure": lambda r: not r.get("match"),
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--provider-model", required=True, help="Groq model id (e.g. qwen/qwen3-32b)")
    p.add_argument("--max-cases", type=int, default=20)
    p.add_argument("--bucket", default="filter_or_value", choices=list(_BUCKETS.keys()))
    p.add_argument("--difficulty", default=None, choices=["simple", "moderate", "challenging"])
    p.add_argument("--skip-qids", default="", help="comma-separated qids to skip (already covered by prior runs)")
    p.add_argument("--bird-root", default="data/bird_mini_dev/MINIDEV")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    settings = get_settings()
    examples = {e.question_id: e for e in load_bird_mini_dev(Path(args.bird_root))}
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))["records"]

    # Pick failing cases of the requested bucket (optionally filter difficulty).
    bucket_fn = _BUCKETS[args.bucket]
    skip = {int(x) for x in args.skip_qids.split(",") if x.strip()}
    candidates = [r for r in baseline if bucket_fn(r) and r["question_id"] not in skip]
    if args.difficulty:
        candidates = [r for r in candidates if r["difficulty"] == args.difficulty]
    candidates = candidates[: args.max_cases]
    print(
        f"[info] picked {len(candidates)} {args.bucket} cases "
        f"(skipped {len(skip)} qids)",
        file=sys.stderr,
    )

    # Pipeline with the Groq alt model. We override the codestral-cached
    # provider with a fresh Groq client at the chosen model id.
    raw_groq = OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)

    class _GroqAlt:
        name = "groq_alt"
        model = args.provider_model

        def generate(self, req: GenerateRequest):  # type: ignore[no-untyped-def]
            # Don't force response_format — Groq's reasoning models (gpt-oss)
            # often emit <think>...</think> tags that break json_object
            # validation. The downstream parser already handles fenced JSON,
            # extra prose, and partial JSON via _strip_to_sql fallback.
            messages = [{"role": "user", "content": req.prompt}]
            t0 = time.perf_counter()
            try:
                completion = raw_groq.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
            except Exception as exc:
                raise RuntimeError(f"groq {self.model}: {exc}") from exc
            lat = (time.perf_counter() - t0) * 1000.0
            from nl_sql.llm.providers.base import GenerateResponse
            return GenerateResponse(
                text=completion.choices[0].message.content or "",
                model=completion.model or self.model,
                input_tokens=(completion.usage.prompt_tokens if completion.usage else 0),
                output_tokens=(completion.usage.completion_tokens if completion.usage else 0),
                latency_ms=lat,
            )

    groq_alt = _GroqAlt()
    emb = CachingEmbeddingProvider(
        MistralProvider(api_key=settings.mistral_api_key), cache_dir=settings.llm_cache_dir
    )
    idx = SchemaIndex(persist_dir="chroma_data", embedder=emb)
    registry = get_default_registry()

    cfg = PipelineConfig(
        sql_provider=groq_alt,  # type: ignore[arg-type]
        explain_provider=groq_alt,  # type: ignore[arg-type]
        schema_index=idx,
        registry=registry,
        fewshot_top_k=3,
        sort_schema_block=True,
        cross_db_fewshot=True,
        verify_retry_on_empty=True,
    )
    pipeline = build_pipeline(cfg)

    records = []
    total_in_tokens = 0
    total_out_tokens = 0
    voted_better = 0
    voted_worse = 0
    voted_same = 0

    for i, baseline_rec in enumerate(candidates, 1):
        qid = baseline_rec["question_id"]
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
                print(f"[{i:3d}/{len(candidates)}] EXC qid={qid}: {exc}", file=sys.stderr)
                continue

            # Sum input/output tokens for budget tracking
            for step in alt.trace:
                if isinstance(step.get("input_tokens"), int):
                    total_in_tokens += step["input_tokens"]
                if isinstance(step.get("output_tokens"), int):
                    total_out_tokens += step["output_tokens"]

            # Execute alt's pred against the DB
            alt_rows: list = []
            if alt.outcome and alt.outcome.result:
                alt_rows = list(alt.outcome.result.rows)

            # Baseline pred (codestral) — re-execute for fingerprinting
            try:
                base_outcome = execute_validated(
                    engine,
                    baseline_rec["pred_sql"],
                    dialect="sqlite",
                    statement_timeout_ms=30_000,
                    row_cap=10_000,
                )
                base_rows = list(base_outcome.result.rows) if base_outcome.result else []
            except Exception:
                base_rows = []

            try:
                gold_rows, _ = _execute_gold(
                    engine, ex.sql, statement_timeout_ms=30_000, row_cap=10_000
                )
            except Exception:
                gold_rows = []

            # Verdicts
            base_cmp = compare_results(gold_rows, base_rows, gold_sql=ex.sql)
            alt_cmp = compare_results(gold_rows, alt_rows, gold_sql=ex.sql)

            # 2-way vote: if both agree → use that; else pick by confidence.
            # Here baseline_rec has no flat confidence — alt has it via parsed JSON.
            fp_base = fingerprint_rows(base_rows)
            fp_alt = fingerprint_rows(alt_rows)
            agree = fp_base == fp_alt
            if agree:
                vote_match = base_cmp.match  # equivalent to alt_cmp.match
                vote_source = "agree"
            else:
                # Disagreement — pick highest confidence. Baseline has no
                # flat confidence; default to picking alt if alt confidence
                # >= 0.7 else fall back to baseline. Real production would
                # use a 3rd voter to break ties.
                if alt.confidence >= 0.7:
                    vote_match = alt_cmp.match
                    vote_source = "alt-pick"
                else:
                    vote_match = base_cmp.match
                    vote_source = "base-fallback"

            if vote_match and not baseline_rec["match"]:
                voted_better += 1
            elif baseline_rec["match"] and not vote_match:
                voted_worse += 1
            else:
                voted_same += 1

            elapsed = (time.perf_counter() - t0) * 1000.0
            records.append(
                {
                    "question_id": qid,
                    "db_id": ex.db_id,
                    "difficulty": ex.difficulty,
                    "question": ex.question,
                    "gold_sql": ex.sql,
                    "baseline_pred": baseline_rec["pred_sql"],
                    "alt_pred": alt.sql,
                    "alt_confidence": alt.confidence,
                    "baseline_match": baseline_rec["match"],
                    "alt_match": alt_cmp.match,
                    "vote_match": vote_match,
                    "vote_source": vote_source,
                    "agree": agree,
                    "elapsed_ms": elapsed,
                }
            )
            print(
                f"[{i:3d}/{len(candidates)}] qid={qid} {ex.difficulty:11s} "
                f"base={baseline_rec['match']} alt={alt_cmp.match} "
                f"vote={vote_match} ({vote_source})",
                file=sys.stderr,
            )
        finally:
            engine.dispose()

    print(file=sys.stderr)
    print("=== voting summary ===", file=sys.stderr)
    print(f"  alt model: {args.provider_model}", file=sys.stderr)
    print(f"  cases processed: {len(records)}", file=sys.stderr)
    print(f"  vote BETTER than baseline: {voted_better}", file=sys.stderr)
    print(f"  vote WORSE  than baseline: {voted_worse}", file=sys.stderr)
    print(f"  vote SAME:                {voted_same}", file=sys.stderr)
    print(f"  groq tokens used: in={total_in_tokens} out={total_out_tokens}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "alt_model": args.provider_model,
                "summary": {
                    "voted_better": voted_better,
                    "voted_worse": voted_worse,
                    "voted_same": voted_same,
                    "groq_input_tokens": total_in_tokens,
                    "groq_output_tokens": total_out_tokens,
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
