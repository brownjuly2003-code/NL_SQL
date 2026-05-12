"""Failure taxonomy for an eval report.

Given a `G_*hybrid*.json` (or any report with the standard record schema), classify
every failing example into an actionable bucket so accuracy work can target the
biggest pile instead of guessing.

Buckets:
    exec_failed         — pred SQL crashed at runtime
    exec_timeout        — pred SQL hit statement_timeout
    empty_result        — pred returned 0 rows, gold has rows
    row_count_off       — both ran, row counts differ (missing/extra GROUP BY,
                          missing LIMIT, missing JOIN filter)
    projection_diff     — same row count, column shape differs (wrong SELECT list)
    filter_or_value     — same shape, values differ (wrong WHERE, wrong JOIN,
                          wrong aggregation expression)
    order_by_off        — gold has ORDER BY and gold[0] != pred[0]
    numeric_precision   — single-row scalar, off by <1e-3 rel or CAST flavour

Usage:
    uv run python scripts/error_taxonomy.py eval/reports/2026-05-11/G_*hybrid*.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_RE_ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)
_RE_GROUP_BY = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)
_RE_LIMIT = re.compile(r"\blimit\b", re.IGNORECASE)
_RE_AGG = re.compile(r"\b(sum|avg|count|min|max|cast)\s*\(", re.IGNORECASE)
_RE_CASE = re.compile(r"\bcase\s+when\b|\biif\s*\(", re.IGNORECASE)


def _classify(rec: dict[str, Any]) -> str:
    if rec.get("match"):
        return "match"

    ek = (rec.get("error_kind") or "").lower()
    if "timeout" in ek:
        return "exec_timeout"
    if ek in {"execution_failed", "validation_failed", "parse_failed"}:
        return "exec_failed"
    if ek == "empty_result":
        return "empty_result"

    gc = rec.get("gold_row_count") or 0
    pc = rec.get("pred_row_count") or 0
    gold = rec.get("gold_sql") or ""
    reason = (rec.get("comparison_reason") or "").lower()

    if gc != pc:
        return "row_count_off"

    if gc == pc == 1 and _RE_AGG.search(gold) and (_RE_CASE.search(gold) or "/ " in gold or "*100" in gold.replace(" ", "")):
        return "filter_or_value"

    if reason.startswith("ordered row"):
        if _RE_ORDER_BY.search(gold):
            return "order_by_off"
        return "filter_or_value"

    if "column" in reason or "projection" in reason or "shape" in reason:
        return "projection_diff"

    return "filter_or_value"


def _exemplars(records: list[dict[str, Any]], bucket: str, n: int = 3) -> list[dict[str, Any]]:
    items = [r for r in records if _classify(r) == bucket]
    return items[:n]


def summarise(report_path: Path) -> dict[str, Any]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    n = len(records)

    by_bucket: Counter[str] = Counter()
    by_diff_bucket: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        b = _classify(r)
        by_bucket[b] += 1
        by_diff_bucket[r.get("difficulty", "?")][b] += 1

    print(f"\n=== {report_path.name} (n={n}) ===")
    overall = data.get("overall", {})
    print(f"EA={overall.get('ea', 0):.3f}  first_pass={overall.get('first_pass_ea', 0):.3f}  "
          f"valid={overall.get('validity_rate', 0):.3f}  recall={overall.get('schema_recall_at_k', 0):.3f}")
    print(f"\n  bucket             n     %   lift_if_solved")
    print(f"  ----------------- ---  ----  --------------")
    matches = by_bucket.get("match", 0)
    for bucket, cnt in by_bucket.most_common():
        pct = 100.0 * cnt / n
        lift = 0.0 if bucket == "match" else 100.0 * cnt / n
        print(f"  {bucket:17s} {cnt:3d}  {pct:5.1f}%  +{lift:5.1f}pp")

    print(f"\n  by difficulty:")
    for diff in ("simple", "moderate", "challenging"):
        bd = by_diff_bucket.get(diff)
        if not bd:
            continue
        total = sum(bd.values())
        miss = total - bd.get("match", 0)
        if total:
            print(f"    {diff:12s} n={total:3d} miss={miss:3d}  " + ", ".join(
                f"{k}={v}" for k, v in bd.most_common() if k != "match"
            ))

    print(f"\n  top failure buckets — exemplars:")
    for bucket, _ in [(b, c) for b, c in by_bucket.most_common() if b != "match"][:4]:
        ex = _exemplars(records, bucket, n=2)
        print(f"\n  [{bucket}]")
        for r in ex:
            q = (r.get("question") or "").replace("\n", " ")[:120]
            print(f"    qid={r['question_id']} ({r['difficulty']}, {r['db_id']}): {q}")
            print(f"      gold: {(r.get('gold_sql') or '')[:140]}")
            print(f"      pred: {(r.get('pred_sql') or '')[:140]}")
            print(f"      reason: {r.get('comparison_reason') or r.get('error_kind') or 'n/a'}")

    return {"by_bucket": dict(by_bucket), "by_difficulty": {k: dict(v) for k, v in by_diff_bucket.items()}}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for path in sys.argv[1:]:
        summarise(Path(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
