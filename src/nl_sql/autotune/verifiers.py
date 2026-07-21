"""Verifier seam for the autotune cycle: one candidate answer → pass/fail.

`run_cycle.py` needs a single place to answer "is this generated SQL good?"
without каждый раз re-deriving the rules from the eval runner. That question
shows up in three different steps of the track and each one wants the same
verdict:

- S6(b) execution-filter of the training set — drop gold that does not run;
- S6(a) teacher normalisation — keep the teacher's SQL only when it reproduces
  gold's result set, otherwise fall back to gold;
- ad-hoc triage of a tuned checkpoint on a handful of questions, without
  standing up the whole n=200 harness.

One interface, one implementation. This is deliberately NOT a plugin system:
`Verifier` is a Protocol so a future verifier (LLM judge, AST equivalence)
can be dropped in as a plain object, and nothing here knows they exist.

Parity with the reported metric matters more than elegance, so the two SQL
paths deliberately differ, exactly as `eval/runner.py` does it:

- the candidate goes through `execute_validated` — the AST guards are part of
  the product path, and SQL that the guards reject is SQL the product would
  refuse to run;
- gold is trusted and runs through `execute_readonly` unguarded, because BIRD
  ships gold that the guards (and sometimes sqlglot) would reject while SQLite
  executes it happily.

The one place this is thinner than the runner: the runner has a last-resort
raw-cursor retry for gold, kept there to surface BIRD's ~1% broken gold in the
logs. Here a gold failure is simply `GOLD_FAILED` — "cannot judge", not
"candidate is wrong" — which is precisely the signal the execution-filter
wants.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from nl_sql.db.connection import execute_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.eval.metrics.execution_accuracy import safe_compare_pred
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.runner import execute_validated

STATEMENT_TIMEOUT_MS = 30_000
ROW_CAP = 10_000


class VerifierVerdict(StrEnum):
    """Why a verification passed or failed. Fixed set — callers exhaust it."""

    MATCH = "match"  # candidate reproduces gold's result set
    MISMATCH = "mismatch"  # both ran, results differ
    EXECUTES = "executes"  # no gold supplied: candidate merely ran
    CANDIDATE_FAILED = "candidate_failed"  # guard rejected it or the DB raised
    GOLD_FAILED = "gold_failed"  # reference itself is broken → cannot judge
    UNKNOWN_DATABASE = "unknown_database"  # db_id not in the registry


@dataclass(frozen=True, slots=True)
class VerificationItem:
    """One thing to check.

    `gold_sql=None` asks the weaker question "does this run at all?" — that is
    the execution-filter mode. The dialect is taken from the registry spec
    rather than the caller, so the two cannot disagree.
    """

    db_id: str
    candidate_sql: str
    gold_sql: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    passed: bool
    verdict: VerifierVerdict
    detail: str = ""


class Verifier(Protocol):
    """answer → pass/fail. The whole extensibility contract of the track."""

    def verify(self, item: VerificationItem) -> VerificationOutcome: ...


@dataclass(frozen=True, slots=True)
class ExecutionVerifier:
    """Verify by executing: run the SQL, compare result sets BIRD-style.

    The comparison goes through `safe_compare_pred`, never the raw
    `compare_results` (see scripts/check_no_raw_compare.py): an empty gold and
    a candidate that never produced rows must not be blessed as equal.
    """

    registry: DatabaseRegistry
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS
    row_cap: int = ROW_CAP

    def verify(self, item: VerificationItem) -> VerificationOutcome:
        try:
            spec = self.registry.get(item.db_id)
        except KeyError as exc:
            return VerificationOutcome(False, VerifierVerdict.UNKNOWN_DATABASE, str(exc))

        engine = spec.make_engine()
        candidate = execute_validated(
            engine,
            item.candidate_sql,
            dialect=spec.dialect,
            statement_timeout_ms=self.statement_timeout_ms,
            row_cap=self.row_cap,
        )

        if item.gold_sql is None:
            if candidate.result is None:
                return VerificationOutcome(
                    False,
                    VerifierVerdict.CANDIDATE_FAILED,
                    _candidate_detail(candidate.error_kind, candidate.error_message),
                )
            return VerificationOutcome(
                True,
                VerifierVerdict.EXECUTES,
                f"{candidate.result.row_count} row(s)",
            )

        try:
            with execute_readonly(
                engine,
                item.gold_sql,
                statement_timeout_ms=self.statement_timeout_ms,
                row_cap=self.row_cap,
            ) as gold:
                gold_rows = list(gold.rows)
        except (SQLAlchemyError, MemoryError) as exc:
            return VerificationOutcome(False, VerifierVerdict.GOLD_FAILED, repr(exc))

        if candidate.result is None:
            return VerificationOutcome(
                False,
                VerifierVerdict.CANDIDATE_FAILED,
                _candidate_detail(candidate.error_kind, candidate.error_message),
            )

        comparison = safe_compare_pred(
            gold_rows,
            candidate.result.rows,
            gold_sql=item.gold_sql,
            pred_failed=False,
            gold_failed=False,
        )
        verdict = VerifierVerdict.MATCH if comparison.match else VerifierVerdict.MISMATCH
        detail = comparison.reason or f"gold {comparison.gold_rows} / pred {comparison.pred_rows}"
        return VerificationOutcome(comparison.match, verdict, detail)


def _candidate_detail(kind: ExecutionErrorKind | None, message: str) -> str:
    label = kind.value if kind is not None else "unknown"
    return f"{label}: {message}" if message else label
