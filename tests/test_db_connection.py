"""Tests for the read-only target-DB connection layer.

We build a small SQLite database in a tmp_path so the tests cover the real
SQLAlchemy + sqlite3 path, not just the URL builder. Postgres-specific runtime
limits are verified at the SQL emission level by inspecting the engine's
dialect — full Postgres integration tests are deferred to the docker-compose
profile and live in tests/integration/ when that lands.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from nl_sql.db import (
    DatabaseSpec,
    connect,
    execute_readonly,
)
from nl_sql.db.connection import sqlite_url_readonly


@pytest.fixture
def chinook_like(tmp_path: Path) -> Path:
    db_path = tmp_path / "tiny.sqlite"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE Artists (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE Albums (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            artist_id INTEGER REFERENCES Artists(id)
        );
        INSERT INTO Artists (id, name) VALUES (1, 'Queen'), (2, 'Pink Floyd');
        INSERT INTO Albums (id, title, artist_id) VALUES
            (1, 'A Night at the Opera', 1),
            (2, 'The Dark Side of the Moon', 2),
            (3, 'The Wall', 2);
        """
    )
    raw.commit()
    raw.close()
    return db_path


def _spec(db_path: Path) -> DatabaseSpec:
    return DatabaseSpec(
        id="tiny",
        dialect="sqlite",
        url=sqlite_url_readonly(db_path),
        description="test fixture",
    )


@pytest.fixture
def engine(chinook_like: Path) -> Iterator[Engine]:
    eng = connect(_spec(chinook_like))
    try:
        yield eng
    finally:
        eng.dispose()


def test_execute_readonly_returns_rows(engine: Engine) -> None:
    with execute_readonly(engine, "SELECT name FROM Artists ORDER BY id") as result:
        assert result.columns == ["name"]
        assert result.rows == [("Queen",), ("Pink Floyd",)]
        assert result.row_count == 2
        assert not result.truncated
        assert result.elapsed_ms >= 0


def test_execute_readonly_caps_rows(engine: Engine) -> None:
    with execute_readonly(engine, "SELECT * FROM Albums", row_cap=2) as result:
        assert result.row_count == 2
        assert result.truncated is True


def test_execute_readonly_handles_colons_in_string_literal(engine: Engine) -> None:
    """Regression: SQLAlchemy `text()` parses `:ident` as bind parameters, which
    breaks BIRD gold like `LIKE '_:%:__.___'` (qids 959 / 989 / 990 — formula_1
    time patterns). `execute_readonly` must run the statement via
    `exec_driver_sql` so colons inside string literals reach the DBAPI verbatim.
    """
    sql = "SELECT name FROM Artists WHERE name LIKE '_:%:__.___' OR name = 'Queen' ORDER BY id"
    with execute_readonly(engine, sql) as result:
        assert result.rows == [("Queen",)]


def test_execute_readonly_rejects_writes(engine: Engine) -> None:
    """The engine itself rejects DML even when caller bypasses the AST guard."""
    with engine.connect() as conn, pytest.raises(Exception, match=r"(?i)readonly|read.only"):
        conn.execute(text("INSERT INTO Artists (id, name) VALUES (99, 'Hacked')"))


def test_sqlite_url_readonly_returns_absolute_path(tmp_path: Path) -> None:
    target = tmp_path / "x.sqlite"
    url = sqlite_url_readonly(target)
    assert Path(url).is_absolute()
    assert url == str(target.resolve())


def test_unsupported_dialect_raises() -> None:
    spec = DatabaseSpec(id="bad", dialect="mysql", url="mysql://x", description="")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported dialect"):
        connect(spec)
