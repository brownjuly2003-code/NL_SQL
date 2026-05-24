"""Archive sweep: scan eval/reports/**/*.json for stale pred_sql that match
gold under the *current* corrected runner, for any qid currently missing in a
baseline report.

Use this after a runner-level fix (e.g. the day-5 bind-bug fix in
`db/connection.py`) or a scoring-methodology change (e.g. Counter → set in
`compare_results`): pred_sqls that were written long ago may have become
correct because the gold side stopped silently dropping rows or because the
matcher is no longer over-strict. Each rescue is a *re-verification*, not a
fresh model call — strictly $0 budget and offline.

Audit discipline: every candidate is re-executed live; the script never trusts
a stored `match` flag from the source report. Audit it afterwards via
`scripts/audit_rescore.py`.

Example:
    uv run python scripts/archive_sweep.py \
        --baseline eval/reports/2026-05-23/v24-v23-plus-archive-rescore-959-merged.json \
        --out eval/reports/2026-05-23/archive-sweep-v24-candidates.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from nl_sql.db import DatabaseSpec
from nl_sql.db.connection import execute_readonly, sqlite_url_readonly
from nl_sql.eval.metrics.execution_accuracy import compare_results
from nl_sql.eval.runner import _execute_gold


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument(
        "--reports-root", type=Path, default=Path("eval/reports")
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/bird_mini_dev/MINIDEV/dev_databases"),
    )
    p.add_argument(
        "--only-qids",
        type=str,
        default=None,
        help="Optional comma-separated qids to restrict sweep to.",
    )
    args = p.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    misses = [r for r in baseline["records"] if not r.get("match")]
    if args.only_qids:
        wanted = {int(x.strip()) for x in args.only_qids.split(",") if x.strip()}
        misses = [r for r in misses if r.get("question_id") in wanted]
    miss_index = {r["question_id"]: r for r in misses}
    print(f"baseline: {args.baseline}")
    print(f"  misses: {len(misses)} (qids: {sorted(miss_index)})")

    candidates: dict[int, set[str]] = {q: set() for q in miss_index}
    for rp in glob.glob(str(args.reports_root / "**" / "*.json"), recursive=True):
        rp_path = Path(rp)
        if rp_path.resolve() == args.baseline.resolve():
            continue
        try:
            d = json.loads(rp_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        recs = d.get("records", []) if isinstance(d, dict) else []
        for r in recs:
            if not isinstance(r, dict):
                continue
            qid_raw = r.get("question_id") or r.get("qid")
            if not isinstance(qid_raw, int) or qid_raw not in miss_index:
                continue
            qid = qid_raw
            for key in ("pred_sql", "alt_pred"):
                pred = r.get(key) or ""
                if isinstance(pred, str) and pred.strip():
                    candidates[qid].add(pred.strip())

    total_cands = sum(len(v) for v in candidates.values())
    print(f"  unique candidate pred_sqls: {total_cands}")

    rescues: list[dict[str, Any]] = []
    examined: list[dict[str, Any]] = []
    for qid in sorted(miss_index):
        miss = miss_index[qid]
        db_id = miss["db_id"]
        gold_sql = miss["gold_sql"]
        db_path = args.data_root / db_id / f"{db_id}.sqlite"
        spec = DatabaseSpec(id=db_id, dialect="sqlite", url=sqlite_url_readonly(db_path))
        engine = spec.make_engine()
        try:
            try:
                gold_rows, _ = _execute_gold(
                    engine, gold_sql, statement_timeout_ms=30_000, row_cap=10_000
                )
            except Exception as exc:
                print(f"  qid={qid}: gold failed: {exc!r}")
                gold_rows = []
            found = False
            for pred in sorted(candidates[qid]):
                try:
                    with execute_readonly(
                        engine, pred, statement_timeout_ms=30_000, row_cap=10_000
                    ) as result:
                        pred_rows = list(result.rows)
                except Exception:
                    pred_rows = []
                    continue
                cmp = compare_results(gold_rows, pred_rows, gold_sql=gold_sql)
                if cmp.match:
                    rescues.append(
                        {
                            "question_id": qid,
                            "difficulty": miss.get("difficulty"),
                            "db_id": db_id,
                            "alt_pred": pred,
                            "alt_match": True,
                            "alt_rows": len(pred_rows),
                            "gold_rows": len(gold_rows),
                            "baseline_match": False,
                        }
                    )
                    print(
                        f"  qid={qid} {miss.get('difficulty'):>11} db={db_id}: RESCUE "
                        f"(alt_rows={len(pred_rows)}, gold_rows={len(gold_rows)})"
                    )
                    found = True
                    break
            examined.append(
                {
                    "question_id": qid,
                    "difficulty": miss.get("difficulty"),
                    "db_id": db_id,
                    "candidates": len(candidates[qid]),
                    "rescued": found,
                }
            )
            if not found:
                print(
                    f"  qid={qid} {miss.get('difficulty'):>11} db={db_id}: no archive rescue "
                    f"({len(candidates[qid])} cand)"
                )
        finally:
            engine.dispose()

    out = {
        "alt_model": "archive-sweep",
        "baseline": str(args.baseline).replace("\\", "/"),
        "summary": {
            "voted_better": len(rescues),
            "voted_worse": 0,
            "voted_same": 0,
            "examined_qids": len(miss_index),
            "total_candidates": total_cands,
        },
        "examined": examined,
        "records": rescues,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote: {args.out}")
    print(f"  rescues: {len(rescues)} / {len(miss_index)} misses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
