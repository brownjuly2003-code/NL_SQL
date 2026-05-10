"""Node: execute the validated SQL via the read-only runner.

The validate node has already produced a `ValidationReport`; we re-validate
inside `execute_validated` (cheap) so this node still works if it's ever
called directly without the validate predecessor (e.g. in unit tests).
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.state import PipelineState
from nl_sql.db.connection import Dialect
from nl_sql.db.registry import DatabaseRegistry, get_default_registry
from nl_sql.execution.runner import execute_validated


def make_execute_node(
    *,
    registry: DatabaseRegistry | None = None,
    statement_timeout_ms: int = 30_000,
    row_cap: int = 10_000,
) -> Callable[[PipelineState], PipelineState]:
    """`registry` is injected for tests; production code uses the default scan.

    Engine is created+disposed per call. SQLite engine setup is essentially
    free; pooling is unnecessary for one query at a time and risks leaking
    SQLite connections under pytest's strict `ResourceWarning` regime on
    Windows.
    """
    reg = registry or get_default_registry()

    def node(state: PipelineState) -> PipelineState:
        generated = state.get("generated")
        db_id = state.get("db_id", "")
        dialect: Dialect = state.get("dialect", "sqlite")
        trace = list(state.get("trace") or [])

        if generated is None or not generated.sql:
            trace.append({"node": "execute", "ok": False, "reason": "no_sql"})
            # validate already populated outcome+error fields; pass them through.
            return {"trace": trace}

        engine = reg.get(db_id).make_engine()
        try:
            outcome = execute_validated(
                engine,
                generated.sql,
                dialect=dialect,
                statement_timeout_ms=statement_timeout_ms,
                row_cap=row_cap,
            )
        finally:
            engine.dispose()
        if outcome.ok:
            trace.append(
                {
                    "node": "execute",
                    "ok": True,
                    "row_count": outcome.result.row_count if outcome.result else 0,
                    "elapsed_ms": outcome.result.elapsed_ms if outcome.result else 0.0,
                }
            )
            return {
                "outcome": outcome,
                "error_kind": None,
                "error_message": "",
                "trace": trace,
            }

        trace.append(
            {
                "node": "execute",
                "ok": False,
                "kind": outcome.error_kind.value if outcome.error_kind else None,
                "message": outcome.error_message,
            }
        )
        return {
            "outcome": outcome,
            "last_error": outcome.error_message,
            "error_kind": outcome.error_kind,
            "error_message": outcome.error_message,
            "trace": trace,
        }

    return node
