"""Qid-level acceptance harness for the narrow P3.F JOIN-path work.

This script checks a finished eval/voting report. It does not call providers,
does not run a broad residue sweep, and does not implement the JOIN linker.

Usage:
    uv run python scripts/p3f_acceptance.py \
        --report eval/reports/2026-05-22/v20-kimi-k2-thinking-merged.json
    uv run python scripts/p3f_acceptance.py --report <candidate>.json --require-pass
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

ColumnRef = tuple[str, str]


@dataclass(frozen=True)
class AcceptanceTarget:
    qid: int
    label: str
    required_columns: tuple[ColumnRef, ...]
    forbidden_columns: tuple[ColumnRef, ...] = ()


@dataclass(frozen=True)
class AcceptanceResult:
    qid: int
    label: str
    accepted: bool
    match: bool
    reasons: tuple[str, ...]
    pred_sql: str


TARGETS: tuple[AcceptanceTarget, ...] = (
    AcceptanceTarget(
        qid=1404,
        label="student_club expense type must come from event.type",
        required_columns=(("event", "type"),),
        forbidden_columns=(("expense", "expense_description"), ("expense", "type")),
    ),
    AcceptanceTarget(
        qid=207,
        label="toxicology double bond path must not shortcut through connected.bond_id",
        required_columns=(("connected", "atom_id"),),
        forbidden_columns=(("connected", "bond_id"),),
    ),
    AcceptanceTarget(
        qid=902,
        label="formula_1 driver track-number/standing must use driverStandings.position, not results.position",
        required_columns=(("driverstandings", "position"),),
        forbidden_columns=(("results", "position"), ("results", "positionorder")),
    ),
    AcceptanceTarget(
        qid=1531,
        label="debit_card_specializing 'top spending' must use yearmonth.Consumption subquery, not transactions_1k Price aggregation",
        required_columns=(("yearmonth", "consumption"),),
        forbidden_columns=(),
    ),
    AcceptanceTarget(
        qid=894,
        label="formula_1 'best lap time recorded' must include lapTimes.milliseconds as a SELECT column",
        required_columns=(("laptimes", "milliseconds"),),
        forbidden_columns=(),
    ),
    AcceptanceTarget(
        qid=1251,
        label="thrombosis_prediction 'IgG higher than normal' patient-count must restrict to patients in Examination",
        required_columns=(("examination", "id"),),
        forbidden_columns=(),
    ),
)


def evaluate_report(report: Mapping[str, Any]) -> list[AcceptanceResult]:
    records = _records_by_qid(report)
    missing = [target.qid for target in TARGETS if target.qid not in records]
    if missing:
        raise ValueError(f"missing target qids: {missing}")
    return [_evaluate_record(records[target.qid], target) for target in TARGETS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="return exit code 1 unless every P3.F target is accepted",
    )
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    try:
        results = evaluate_report(report)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3

    print(f"Report: {args.report}")
    for result in results:
        flag = "PASS" if result.accepted else "FAIL"
        print(f"{flag} qid={result.qid} match={result.match} - {result.label}")
        for reason in result.reasons:
            print(f"  - {reason}")

    if args.require_pass and any(not result.accepted for result in results):
        return 1
    return 0


def _evaluate_record(
    record: Mapping[str, Any],
    target: AcceptanceTarget,
) -> AcceptanceResult:
    pred_sql = str(record.get("pred_sql") or "")
    match = bool(record.get("match"))
    columns, parse_error = _qualified_columns(pred_sql)
    reasons: list[str] = []
    if not match:
        reasons.append("EA match is false")
    if parse_error:
        reasons.append(parse_error)
    for table, column in target.required_columns:
        if (table, column) not in columns:
            reasons.append(f"missing required column {table}.{column}")
    for table, column in target.forbidden_columns:
        if (table, column) in columns:
            reasons.append(f"forbidden column {table}.{column} is present")
    return AcceptanceResult(
        qid=target.qid,
        label=target.label,
        accepted=not reasons,
        match=match,
        reasons=tuple(reasons),
        pred_sql=pred_sql,
    )


def _records_by_qid(report: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    raw_records = report.get("records") or []
    records: dict[int, Mapping[str, Any]] = {}
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            continue
        qid = raw_record.get("question_id")
        if isinstance(qid, int):
            records[qid] = raw_record
    return records


def _qualified_columns(sql: str) -> tuple[set[ColumnRef], str | None]:
    if not sql.strip():
        return set(), None
    try:
        tree = parse_one(sql, read="sqlite")
    except ParseError as exc:
        return set(), f"SQL parse failed: {exc}"

    alias_to_table: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        table_name = _lower(table.name)
        if not table_name:
            continue
        alias_to_table[table_name] = table_name
        alias_to_table[_lower(table.alias_or_name)] = table_name

    columns: set[ColumnRef] = set()
    for column in tree.find_all(exp.Column):
        column_name = _lower(column.name)
        table_name = _lower(column.table)
        if not column_name:
            continue
        resolved_table = alias_to_table.get(table_name, table_name)
        columns.add((resolved_table, column_name))
    return columns, None


def _lower(value: str) -> str:
    return value.lower()


if __name__ == "__main__":
    raise SystemExit(main())
