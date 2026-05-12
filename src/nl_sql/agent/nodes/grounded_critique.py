"""Node: critique executed row shape against the question and optional plan."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from nl_sql.agent.state import PipelineState


@dataclass(frozen=True, slots=True)
class ShapeVerdict:
    ok: bool
    expected_label: str
    feedback: str


@dataclass(frozen=True, slots=True)
class _ShapeExpectation:
    expected_label: str
    min_rows: int | None = None
    max_rows: int | None = None
    list_cap: int | None = None


def evaluate_shape(question: str, plan_json: str | None, actual_row_count: int) -> ShapeVerdict:
    expectation = _expectation_from_plan(plan_json) or _expectation_from_question(question)
    if expectation is None:
        return ShapeVerdict(ok=True, expected_label="unconstrained rows", feedback="")

    if _shape_matches(expectation, actual_row_count):
        return ShapeVerdict(ok=True, expected_label=expectation.expected_label, feedback="")

    feedback = (
        f"The previous query returned {actual_row_count} rows, but the question implies "
        f"{expectation.expected_label}.\n"
        "Common causes: (a) missing WHERE filter implied by the question, (b) missing\n"
        'GROUP BY, (c) wrong join multiplicity, (d) "for X among Y" needing additional\n'
        "condition. Re-examine the question and produce SQL whose result shape matches."
    )
    return ShapeVerdict(ok=False, expected_label=expectation.expected_label, feedback=feedback)


def make_grounded_critique_node() -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        outcome = state.get("outcome")
        actual_row_count = 0
        if outcome is not None and outcome.result is not None:
            actual_row_count = len(outcome.result.rows)

        verdict = evaluate_shape(
            state.get("question", ""),
            state.get("plan"),
            actual_row_count,
        )
        if not verdict.ok:
            return {"last_error": verdict.feedback, "critique_failed": True}
        return {"critique_failed": False}

    return node


def _expectation_from_plan(plan_json: str | None) -> _ShapeExpectation | None:
    if not plan_json or not plan_json.strip():
        return None
    try:
        payload: object = json.loads(plan_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    value = payload.get("expected_row_count")
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    if normalized == "1":
        return _ShapeExpectation(expected_label="exactly 1 row", min_rows=1, max_rows=1)
    if normalized == "few (2-20)":
        return _ShapeExpectation(expected_label="2 to 20 rows", min_rows=2, max_rows=20)
    if normalized == "many (>20)":
        return _ShapeExpectation(expected_label="more than 20 rows", min_rows=21)
    return None


def _expectation_from_question(question: str) -> _ShapeExpectation | None:
    normalized = question.lower()
    if (
        "how many" in normalized
        or "count of" in normalized
        or "number of" in normalized
        or "percentage" in normalized
        or "ratio" in normalized
        or "what fraction" in normalized
        or "what proportion" in normalized
        or "average " in normalized
        or "mean " in normalized
        or _has_single_total_or_sum(normalized)
        or _asks_for_single_extreme(normalized)
    ):
        return _ShapeExpectation(expected_label="exactly 1 row", min_rows=1, max_rows=1)

    top_n = _extract_top_n(normalized)
    if top_n is not None:
        return _ShapeExpectation(
            expected_label=f"at most {top_n} rows",
            min_rows=1,
            max_rows=top_n,
        )

    if re.search(r"\b(which|what|list|name|show|indicate)\b", normalized):
        return _ShapeExpectation(expected_label="1 to 1000 rows", min_rows=1, list_cap=1000)

    return None


def _shape_matches(expectation: _ShapeExpectation, actual_row_count: int) -> bool:
    if expectation.min_rows is not None and actual_row_count < expectation.min_rows:
        return False
    if expectation.max_rows is not None and actual_row_count > expectation.max_rows:
        return False
    return expectation.list_cap is None or actual_row_count <= expectation.list_cap


def _extract_top_n(question: str) -> int | None:
    top_match = re.search(r"\btop\s+(\d+)\b", question)
    if top_match:
        return int(top_match.group(1))
    ranked_match = re.search(r"\b(\d+)\s+(?:highest|lowest)\b", question)
    if ranked_match:
        return int(ranked_match.group(1))
    return None


def _has_single_total_or_sum(question: str) -> bool:
    return bool(
        re.search(r"\b(total|sum)\b", question)
        and not re.search(r"\b(by|per|each)\b|for each|grouped by", question)
    )


def _asks_for_single_extreme(question: str) -> bool:
    return bool(
        re.search(r"\bwhich\b.+\bhas\s+the\s+(?:most|highest|least)\b", question)
        or re.search(r"\bwhose\b.+\bis\s+the\s+most\b", question)
    )


__all__ = ["ShapeVerdict", "evaluate_shape", "make_grounded_critique_node"]
