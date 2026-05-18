"""One-shot audit: re-score every stored record under the fixed runner.

Reads a baseline/voting eval JSON, re-executes each `pred_sql` + `gold_sql`
through `_execute_gold` + `execute_readonly`, recomputes `match` via
`compare_results`, and reports every qid where the stored flag disagrees
with the fresh computation.

Use this to validate that the SQLAlchemy `:identifier` bind-bug fix
(see commit 8aa7544) did not leave residual false positives or false
negatives anywhere in the n=200 evaluation surface.

Example:
    uv run python scripts/audit_rescore.py \
        --report eval/reports/2026-05-18/v16-helallao-dac-reasoning.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nl_sql.db import DatabaseSpec
from nl_sql.db.connection import execute_readonly, sqlite_url_readonly
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _execute_gold


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/bird_mini_dev/MINIDEV/dev_databases"),
    )
    args = p.parse_args()

    data = json.loads(args.report.read_text(encoding="utf-8"))
    records = data["records"] if isinstance(data, dict) else data

    mismatches: list[dict[str, object]] = []
    for r in records:
        db_id = r.get("db_id")
        db_path = args.data_root / db_id / f"{db_id}.sqlite"
        spec = DatabaseSpec(id=db_id, dialect="sqlite", url=sqlite_url_readonly(db_path))
        engine = spec.make_engine()
        try:
            gold_rows, _ = _execute_gold(
                engine, r["gold_sql"], statement_timeout_ms=30_000, row_cap=10_000
            )
            pred_sql = r.get("pred_sql") or ""
            pred_rows: list = []
            if pred_sql.strip():
                try:
                    with execute_readonly(
                        engine, pred_sql, statement_timeout_ms=30_000, row_cap=10_000
                    ) as result:
                        pred_rows = list(result.rows)
                except Exception:
                    pred_rows = []
            cmp = compare_results(gold_rows, pred_rows, gold_sql=r["gold_sql"])
            true_match = bool(cmp.match)
            stored = bool(r.get("match"))
            if stored != true_match:
                mismatches.append(
                    {
                        "qid": r["question_id"],
                        "difficulty": r.get("difficulty"),
                        "db_id": db_id,
                        "stored_match": stored,
                        "true_match": true_match,
                        "gold_rows": len(gold_rows),
                        "pred_rows": len(pred_rows),
                        "reason": cmp.reason,
                    }
                )
        finally:
            engine.dispose()

    matched_stored = sum(1 for r in records if r.get("match"))
    matched_true = matched_stored + sum(
        1 if m["true_match"] else -1 for m in mismatches
    )
    print(f"Report: {args.report}")
    print(f"  records: {len(records)}")
    print(f"  matches stored: {matched_stored}")
    print(f"  matches true:   {matched_true}")
    print(f"  mismatches:     {len(mismatches)}")
    for m in mismatches:
        print(f"    qid={m['qid']:>5} {m['difficulty']:11s} stored={m['stored_match']} → true={m['true_match']} (gold={m['gold_rows']}, pred={m['pred_rows']}) reason={m['reason']!r}")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
