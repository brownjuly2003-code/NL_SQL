"""End-to-end SQL execution: validate → execute under runtime limits → report.

Single entry point `execute_validated`. Pipeline nodes call this instead of
threading the guard + DB layers themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from nl_sql.db.connection import Dialect, QueryResult, execute_readonly
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.guards import ValidationReport, validate_sql


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """Combined result + error taxonomy.

    Exactly one of `result` or `error_kind` is set. `validation` is always
    present so callers can render the AST-level diagnostics regardless of
    whether execution actually ran.
    """

    sql: str
    validation: ValidationReport
    result: QueryResult | None = None
    error_kind: ExecutionErrorKind | None = None
    error_message: str = ""

    @property
    def ok(self) -> bool:
        return self.result is not None and self.error_kind is None


def execute_validated(
    engine: Engine,
    sql: str,
    *,
    dialect: Dialect = "sqlite",
    statement_timeout_ms: int = 30_000,
    row_cap: int = 10_000,
) -> ExecutionOutcome:
    validation = validate_sql(sql, dialect=dialect)
    if not validation.ok:
        return ExecutionOutcome(
            sql=sql,
            validation=validation,
            error_kind=ExecutionErrorKind.INVALID_SQL,
            error_message="; ".join(v.message for v in validation.violations),
        )

    try:
        with execute_readonly(
            engine,
            sql,
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
        ) as result:
            if result.row_count == 0:
                return ExecutionOutcome(
                    sql=sql,
                    validation=validation,
                    result=result,
                    error_kind=ExecutionErrorKind.EMPTY_RESULT,
                    error_message="query returned 0 rows",
                )
            return ExecutionOutcome(sql=sql, validation=validation, result=result)
    except OperationalError as exc:
        kind = (
            ExecutionErrorKind.EXECUTION_TIMEOUT
            if "timeout" in str(exc).lower() or "interrupted" in str(exc).lower()
            else ExecutionErrorKind.EXECUTION_FAILED
        )
        return ExecutionOutcome(
            sql=sql,
            validation=validation,
            error_kind=kind,
            error_message=str(exc),
        )
    except SQLAlchemyError as exc:
        return ExecutionOutcome(
            sql=sql,
            validation=validation,
            error_kind=ExecutionErrorKind.EXECUTION_FAILED,
            error_message=str(exc),
        )
