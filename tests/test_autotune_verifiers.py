"""Tests for the autotune verifier seam (plan_autotune S7).

Everything runs against a real tmp_path SQLite file, so the guards, the DBAPI
cursor path and the BIRD-style comparator are all exercised for real — a
verifier that agreed with the eval runner only in mocks would be worthless.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from nl_sql.autotune import (
    ExecutionVerifier,
    VerificationItem,
    VerifierVerdict,
)
from nl_sql.db.connection import DatabaseSpec, dispose_engines, sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry


@pytest.fixture
def registry(tmp_path: Path) -> Iterator[DatabaseRegistry]:
    db_path = tmp_path / "tiny.sqlite"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE Artists (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        INSERT INTO Artists (id, name) VALUES (1, 'Queen'), (2, 'Pink Floyd');
        """
    )
    raw.commit()
    raw.close()

    reg = DatabaseRegistry()
    reg.register(
        DatabaseSpec(
            id="tiny",
            dialect="sqlite",
            url=sqlite_url_readonly(db_path),
            description="verifier test fixture",
        )
    )
    try:
        yield reg
    finally:
        dispose_engines()


def test_matching_sql_passes(registry: DatabaseRegistry) -> None:
    verifier = ExecutionVerifier(registry)
    outcome = verifier.verify(
        VerificationItem(
            db_id="tiny",
            candidate_sql="SELECT name FROM Artists ORDER BY id DESC",
            gold_sql="SELECT name FROM Artists",
        )
    )
    assert outcome.passed
    assert outcome.verdict is VerifierVerdict.MATCH


def test_different_rows_fail(registry: DatabaseRegistry) -> None:
    verifier = ExecutionVerifier(registry)
    outcome = verifier.verify(
        VerificationItem(
            db_id="tiny",
            candidate_sql="SELECT name FROM Artists WHERE id = 1",
            gold_sql="SELECT name FROM Artists",
        )
    )
    assert not outcome.passed
    assert outcome.verdict is VerifierVerdict.MISMATCH


def test_candidate_rejected_by_guard(registry: DatabaseRegistry) -> None:
    verifier = ExecutionVerifier(registry)
    outcome = verifier.verify(
        VerificationItem(
            db_id="tiny",
            candidate_sql="DELETE FROM Artists",
            gold_sql="SELECT name FROM Artists",
        )
    )
    assert not outcome.passed
    assert outcome.verdict is VerifierVerdict.CANDIDATE_FAILED
    assert "invalid_sql" in outcome.detail


def test_candidate_that_raises_is_not_blessed_by_empty_gold(
    registry: DatabaseRegistry,
) -> None:
    """The qid-518 defect class, pinned at the verifier boundary.

    Gold legitimately returns zero rows; the candidate never executes at all.
    Row-level comparison would call that a match (`[] == []`). The verifier
    must report the candidate's failure instead — this is why the comparison
    is short-circuited rather than delegated to `compare_results`.
    """
    verifier = ExecutionVerifier(registry)
    outcome = verifier.verify(
        VerificationItem(
            db_id="tiny",
            candidate_sql="SELECT name FROM NoSuchTable",
            gold_sql="SELECT name FROM Artists WHERE id = 999",
        )
    )
    assert not outcome.passed
    assert outcome.verdict is VerifierVerdict.CANDIDATE_FAILED


def test_broken_gold_is_unjudgeable_not_a_candidate_failure(
    registry: DatabaseRegistry,
) -> None:
    verifier = ExecutionVerifier(registry)
    outcome = verifier.verify(
        VerificationItem(
            db_id="tiny",
            candidate_sql="SELECT name FROM Artists",
            gold_sql="SELECT name FROM GoldTypo",
        )
    )
    assert not outcome.passed
    assert outcome.verdict is VerifierVerdict.GOLD_FAILED


def test_execution_filter_mode_without_gold(registry: DatabaseRegistry) -> None:
    verifier = ExecutionVerifier(registry)
    ok = verifier.verify(VerificationItem(db_id="tiny", candidate_sql="SELECT 1"))
    assert ok.passed
    assert ok.verdict is VerifierVerdict.EXECUTES

    bad = verifier.verify(VerificationItem(db_id="tiny", candidate_sql="SELECT * FROM Nope"))
    assert not bad.passed
    assert bad.verdict is VerifierVerdict.CANDIDATE_FAILED


def test_unknown_database_is_reported_not_raised(registry: DatabaseRegistry) -> None:
    verifier = ExecutionVerifier(registry)
    outcome = verifier.verify(
        VerificationItem(db_id="absent", candidate_sql="SELECT 1", gold_sql="SELECT 1")
    )
    assert not outcome.passed
    assert outcome.verdict is VerifierVerdict.UNKNOWN_DATABASE
    assert "absent" in outcome.detail
