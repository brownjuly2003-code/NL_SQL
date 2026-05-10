"""Error taxonomy for the execution layer.

The pipeline reports outcomes via this fixed enum so eval metrics can slice
failures by exact category. Adding a new failure mode requires extending
this enum first; downstream code must exhaust the cases.
"""

from __future__ import annotations

from enum import StrEnum


class ExecutionErrorKind(StrEnum):
    INVALID_SQL = "invalid_sql"  # AST guard rejected before execute
    EXECUTION_TIMEOUT = "execution_timeout"
    EXECUTION_FAILED = "execution_failed"  # database raised at execute time
    EMPTY_RESULT = "empty_result"  # not an error per se; tracked for slicing
    LOW_CONFIDENCE = "low_confidence"  # confidence flag from generator
    REPAIR_FAILED = "repair_failed"  # second-pass also rejected


class ExecutionError(Exception):
    def __init__(self, kind: ExecutionErrorKind, message: str) -> None:
        super().__init__(f"{kind.value}: {message}")
        self.kind = kind
        self.message = message


class ValidationError(ExecutionError):
    def __init__(self, message: str) -> None:
        super().__init__(ExecutionErrorKind.INVALID_SQL, message)
