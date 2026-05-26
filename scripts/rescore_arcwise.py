"""Re-score a v10-style BIRD eval report against Arcwise-Plat corrected gold.

Jin et al. (CIDR/VLDB 2026, arXiv:2601.08778) audited BIRD Mini-Dev and found
~52.8% questions have annotation errors. Their corrected artifacts
(`arcwise_plat_sql_only` = SQL-only fixes, `arcwise_plat_full` = SQL + question +
evidence + schema fixes) live at
https://github.com/uiuc-kang-lab/text_to_sql_benchmarks/blob/main/data/.

This script keeps our predictions unchanged and only swaps the gold SQL used
for execution-accuracy scoring. It writes a comparison report grouped into
buckets: same / gained (pred now matches corrected gold) / lost (pred matched
original gold but no longer matches corrected) per source variant.

Outputs:
- eval/reports/2026-05-17/arcwise_rescored.json (full per-record audit)
- stdout summary table

Usage:
    uv run python scripts/rescore_arcwise.py \
        --report eval/reports/2026-05-17/hybrid-vote-critique-selfcon-sonnet-fewshot5-groq4-mschema-v10.json \
        --sql-only data/arcwise_plat_sql_only.json \
        --full data/arcwise_plat_full.json \
        --out eval/reports/2026-05-17/arcwise_rescored.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from nl_sql.db.connection import execute_readonly
from nl_sql.db.registry import get_default_registry
from nl_sql.eval.metrics.execution_accuracy import safe_compare_pred
from nl_sql.eval.runner import _execute_gold_with_status


def _load_arcwise(path: Path) -> dict[int, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for entry in raw:
        qid = int(entry["question_id"])
        out[qid] = entry
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--sql-only", type=Path, required=True)
    p.add_argument("--full", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    arc_sql = _load_arcwise(args.sql_only)
    arc_full = _load_arcwise(args.full)

    registry = get_default_registry()
    records = report["records"]

    # Per-variant aggregates.
    variants = ("original", "sql_only", "full")
    matched: dict[str, int] = {v: 0 for v in variants}
    total_scored: dict[str, int] = {v: 0 for v in variants}
    per_diff: dict[str, dict[str, list[int]]] = {v: defaultdict(lambda: [0, 0]) for v in variants}
    # Per-qid transitions sql_only vs original, full vs original.
    transitions: dict[str, list[dict[str, Any]]] = {"gained": [], "lost": [], "changed_gold": []}

    per_record: list[dict[str, Any]] = []

    for i, rec in enumerate(records, 1):
        qid = rec["question_id"]
        db_id = rec["db_id"]
        difficulty = rec["difficulty"]
        pred_sql = rec.get("pred_sql") or ""
        orig_match = bool(rec.get("match"))

        spec = registry.get(f"bird_{db_id}")
        engine = spec.make_engine()
        out_entry = {
            "question_id": qid,
            "db_id": db_id,
            "difficulty": difficulty,
            "pred_sql": pred_sql,
            "original_match": orig_match,
        }
        try:
            # Execute pred once, reuse rows. Route pred through `execute_readonly`
            # directly (matches canonical `scripts/audit_rescore.py`): the
            # `_execute_gold` SQLAlchemyError fallback is intended only for
            # trusted BIRD gold SQL, not for model-generated pred SQL — using
            # it on pred can mask validator-style failures and yields
            # non-deterministic engine state across sequential records.
            pred_rows: list[tuple[Any, ...]] = []
            pred_failed = False
            if pred_sql.strip():
                try:
                    with execute_readonly(
                        engine, pred_sql, statement_timeout_ms=30_000, row_cap=10_000
                    ) as result:
                        pred_rows = list(result.rows)
                except Exception as exc:
                    out_entry["pred_exec_error"] = str(exc)
                    pred_failed = True
            else:
                pred_failed = True

            # Score against each variant.
            for variant, source in (
                ("original", rec.get("gold_sql") or ""),
                ("sql_only", arc_sql.get(qid, {}).get("SQL") or ""),
                ("full", arc_full.get(qid, {}).get("SQL") or ""),
            ):
                if not source:
                    continue
                gold_failed = False
                try:
                    gold_rows, _, gold_failed = _execute_gold_with_status(
                        engine, source, statement_timeout_ms=30_000, row_cap=10_000
                    )
                    if gold_failed:
                        out_entry[f"{variant}_gold_exec_error"] = (
                            "gold SQL crashed in both execute_readonly and raw-connection paths"
                        )
                except Exception as exc:
                    gold_rows = []
                    gold_failed = True
                    out_entry[f"{variant}_gold_exec_error"] = str(exc)
                cmp = safe_compare_pred(
                    gold_rows,
                    pred_rows,
                    gold_sql=source,
                    pred_failed=pred_failed,
                    gold_failed=gold_failed,
                )
                is_match = bool(cmp.match)
                out_entry[f"{variant}_match"] = is_match
                out_entry[f"{variant}_reason"] = cmp.reason
                out_entry[f"{variant}_gold_rows"] = len(gold_rows)
                total_scored[variant] += 1
                matched[variant] += int(is_match)
                per_diff[variant][difficulty][1] += 1
                per_diff[variant][difficulty][0] += int(is_match)

            # Transitions vs sql_only and vs full.
            # Use the FRESHLY-re-executed original-variant match (written at
            # `out_entry["original_match"]` by the variant loop above) rather
            # than the stale `orig_match` snapshot from the input JSON — the
            # whole point of rescore is to apply current scoring semantics, so
            # mixing in stored EA bits would produce a hybrid that doesn't
            # match either run cleanly (Codex audit 2026-05-25 #7). On the
            # current canonical v22-v30 baselines the two values agree on
            # every record, so this is a future-proofing change; no
            # observable difference in committed reports.
            fresh_orig = bool(out_entry.get("original_match", orig_match))
            for variant in ("sql_only", "full"):
                v_match = out_entry.get(f"{variant}_match")
                if v_match is None:
                    continue
                src = arc_sql if variant == "sql_only" else arc_full
                arc_entry = src.get(qid) or {}
                gold_changed = bool(
                    arc_entry.get("SQL", "").strip() != (rec.get("gold_sql") or "").strip()
                )
                if gold_changed:
                    out_entry[f"{variant}_gold_changed"] = True
                if fresh_orig and not v_match:
                    transitions["lost"].append(
                        {"qid": qid, "variant": variant, "difficulty": difficulty}
                    )
                elif (not fresh_orig) and v_match:
                    transitions["gained"].append(
                        {"qid": qid, "variant": variant, "difficulty": difficulty}
                    )
        finally:
            engine.dispose()
        per_record.append(out_entry)
        if i % 25 == 0:
            print(f"[{i:3d}/{len(records)}] processed", file=sys.stderr)

    # Summary.
    print("\n=== Arcwise rescoring summary ===", file=sys.stderr)
    for variant in variants:
        total = total_scored[variant]
        count = matched[variant]
        pct = (count / total * 100) if total else 0.0
        print(f"  {variant:10s}: {count}/{total} = {pct:.2f}%", file=sys.stderr)
    print("\n=== Per-tier ===", file=sys.stderr)
    for variant in variants:
        line = f"  {variant:10s}: "
        for diff in ("simple", "moderate", "challenging"):
            mt, tot = per_diff[variant][diff]
            pct = (mt / tot * 100) if tot else 0.0
            line += f"{diff[:4]}={mt}/{tot}({pct:.1f}%) "
        print(line, file=sys.stderr)
    print("\n=== Transitions (vs original gold) ===", file=sys.stderr)
    print(f"  gained (sql_only): {len(transitions['gained'])}", file=sys.stderr)
    print(
        f"  lost (sql_only): {sum(1 for t in transitions['lost'] if t['variant'] == 'sql_only')}",
        file=sys.stderr,
    )
    print(
        f"  gained (full): {sum(1 for t in transitions['gained'] if t['variant'] == 'full')}",
        file=sys.stderr,
    )
    print(
        f"  lost (full): {sum(1 for t in transitions['lost'] if t['variant'] == 'full')}",
        file=sys.stderr,
    )

    out_payload = {
        "source_report": str(args.report),
        "summary": {v: {"matched": matched[v], "total": total_scored[v]} for v in variants},
        "per_difficulty": {
            v: {
                d: {"matched": per_diff[v][d][0], "total": per_diff[v][d][1]}
                for d in ("simple", "moderate", "challenging")
            }
            for v in variants
        },
        "transitions": transitions,
        "records": per_record,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_payload, indent=2, default=str), encoding="utf-8")
    print(f"\n[info] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
