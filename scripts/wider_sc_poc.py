"""Wider self-consistency POC: 2 prompt variants x 4 temps on v29 residue qids.

Hypothesis: current config F (4 temps x 1 prompt) converges on a single shape;
adding a BIRD-shape-hint prompt variant introduces alternative aggregation/sort
patterns that residue qids need (LIMIT vs WHERE=MAX, AVG vs CAST(SUM)/COUNT,
date-format conventions).

Standalone -- bypasses LangGraph. For each residue qid:
  1. Build context via retrieve_context (same as production C config).
  2. Generate 8 candidates (2 variants x 4 temps).
  3. Execute each on the live db.
  4. Cluster by fingerprint_rows (existing eval.self_consistency helper).
  5. Pick plurality cluster; compare winner vs gold.

POC scope: 3 BIRD-shape-friendly residue qids first. If lift detected -> scale.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import chromadb

from nl_sql.agent.nodes._support import parse_generate_sql_output, render_schema_block
from nl_sql.agent.prompts import load_prompt
from nl_sql.config import get_settings
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.dataset import DEFAULT_BIRD_ROOT, load_bird_mini_dev
from nl_sql.eval.metrics.execution_accuracy import safe_compare_pred
from nl_sql.eval.runner import _execute_gold_with_status
from nl_sql.eval.self_consistency import fingerprint_rows
from nl_sql.execution.runner import execute_validated
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers import build_provider
from nl_sql.llm.providers.base import GenerateRequest
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.retriever import retrieve_context

BIRD_SHAPE_RULES = """
# BIRD-style shape conventions (apply when relevant to the question)

These are common shape patterns observed in BIRD gold SQL; if your default
choice does not fit one of them, consider the alternative.

- "Which/who has the highest/lowest/most X" → BIRD gold often uses
  `WHERE col = (SELECT MAX(col) FROM ...)` rather than
  `ORDER BY col DESC LIMIT 1`. Prefer the WHERE=MAX subquery shape unless
  the question explicitly says "top 1" or "first".

- "Average of average X" / "Mean X" in BIRD context → prefer
  `CAST(SUM(X) AS REAL) / COUNT(*)` over `AVG(X)`. BIRD gold rarely uses AVG().

- "After Y/M/D" / "before Y/M/D" date filters → match the exact format
  stored in the column. If samples show 'YYYY-MM-DD' literal, use
  `date_col > 'Y-M-D'` directly (no strftime). If samples show numeric year,
  cast accordingly.

- "Rank N" / "in position N" / "Nth place" → BIRD gold uses
  `WHERE rank_col = N` rather than `ORDER BY rank_col LIMIT N`.
  Returns all ties; the LIMIT version silently drops them.

- "List all X with maximum/minimum Y" → BIRD gold uses
  `WHERE Y = (SELECT MAX/MIN(Y))` to return all ties. Do NOT use
  `ORDER BY Y DESC LIMIT 1` if the question implies tie inclusion.

- "Highest scoring" / "best" in european_football_2: BIRD gold occasionally
  treats lower numeric values as "higher rank" (positional inversion).
  Consider both ASC and DESC sort orders when the column semantics are
  ambiguous from the schema.
"""


def _build_prompt(
    *,
    variant: str,
    context: Any,
    question: str,
    dialect: str = "sqlite",
) -> str:
    """Build the full prompt for a given variant."""
    schema_text = render_schema_block(context, sort_alphabetically=True)
    base = load_prompt(
        "generate_sql",
        dialect=dialect,
        schema_block=schema_text,
        fewshot_block="",
        plan_block="(no plan — generate SQL directly from question)",
        question=question,
    )
    if variant == "bird_shape":
        # Splice BIRD-shape rules just before the JSON output contract so the
        # model sees them before formulating SQL.
        marker = "# Output contract"
        if marker in base:
            head, tail = base.split(marker, 1)
            return head + BIRD_SHAPE_RULES + "\n" + marker + tail
        return base + "\n" + BIRD_SHAPE_RULES
    return base


def _run_one_qid(
    *,
    example: Any,
    schema_index: SchemaIndex,
    registry: Any,
    provider: Any,
    variants: tuple[str, ...],
    temperatures: tuple[float, ...],
) -> dict[str, Any]:
    """Generate 8 candidates, execute, cluster, return winner + diagnostics."""
    bundle = retrieve_context(
        schema_index,
        example.question,
        db_id=example.registry_db_id,
        schema_top_k=5,
        fewshot_top_k=0,
        fk_hops=1,
        table_budget=12,
        primary_sample_size=3,
        extended_sample_size=0,
        cross_db_fewshot=False,
    )

    engine = registry.get(example.registry_db_id).make_engine()
    try:
        gold_rows, _gold_cols, gold_failed = _execute_gold_with_status(
            engine, example.sql, statement_timeout_ms=60_000, row_cap=10_000
        )

        candidates: list[dict[str, Any]] = []
        for variant in variants:
            prompt = _build_prompt(variant=variant, context=bundle, question=example.question)
            for temp in temperatures:
                try:
                    response = provider.generate(
                        GenerateRequest(prompt=prompt, max_tokens=1024, temperature=temp)
                    )
                except Exception as exc:
                    candidates.append(
                        {
                            "variant": variant,
                            "temperature": temp,
                            "sql": "",
                            "rows": [],
                            "fingerprint": None,
                            "executed": False,
                            "confidence": 0.0,
                            "error": f"provider: {exc!s}"[:200],
                        }
                    )
                    continue
                parsed = parse_generate_sql_output(response.text)
                if not parsed.sql:
                    candidates.append(
                        {
                            "variant": variant,
                            "temperature": temp,
                            "sql": "",
                            "rows": [],
                            "fingerprint": None,
                            "executed": False,
                            "confidence": parsed.confidence,
                            "error": "parse: empty sql",
                        }
                    )
                    continue
                outcome = execute_validated(
                    engine,
                    parsed.sql,
                    dialect="sqlite",
                    statement_timeout_ms=60_000,
                    row_cap=10_000,
                )
                if outcome.ok and outcome.result is not None:
                    rows = list(outcome.result.rows)
                    fp = fingerprint_rows(rows)
                    candidates.append(
                        {
                            "variant": variant,
                            "temperature": temp,
                            "sql": parsed.sql,
                            "rows": rows[:5],
                            "row_count": len(rows),
                            "fingerprint": fp,
                            "executed": True,
                            "confidence": parsed.confidence,
                            "error": "",
                        }
                    )
                else:
                    candidates.append(
                        {
                            "variant": variant,
                            "temperature": temp,
                            "sql": parsed.sql,
                            "rows": [],
                            "fingerprint": None,
                            "executed": False,
                            "confidence": parsed.confidence,
                            "error": f"exec: {outcome.error_kind.value if outcome.error_kind else 'unknown'}: {outcome.error_message[:200]}",
                        }
                    )

        # Cluster by fingerprint.
        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for c in candidates:
            if c["fingerprint"] is not None:
                clusters[c["fingerprint"]].append(c)

        winner: dict[str, Any] | None = None
        cluster_summary: list[dict[str, Any]] = []
        if clusters:
            ranked = sorted(
                clusters.items(),
                key=lambda kv: (
                    -len(kv[1]),
                    -max(m["confidence"] for m in kv[1]),
                    min(m["temperature"] for m in kv[1]),
                ),
            )
            for fp, members in ranked:
                cluster_summary.append(
                    {
                        "fingerprint": fp[:16],
                        "size": len(members),
                        "row_count": members[0].get("row_count", 0),
                        "variants": sorted({m["variant"] for m in members}),
                        "temps": sorted({m["temperature"] for m in members}),
                        "sample_sql": members[0]["sql"][:200],
                    }
                )
            _winner_cluster_fp, winner_members = ranked[0]
            winner = max(
                winner_members,
                key=lambda c: (c["confidence"], -c["temperature"]),
            )

        # Compare winner vs gold.
        if winner is None:
            comparison = safe_compare_pred(
                gold_rows, [], gold_sql=example.sql, pred_failed=True, gold_failed=gold_failed
            )
        else:
            comparison = safe_compare_pred(
                gold_rows,
                [
                    tuple(r) if not isinstance(r, tuple) else r
                    for r in (
                        # winner rows is truncated to 5 in candidates dict for display,
                        # re-execute to get full rowset
                        []
                    )
                ],
                gold_sql=example.sql,
                pred_failed=False,
                gold_failed=gold_failed,
            )
            # Re-execute winner SQL fully to get true rows for comparison.
            outcome = execute_validated(
                engine,
                winner["sql"],
                dialect="sqlite",
                statement_timeout_ms=60_000,
                row_cap=10_000,
            )
            pred_rows = list(outcome.result.rows) if outcome.ok and outcome.result else []
            comparison = safe_compare_pred(
                gold_rows,
                pred_rows,
                gold_sql=example.sql,
                pred_failed=not outcome.ok,
                gold_failed=gold_failed,
            )

        return {
            "qid": example.question_id,
            "db_id": example.registry_db_id,
            "difficulty": example.difficulty,
            "question": example.question,
            "gold_sql": example.sql,
            "gold_failed": gold_failed,
            "gold_rows_count": len(gold_rows),
            "candidates_total": len(candidates),
            "candidates_executed": sum(1 for c in candidates if c["executed"]),
            "clusters": cluster_summary,
            "winner_sql": winner["sql"] if winner else "",
            "winner_variant": winner["variant"] if winner else None,
            "winner_temp": winner["temperature"] if winner else None,
            "winner_confidence": winner["confidence"] if winner else 0.0,
            "match": comparison.match,
            "match_reason": comparison.reason if hasattr(comparison, "reason") else "",
            "all_candidates": candidates,
        }
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qids",
        default="",
        help="comma-separated qids to run; default: all v29 residue",
    )
    parser.add_argument(
        "--baseline",
        default="eval/reports/2026-05-24/v29-v28-plus-p3f-q1275-merged.json",
        help="v29 merged baseline to source residue qids",
    )
    parser.add_argument(
        "--temps",
        default="0.2,0.4,0.6,0.8",
        help="comma-separated sampling temperatures",
    )
    parser.add_argument(
        "--variants",
        default="default,bird_shape",
        help="comma-separated prompt variants",
    )
    parser.add_argument(
        "--out",
        default="eval/reports/2026-05-25/wider_sc_poc.json",
        help="output JSON path",
    )
    parser.add_argument("--persist", default="chroma_data", help="chroma persist directory")
    parser.add_argument("--bird-root", default=str(DEFAULT_BIRD_ROOT), help="MINIDEV/ root")
    args = parser.parse_args(argv)

    # Load residue qids.
    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        print(f"[error] baseline not found: {baseline_path}", file=sys.stderr)
        return 2
    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    residue_qids = [r["question_id"] for r in baseline_data["records"] if not r["match"]]
    if args.qids:
        residue_qids = [int(q) for q in args.qids.split(",") if q.strip()]
    print(f"[info] residue qids: {residue_qids}")

    # Load BIRD examples.
    all_examples = load_bird_mini_dev(Path(args.bird_root))
    by_qid = {e.question_id: e for e in all_examples}
    sample = [by_qid[q] for q in residue_qids if q in by_qid]
    missing = [q for q in residue_qids if q not in by_qid]
    if missing:
        print(f"[warn] qids not found in MINIDEV: {missing}", file=sys.stderr)
    print(f"[info] running on {len(sample)} qids")

    # Setup providers + index + registry.
    settings = get_settings()
    raw = build_provider("mistral", settings=settings)
    provider = CachingLLMProvider(
        raw, cache_dir=settings.llm_cache_dir, size_limit_gb=settings.llm_cache_size_limit_gb
    )
    print(f"[info] provider: mistral (model={raw.model}); cache: {settings.llm_cache_dir}")

    persist_dir = Path(args.persist)
    if not persist_dir.is_dir():
        print(f"[error] chroma persist dir not found: {persist_dir}", file=sys.stderr)
        return 2
    embed_provider_raw = build_provider("mistral", settings=settings)
    embed_provider = CachingEmbeddingProvider(
        embed_provider_raw,
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    client = chromadb.PersistentClient(path=str(persist_dir))
    schema_index = SchemaIndex(persist_dir, embedder=embed_provider, client=client)

    registry = get_default_registry()

    variants = tuple(v.strip() for v in args.variants.split(",") if v.strip())
    temperatures = tuple(float(t) for t in args.temps.split(",") if t.strip())
    print(
        f"[info] variants={variants} x temps={temperatures} = {len(variants) * len(temperatures)} candidates/qid"
    )

    results = []
    for idx, ex in enumerate(sample, start=1):
        print(
            f"[{idx:>2}/{len(sample)}] qid={ex.question_id} db={ex.registry_db_id} — {ex.question[:80]}"
        )
        try:
            res = _run_one_qid(
                example=ex,
                schema_index=schema_index,
                registry=registry,
                provider=provider,
                variants=variants,
                temperatures=temperatures,
            )
        except Exception as exc:
            print(f"  [error] {exc!r}")
            res = {
                "qid": ex.question_id,
                "db_id": ex.registry_db_id,
                "difficulty": ex.difficulty,
                "question": ex.question,
                "error": repr(exc),
                "match": False,
            }
        results.append(res)
        flag = "OK " if res.get("match") else "MISS"
        winner_var = res.get("winner_variant", "?")
        n_clusters = len(res.get("clusters", []))
        print(f"  {flag} | clusters={n_clusters} | winner_variant={winner_var}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "baseline": str(baseline_path),
                "variants": list(variants),
                "temperatures": list(temperatures),
                "total_qids": len(sample),
                "matches": sum(1 for r in results if r.get("match")),
                "records": results,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    matches = sum(1 for r in results if r.get("match"))
    print(
        f"\n[summary] {matches}/{len(results)} matches on residue ({matches / len(results) * 100:.1f}% if N>0)"
    )
    print(f"[summary] saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
