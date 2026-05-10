"""Read-only connection helpers for target databases.

The NL→SQL pipeline never owns write privileges on a target DB. Defences:
- Postgres: dedicated role with `default_transaction_read_only=on`, see
  `scripts/sql/postgres_init.sql`.
- SQLite: `mode=ro` URI passed via a SQLAlchemy creator (URL form does not
  carry through cross-platform; creator gives us full control over path
  encoding) plus `PRAGMA query_only=ON` as a belt-and-braces guard.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Connection, Engine, create_engine, text

Dialect = Literal["sqlite", "postgresql"]


@dataclass(frozen=True, slots=True)
class DatabaseSpec:
    """Connection target.

    For SQLite, `url` is the absolute filesystem path to the .sqlite file.
    For Postgres, `url` is a standard libpq DSN (`postgresql://...`).
    """

    id: str
    dialect: Dialect
    url: str
    description: str = ""

    def make_engine(self) -> Engine:
        return _build_engine(self)


@dataclass(frozen=True, slots=True)
class QueryResult:
    rows: list[tuple[Any, ...]]
    columns: list[str]
    row_count: int
    truncated: bool
    elapsed_ms: float


def _build_engine(spec: DatabaseSpec) -> Engine:
    if spec.dialect == "sqlite":
        return _build_sqlite_readonly_engine(Path(spec.url))
    if spec.dialect == "postgresql":
        return create_engine(spec.url, future=True, pool_pre_ping=True)
    raise ValueError(f"unsupported dialect: {spec.dialect}")


def _build_sqlite_readonly_engine(path: Path) -> Engine:
    if not path.is_absolute():
        path = path.resolve()
    file_uri = path.as_uri() + "?mode=ro"

    def _creator() -> sqlite3.Connection:
        conn = sqlite3.connect(file_uri, uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only = ON")
        return conn

    return create_engine("sqlite://", creator=_creator, future=True)


def connect(spec: DatabaseSpec) -> Engine:
    """Build (or reuse via SQLAlchemy pool) an engine for a DB spec."""
    return spec.make_engine()


@contextmanager
def execute_readonly(
    engine: Engine,
    sql: str,
    *,
    statement_timeout_ms: int = 30_000,
    row_cap: int = 10_000,
) -> Iterator[QueryResult]:
    """Run a SELECT-only query with hard timeout and row cap.

    Caller must have already validated `sql` through the AST guard. This
    function enforces operational limits, not correctness or safety.
    """
    started = time.perf_counter()
    with engine.connect() as conn:
        _apply_runtime_limits(conn, statement_timeout_ms)
        cursor = conn.execute(text(sql))
        columns = list(cursor.keys())
        rows = cursor.fetchmany(row_cap + 1)
        cursor.close()  # drain any remaining rows so SQLite/Postgres release resources
    truncated = len(rows) > row_cap
    if truncated:
        rows = rows[:row_cap]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    yield QueryResult(
        rows=[tuple(r) for r in rows],
        columns=columns,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=elapsed_ms,
    )


def _apply_runtime_limits(conn: Connection, statement_timeout_ms: int) -> None:
    dialect = conn.engine.dialect.name
    if dialect == "postgresql":
        conn.execute(text(f"SET statement_timeout = {int(statement_timeout_ms)}"))
        conn.execute(text("SET default_transaction_read_only = on"))
    elif dialect == "sqlite":
        # SQLite has no per-query timeout knob in the URL API; use connection
        # progress handler at the dbapi level.
        seconds = statement_timeout_ms / 1000.0
        raw = conn.connection.driver_connection
        if isinstance(raw, sqlite3.Connection):
            _install_sqlite_timeout(raw, seconds)


def _install_sqlite_timeout(conn: sqlite3.Connection, seconds: float) -> None:
    deadline = time.monotonic() + seconds

    def _interrupt() -> int:
        return 1 if time.monotonic() > deadline else 0

    # progress handler is invoked every N VM ops; 1000 keeps overhead trivial.
    conn.set_progress_handler(_interrupt, 1000)


def sqlite_url_readonly(path: Path) -> str:
    """Return the absolute path used as DatabaseSpec.url for SQLite specs.

    We store the bare path (not a full SQLAlchemy URL) because read-only mode
    is applied via a creator function in `_build_sqlite_readonly_engine` —
    SQLAlchemy's URL builder does not carry the SQLite `mode=ro` URI cleanly
    across Windows and POSIX path encodings.
    """
    return str(path.resolve())
