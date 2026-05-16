"""Execution-fingerprint ensemble voting over existing eval reports."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import fields, replace
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import Engine

from nl_sql.agent.graph import PipelineRunResult
from nl_sql.db.registry import DatabaseRegistry, get_default_registry
from nl_sql.eval.metrics.execution_accuracy import ResultComparison, compare_results
from nl_sql.eval.report import write_html_report, write_json_report
from nl_sql.eval.runner import (
    Configuration,
    EvalRecord,
    EvalRun,
    EvalSummary,
    _execute_gold,
    _summarise,
    _to_dialect,
)
from nl_sql.eval.self_consistency import Candidate, fingerprint_rows, vote
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.runner import ExecutionOutcome, execute_validated

STATEMENT_TIMEOUT_MS = 30_000
ROW_CAP = 10_000

type FallbackMode = Literal["first", "highest-confidence"]
type RecordMeta = dict[str, Any]
type ReportMember = tuple[int, EvalRecord, RecordMeta, ExecutionOutcome, str]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-quorum", type=int, default=2)
    parser.add_argument(
        "--fallback-on-no-quorum",
        choices=["first", "highest-confidence"],
        default="first",
    )
    args = parser.parse_args(argv)

    if len(args.reports) < 2:
        parser.error("--reports requires at least two report files")
    if args.require_quorum < 1:
        parser.error("--require-quorum must be >= 1")

    runs: list[EvalRun] = []
    metadata: list[dict[int, RecordMeta]] = []
    for path in args.reports:
        run, meta = _load_report(path)
        runs.append(run)
        metadata.append(meta)

    ensemble, quorum_count, fallback_count = ensemble_runs(
        runs,
        metadata,
        registry=get_default_registry(),
        require_quorum=args.require_quorum,
        fallback_on_no_quorum=cast(FallbackMode, args.fallback_on_no_quorum),
    )
    _write_reports(ensemble, args.out)

    total = ensemble.overall.n
    quorum_pct = (quorum_count / total * 100.0) if total else 0.0
    fallback_pct = (fallback_count / total * 100.0) if total else 0.0
    print(
        f"ensemble n={total} EA={ensemble.overall.ea * 100:.1f}%, "
        f"quorum={quorum_pct:.1f}%, fallback={fallback_pct:.1f}%"
    )
    return 0


def ensemble_runs(
    runs: Sequence[EvalRun],
    metadata: Sequence[dict[int, RecordMeta]],
    *,
    registry: DatabaseRegistry,
    require_quorum: int,
    fallback_on_no_quorum: FallbackMode,
) -> tuple[EvalRun, int, int]:
    if len(runs) != len(metadata):
        raise ValueError("runs and metadata must have the same length")
    if not runs:
        raise ValueError("at least one report is required")

    indices = [{record.question_id: record for record in run.records} for run in runs]
    common_qids = set(indices[0])
    for index in indices[1:]:
        common_qids &= set(index)
    ordered_qids = [
        record.question_id for record in runs[0].records if record.question_id in common_qids
    ]

    engines: dict[str, Engine] = {}
    merged: list[EvalRecord] = []
    quorum_count = 0
    fallback_count = 0
    try:
        for qid in ordered_qids:
            members = [
                _execute_member(
                    report_idx,
                    indices[report_idx][qid],
                    metadata[report_idx].get(qid, {}),
                    runs[report_idx].sql_model,
                    registry=registry,
                    engines=engines,
                )
                for report_idx in range(len(runs))
            ]
            winner, used_quorum = _choose_winner(
                members,
                require_quorum=require_quorum,
                fallback_on_no_quorum=fallback_on_no_quorum,
            )
            if used_quorum:
                quorum_count += 1
            else:
                fallback_count += 1
            merged.append(_score_winner(winner, registry=registry, engines=engines))
    finally:
        for engine in engines.values():
            engine.dispose()

    sql_models = sorted({run.sql_model for run in runs})
    return (
        _summarise(
            configuration=runs[0].configuration,
            sql_model=" + ".join(sql_models),
            records=merged,
        ),
        quorum_count,
        fallback_count,
    )


def _execute_member(
    report_idx: int,
    record: EvalRecord,
    meta: RecordMeta,
    report_model: str,
    *,
    registry: DatabaseRegistry,
    engines: dict[str, Engine],
) -> ReportMember:
    engine = _engine_for_record(record, registry=registry, engines=engines)
    outcome = execute_validated(
        engine,
        record.pred_sql,
        dialect=_to_dialect(record.dialect),
        statement_timeout_ms=STATEMENT_TIMEOUT_MS,
        row_cap=ROW_CAP,
    )
    return (report_idx, record, meta, outcome, report_model)


def _choose_winner(
    members: Sequence[ReportMember],
    *,
    require_quorum: int,
    fallback_on_no_quorum: FallbackMode,
) -> tuple[ReportMember, bool]:
    clusters: dict[str, list[ReportMember]] = defaultdict(list)
    for member in members:
        outcome = member[3]
        if outcome.result is None:
            continue
        if outcome.error_kind in (
            ExecutionErrorKind.INVALID_SQL,
            ExecutionErrorKind.EXECUTION_FAILED,
        ):
            continue
        clusters[fingerprint_rows(outcome.result.rows)].append(member)

    if clusters:
        best_cluster = _best_cluster(list(clusters.values()))
        if len(best_cluster) >= require_quorum:
            return _pick_member_from_cluster(best_cluster), True

    return _fallback_member(members, fallback_on_no_quorum), False


def _best_cluster(clusters: Sequence[list[ReportMember]]) -> list[ReportMember]:
    best = clusters[0]
    for cluster in clusters[1:]:
        if len(cluster) > len(best):
            best = cluster
            continue
        if len(cluster) < len(best):
            continue
        cluster_conf = _max_confidence(cluster)
        best_conf = _max_confidence(best)
        if cluster_conf is None and best_conf is None:
            continue
        if cluster_conf is not None and (best_conf is None or cluster_conf > best_conf):
            best = cluster
            continue
        if cluster_conf == best_conf and _cluster_model_name(cluster) < _cluster_model_name(best):
            best = cluster
    return best


def _pick_member_from_cluster(cluster: Sequence[ReportMember]) -> ReportMember:
    if _max_confidence(cluster) is None:
        return cluster[0]

    ordered = sorted(
        enumerate(cluster),
        key=lambda item: (_model_name(item[1]), item[1][0]),
    )
    temperature_by_pos = {pos: float(rank) for rank, (pos, _) in enumerate(ordered)}
    candidates = [
        Candidate(
            result=_pipeline_result_for_member(member),
            temperature=temperature_by_pos[pos],
        )
        for pos, member in enumerate(cluster)
    ]
    winner = vote(candidates)
    for pos, candidate in enumerate(candidates):
        if candidate is winner:
            return cluster[pos]
    return cluster[0]


def _fallback_member(
    members: Sequence[ReportMember],
    fallback_on_no_quorum: FallbackMode,
) -> ReportMember:
    if fallback_on_no_quorum == "first":
        return members[0]

    if all(_confidence(member) is None for member in members):
        return members[0]
    return min(
        members,
        key=_fallback_sort_key,
    )


def _fallback_sort_key(member: ReportMember) -> tuple[float, str, int]:
    confidence = _confidence(member)
    return (-(confidence if confidence is not None else -1.0), _model_name(member), member[0])


def _score_winner(
    member: ReportMember,
    *,
    registry: DatabaseRegistry,
    engines: dict[str, Engine],
) -> EvalRecord:
    _, record, _, outcome, _ = member
    engine = _engine_for_record(record, registry=registry, engines=engines)
    gold_rows, _ = _execute_gold(
        engine,
        record.gold_sql,
        statement_timeout_ms=STATEMENT_TIMEOUT_MS,
        row_cap=ROW_CAP,
    )
    if outcome.result is None:
        comparison = ResultComparison(
            match=False,
            reason=(
                f"pred failed: {outcome.error_kind.value}"
                if outcome.error_kind
                else "pred failed: unknown"
            ),
            gold_rows=len(gold_rows),
            pred_rows=0,
        )
    else:
        comparison = compare_results(gold_rows, outcome.result.rows, gold_sql=record.gold_sql)

    return replace(
        record,
        match=comparison.match,
        error_kind=outcome.error_kind.value if outcome.error_kind else None,
        error_message=outcome.error_message,
        pred_row_count=comparison.pred_rows,
        gold_row_count=comparison.gold_rows,
        comparison_reason=comparison.reason,
    )


def _pipeline_result_for_member(member: ReportMember) -> PipelineRunResult:
    _, record, _, outcome, _ = member
    confidence = _confidence(member) or 0.0
    return PipelineRunResult(
        question=record.question,
        db_id=record.db_id,
        sql=record.pred_sql,
        rationale="",
        confidence=confidence,
        outcome=outcome,
        output_format=None,
        caption="",
        error_kind=outcome.error_kind,
        error_message=outcome.error_message,
        repair_attempted=record.repair_attempted,
        trace=[
            {
                "node": "generate_sql",
                "model": _model_name(member),
                "confidence": confidence,
            }
        ],
    )


def _engine_for_record(
    record: EvalRecord,
    *,
    registry: DatabaseRegistry,
    engines: dict[str, Engine],
) -> Engine:
    if record.db_id not in engines:
        try:
            spec = registry.get(record.db_id)
        except KeyError:
            spec = registry.get(f"bird_{record.db_id}")
        engines[record.db_id] = spec.make_engine()
    return engines[record.db_id]


def _max_confidence(members: Sequence[ReportMember]) -> float | None:
    values = [_confidence(member) for member in members]
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _confidence(member: ReportMember) -> float | None:
    value = member[2].get("confidence")
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _cluster_model_name(members: Sequence[ReportMember]) -> str:
    confidence = _max_confidence(members)
    if confidence is None:
        return _model_name(members[0])
    return min(_model_name(member) for member in members if _confidence(member) == confidence)


def _model_name(member: ReportMember) -> str:
    raw = member[2].get("model")
    if not isinstance(raw, str) or not raw:
        raw = member[2].get("sql_model")
    if isinstance(raw, str) and raw:
        return raw
    return member[4]


def _load_report(path: Path) -> tuple[EvalRun, dict[int, RecordMeta]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a JSON object")
    payload = cast(dict[str, Any], raw)

    records_raw = payload.get("records")
    if not isinstance(records_raw, list):
        raise ValueError(f"{path} does not contain a records list")

    record_fields = {field.name for field in fields(EvalRecord)}
    records: list[EvalRecord] = []
    metadata: dict[int, RecordMeta] = {}
    for item in records_raw:
        if not isinstance(item, dict):
            raise ValueError(f"{path} contains a non-object record")
        record_payload = cast(dict[str, Any], item)
        coerced = {key: value for key, value in record_payload.items() if key in record_fields}
        for key in ("gold_tables", "retrieved_tables"):
            value = coerced.get(key)
            if isinstance(value, list):
                coerced[key] = tuple(value)
        record = EvalRecord(**coerced)
        records.append(record)
        metadata[record.question_id] = record_payload

    per_difficulty_raw = payload.get("per_difficulty") or {}
    if not isinstance(per_difficulty_raw, dict):
        raise ValueError(f"{path} has invalid per_difficulty")

    return (
        EvalRun(
            configuration=Configuration(str(payload["configuration"])),
            sql_model=str(payload["sql_model"]),
            overall=EvalSummary(**payload["overall"]),
            per_difficulty={
                str(key): EvalSummary(**value)
                for key, value in cast(dict[str, Any], per_difficulty_raw).items()
            },
            records=records,
        ),
        metadata,
    )


def _write_reports(run: EvalRun, out: Path) -> None:
    json_path = write_json_report(run, root=out, name_suffix="ensemble")
    siblings: list[EvalRun] = []
    for other in sorted(json_path.parent.glob("*.json")):
        if other == json_path:
            continue
        try:
            siblings.append(_load_report(other)[0])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    write_html_report([*siblings, run], root=out)


if __name__ == "__main__":
    sys.exit(main())
