"""End-to-end execution tests against a real (tmp) SQLite DB."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from nl_sql.db import DatabaseSpec, connect
from nl_sql.db.connection import sqlite_url_readonly
from nl_sql.execution import ExecutionErrorKind, execute_validated


@pytest.fixture
def music_db(tmp_path: Path) -> Path:
    db = tmp_path / "music.sqlite"
    raw = sqlite3.connect(db)
    raw.executescript(
        """
        CREATE TABLE Artists (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE Albums (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            artist_id INTEGER REFERENCES Artists(id),
            year INTEGER
        );
        INSERT INTO Artists VALUES (1, 'Queen'), (2, 'Pink Floyd'), (3, 'Bowie');
        INSERT INTO Albums VALUES
            (1, 'A Night at the Opera', 1, 1975),
            (2, 'Dark Side of the Moon', 2, 1973),
            (3, 'The Wall', 2, 1979),
            (4, 'Heroes', 3, 1977);
        """
    )
    raw.commit()
    raw.close()
    return db


@pytest.fixture
def engine(music_db: Path) -> Iterator[Engine]:
    spec = DatabaseSpec(
        id="music", dialect="sqlite", url=sqlite_url_readonly(music_db), description=""
    )
    eng = connect(spec)
    try:
        yield eng
    finally:
        eng.dispose()


def test_valid_query_returns_outcome_ok(engine: Engine) -> None:
    outcome = execute_validated(engine, "SELECT name FROM Artists ORDER BY id")

    assert outcome.ok
    assert outcome.error_kind is None
    assert outcome.result is not None
    assert outcome.result.row_count == 3
    assert outcome.validation.ok


def test_invalid_sql_blocked_before_execute(engine: Engine) -> None:
    outcome = execute_validated(engine, "DROP TABLE Artists")

    assert not outcome.ok
    assert outcome.error_kind == ExecutionErrorKind.INVALID_SQL
    assert outcome.result is None
    assert not outcome.validation.ok


def test_garbage_sql_blocked_before_execute(engine: Engine) -> None:
    outcome = execute_validated(engine, "this is not sql")

    assert outcome.error_kind == ExecutionErrorKind.INVALID_SQL


def test_empty_result_marked_explicitly(engine: Engine) -> None:
    outcome = execute_validated(engine, "SELECT * FROM Artists WHERE name = 'NonexistentBand'")

    assert outcome.error_kind == ExecutionErrorKind.EMPTY_RESULT
    assert outcome.result is not None
    assert outcome.result.row_count == 0


def test_query_against_missing_table_yields_execution_failed(engine: Engine) -> None:
    outcome = execute_validated(engine, "SELECT * FROM NoSuchTable")

    assert outcome.error_kind == ExecutionErrorKind.EXECUTION_FAILED
    assert outcome.result is None


def test_row_cap_applied(engine: Engine) -> None:
    outcome = execute_validated(engine, "SELECT * FROM Albums", row_cap=2)

    assert outcome.ok
    assert outcome.result is not None
    assert outcome.result.row_count == 2
    assert outcome.result.truncated is True
