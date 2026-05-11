"""Unit tests for `eval.self_consistency` voting logic.

The voter receives a list of `Candidate(result=PipelineRunResult, temperature)`
and picks one. We don't run the actual graph — we synthesise minimal
`PipelineRunResult` instances directly so the test isolates voting
semantics from any model or executor behaviour.
"""

from __future__ import annotations

import pytest

from nl_sql.agent.graph import PipelineRunResult
from nl_sql.db.connection import QueryResult
from nl_sql.eval.self_consistency import (
    Candidate,
    fingerprint_rows,
    vote,
)
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.guards import ValidationReport
from nl_sql.execution.runner import ExecutionOutcome


def _outcome(rows: list[tuple[object, ...]] | None, error: ExecutionErrorKind | None = None) -> ExecutionOutcome:
    validation = ValidationReport(sql="select 1", dialect="sqlite", violations=[])
    if rows is None:
        return ExecutionOutcome(
            sql="select 1",
            validation=validation,
            result=None,
            error_kind=error,
            error_message="boom" if error else "",
        )
    qr = QueryResult(
        rows=rows,
        columns=["c"] * (len(rows[0]) if rows else 1),
        row_count=len(rows),
        truncated=False,
        elapsed_ms=1.0,
    )
    return ExecutionOutcome(
        sql="select 1",
        validation=validation,
        result=qr,
        error_kind=error,
        error_message="" if error is None else "boom",
    )


def _result(
    *,
    sql: str = "select 1",
    rows: list[tuple[object, ...]] | None,
    error: ExecutionErrorKind | None = None,
    confidence: float = 0.5,
) -> PipelineRunResult:
    outcome = _outcome(rows, error=error)
    trace = [
        {"node": "generate_sql", "model": "x", "confidence": confidence,
         "tables_used": [], "input_tokens": 10, "output_tokens": 20}
    ]
    return PipelineRunResult(
        question="q",
        db_id="db",
        sql=sql,
        rationale="",
        confidence=confidence,
        outcome=outcome,
        output_format=None,
        caption="",
        error_kind=error,
        error_message="" if error is None else "boom",
        repair_attempted=False,
        trace=trace,
    )


def _cand(temp: float, **kwargs: object) -> Candidate:
    return Candidate(result=_result(**kwargs), temperature=temp)  # type: ignore[arg-type]


def test_fingerprint_is_order_agnostic():
    assert fingerprint_rows([(1,), (2,), (3,)]) == fingerprint_rows([(3,), (1,), (2,)])


def test_fingerprint_distinguishes_different_rows():
    assert fingerprint_rows([(1,), (2,)]) != fingerprint_rows([(1,), (3,)])


def test_fingerprint_normalises_floats_and_strings():
    assert fingerprint_rows([(1.0000001,)]) == fingerprint_rows([(1.0,)])
    assert fingerprint_rows([(" hi ",)]) == fingerprint_rows([("hi",)])


def test_fingerprint_sorts_rows_with_none_values():
    """Regression: rows like [('x', None), ('y', 'z')] must sort without TypeError.

    Real BIRD queries surface NULL values mixed with strings; Python 3
    refuses to sort heterogeneous types directly.
    """
    rows_a: list[tuple[object, ...]] = [("x", None), ("y", "z")]
    rows_b: list[tuple[object, ...]] = [("y", "z"), ("x", None)]
    # Both orderings should fingerprint identically (set-equivalence).
    assert fingerprint_rows(rows_a) == fingerprint_rows(rows_b)


def test_vote_picks_largest_cluster():
    # 3 candidates agree on rows=[(1,)], 1 disagrees with [(2,)]
    cands = [
        _cand(0.2, rows=[(1,)]),
        _cand(0.4, rows=[(1,)]),
        _cand(0.6, rows=[(2,)]),
        _cand(0.8, rows=[(1,)]),
    ]
    winner = vote(cands)
    assert winner.result.outcome.result.rows == [(1,)]


def test_vote_breaks_cluster_ties_by_confidence():
    # Two singleton clusters — pick the one with higher self-confidence
    cands = [
        _cand(0.2, rows=[(1,)], confidence=0.3),
        _cand(0.4, rows=[(2,)], confidence=0.9),
    ]
    winner = vote(cands)
    assert winner.result.outcome.result.rows == [(2,)]
    assert winner.result.confidence == pytest.approx(0.9)


def test_vote_within_cluster_picks_highest_confidence():
    # Same cluster, different confidences — return the proudest member
    cands = [
        _cand(0.2, rows=[(1,)], confidence=0.4),
        _cand(0.4, rows=[(1,)], confidence=0.9),
        _cand(0.6, rows=[(1,)], confidence=0.5),
    ]
    winner = vote(cands)
    assert winner.result.confidence == pytest.approx(0.9)


def test_vote_drops_invalid_and_execution_failures_from_voting():
    # Two failed candidates + two that agree on rows=[(7,)]
    cands = [
        _cand(0.2, rows=None, error=ExecutionErrorKind.INVALID_SQL),
        _cand(0.4, rows=None, error=ExecutionErrorKind.EXECUTION_FAILED),
        _cand(0.6, rows=[(7,)]),
        _cand(0.8, rows=[(7,)]),
    ]
    winner = vote(cands)
    assert winner.result.outcome.result.rows == [(7,)]


def test_vote_treats_empty_result_as_legitimate_cluster():
    # Three say "no rows" → that's the answer
    cands = [
        _cand(0.2, rows=[], error=ExecutionErrorKind.EMPTY_RESULT),
        _cand(0.4, rows=[], error=ExecutionErrorKind.EMPTY_RESULT),
        _cand(0.6, rows=[], error=ExecutionErrorKind.EMPTY_RESULT),
        _cand(0.8, rows=[(1,)]),
    ]
    winner = vote(cands)
    assert winner.result.outcome.result.rows == []


def test_vote_falls_back_to_confidence_when_all_failed():
    cands = [
        _cand(0.2, rows=None, error=ExecutionErrorKind.INVALID_SQL, confidence=0.3),
        _cand(0.4, rows=None, error=ExecutionErrorKind.EXECUTION_FAILED, confidence=0.7),
    ]
    winner = vote(cands)
    assert winner.result.confidence == pytest.approx(0.7)


def test_vote_prefers_lower_temperature_on_full_tie():
    cands = [
        _cand(0.6, rows=[(1,)], confidence=0.5),
        _cand(0.2, rows=[(2,)], confidence=0.5),
    ]
    winner = vote(cands)
    assert winner.temperature == pytest.approx(0.2)


def test_vote_requires_at_least_one_candidate():
    with pytest.raises(ValueError, match="at least one candidate"):
        vote([])
