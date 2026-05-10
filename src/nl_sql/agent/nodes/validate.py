"""Node: run the static SQL guard (`validate_sql`) on the current candidate.

Sets `outcome` with INVALID_SQL if the guard rejects, otherwise leaves
`outcome` unset so the execute node can run. Failure here routes to
``repair_once`` if no repair has been tried yet, or to ``deterministic_format``
(with the validation error visible) if we already burned the single retry.
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.state import PipelineState
from nl_sql.db.connection import Dialect
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.guards import GuardViolation, ValidationReport, validate_sql
from nl_sql.execution.runner import ExecutionOutcome


def make_validate_node() -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        generated = state.get("generated")
        dialect: Dialect = state.get("dialect", "sqlite")
        trace = list(state.get("trace") or [])

        if generated is None or not generated.sql:
            report = ValidationReport(sql="", dialect=dialect)
            report.add("no_sql", "generate_sql produced no SQL")
            outcome = ExecutionOutcome(
                sql="",
                validation=report,
                error_kind=ExecutionErrorKind.INVALID_SQL,
                error_message="generate_sql produced no SQL",
            )
            trace.append({"node": "validate", "ok": False, "reason": "no_sql"})
            return {
                "outcome": outcome,
                "last_error": outcome.error_message,
                "error_kind": ExecutionErrorKind.INVALID_SQL,
                "error_message": outcome.error_message,
                "trace": trace,
            }

        report = validate_sql(generated.sql, dialect=dialect)
        if report.ok:
            trace.append({"node": "validate", "ok": True})
            return {
                "outcome": ExecutionOutcome(sql=generated.sql, validation=report),
                "trace": trace,
            }

        joined = "; ".join(v.message for v in report.violations)
        outcome = ExecutionOutcome(
            sql=generated.sql,
            validation=report,
            error_kind=ExecutionErrorKind.INVALID_SQL,
            error_message=joined,
        )
        trace.append(
            {
                "node": "validate",
                "ok": False,
                "violations": [v.code for v in report.violations],
            }
        )
        return {
            "outcome": outcome,
            "last_error": joined,
            "error_kind": ExecutionErrorKind.INVALID_SQL,
            "error_message": joined,
            "trace": trace,
        }

    return node


# GuardViolation is re-exported solely so direct unit tests of this node
# don't need a separate import.
__all__ = ["GuardViolation", "make_validate_node"]
