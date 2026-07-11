"""Vote across provider runs by execution result — the reproducible voting layer.

The archive's headline numbers (85.5%, and the 94.0% built on top of it) came
from voting: run the same questions through several different models, then keep
the answer they agree on. That layer is frozen in `scripts/archive/` because it
scored itself with the unsafe comparator — it called `compare_results` directly,
which blesses a pred that crashed as a match whenever gold also returns no rows.

This is that idea, rebuilt on the safe primitives:

  * candidates come from finished eval reports (one per provider, same slice);
  * every candidate SQL is re-executed against the live database;
  * candidates cluster on `fingerprint_rows` — the execution result, not the SQL
    text, so the same answer spelled two ways votes together;
  * the largest cluster wins, ties break on report order (the strongest provider
    first);
  * the winner is scored with `safe_compare_pred`, which cannot bless a crash.

Diversity here comes from using *different models*, not from re-sampling one
model at a higher temperature — that was measured (config F) and it lost.

Usage:
    python scripts/ensemble_providers.py \
        eval/reports/2026-07-11/E_dense_fewshot_repair-evfirst.json \
        eval/reports/2026-07-11/E_dense_fewshot_repair-groq.json \
        --out eval/reports/2026-07-11/ensemble.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from nl_sql.db.registry import get_default_registry
from nl_sql.eval.metrics.execution_accuracy import safe_compare_pred
from nl_sql.eval.self_consistency import fingerprint_rows
from nl_sql.execution.guards import validate_sql

_ROW_CAP = 10_000


@dataclass(frozen=True, slots=True)
class Candidate:
    provider: str
    sql: str
    rank: int  # position of its report on the command line; lower = more trusted


@dataclass(frozen=True, slots=True)
class Executed:
    candidate: Candidate
    rows: list[tuple[Any, ...]] | None  # None = the SQL failed to execute


def _run(engine: Any, sql: str) -> list[tuple[Any, ...]] | None:
    """Execute one candidate. A failure is a vote for nothing, not an empty answer."""
    from nl_sql.db.connection import execute_readonly

    if not sql.strip():
        return None
    if not validate_sql(sql, "sqlite").ok:  # the guard the product runs behind
        return None
    try:
        with execute_readonly(engine, sql, row_cap=_ROW_CAP) as result:
            return list(result.rows)
    except (SQLAlchemyError, Exception):
        return None


def _vote(executed: list[Executed]) -> Executed | None:
    """Largest cluster of identical execution results; ties go to the better report.

    A candidate that failed to execute is dropped: it agrees with nothing. An
    empty result is a real answer and clusters normally — "no rows" is often
    correct in BIRD.
    """
    alive = [e for e in executed if e.rows is not None]
    if not alive:
        return None
    clusters: dict[str, list[Executed]] = defaultdict(list)
    for item in alive:
        clusters[fingerprint_rows(item.rows or [])].append(item)
    best = max(
        clusters.values(),
        key=lambda group: (len(group), -min(e.candidate.rank for e in group)),
    )
    return min(best, key=lambda e: e.candidate.rank)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="eval report JSONs, strongest first")
    parser.add_argument("--out", default="", help="write the merged report here")
    args = parser.parse_args(argv)

    reports = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
    names = [Path(p).stem for p in args.reports]
    print(f"[ensemble] {len(reports)} providers: {', '.join(names)}")

    # question_id -> candidates, in report order
    by_qid: dict[Any, list[Candidate]] = defaultdict(list)
    gold: dict[Any, dict[str, Any]] = {}
    for rank, (report, name) in enumerate(zip(reports, names, strict=True)):
        for rec in report["records"]:
            qid = rec["question_id"]
            by_qid[qid].append(Candidate(provider=name, sql=rec.get("pred_sql") or "", rank=rank))
            gold.setdefault(qid, rec)

    registry = get_default_registry()
    engines: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    matched = 0

    for i, (qid, candidates) in enumerate(sorted(by_qid.items(), key=lambda kv: str(kv[0])), 1):
        base = gold[qid]
        db_id = base["db_id"]
        if db_id not in engines:
            engines[db_id] = registry.get(db_id).make_engine()
        engine = engines[db_id]

        executed = [Executed(candidate=c, rows=_run(engine, c.sql)) for c in candidates]
        winner = _vote(executed)

        gold_rows = _run(engine, base["gold_sql"])
        if winner is None or gold_rows is None:
            comparison = safe_compare_pred(
                gold_rows or [],
                [],
                gold_sql=base["gold_sql"],
                pred_failed=winner is None,
                gold_failed=gold_rows is None,
            )
        else:
            comparison = safe_compare_pred(
                gold_rows,
                winner.rows or [],
                gold_sql=base["gold_sql"],
                pred_failed=False,
                gold_failed=False,
            )

        matched += int(comparison.match)
        agreement = sum(
            1
            for e in executed
            if e.rows is not None
            and winner is not None
            and fingerprint_rows(e.rows) == fingerprint_rows(winner.rows or [])
        )
        records.append(
            {
                **{k: base[k] for k in ("question_id", "db_id", "difficulty", "question")},
                "gold_sql": base["gold_sql"],
                "pred_sql": winner.candidate.sql if winner else "",
                "winning_provider": winner.candidate.provider if winner else None,
                "agreement": agreement,
                "candidates": len(candidates),
                "match": comparison.match,
                "comparison_reason": comparison.reason,
            }
        )
        if i % 25 == 0:
            print(f"  [{i:>3}/{len(by_qid)}] running EA {matched / i:.1%}")

    n = len(records)
    ea = matched / n if n else 0.0
    print(f"\n[ensemble] EA {ea:.1%} ({matched}/{n})")

    by_provider: dict[str, int] = defaultdict(int)
    for rec in records:
        if rec["winning_provider"]:
            by_provider[rec["winning_provider"]] += 1
    print("[ensemble] questions won per provider:")
    for name, count in sorted(by_provider.items(), key=lambda kv: -kv[1]):
        print(f"    {name:<50} {count}")

    unanimous = sum(1 for r in records if r["agreement"] == r["candidates"])
    print(f"[ensemble] all providers agreed on {unanimous}/{n} questions")

    if args.out:
        out = {
            "configuration": "ensemble+" + "+".join(names),
            "sql_model": " + ".join(names),
            "overall": {"n": n, "ea": round(ea, 4), "matched": matched},
            "records": records,
        }
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[json] {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
