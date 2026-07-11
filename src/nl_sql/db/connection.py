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
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

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
        return _build_postgres_readonly_engine(spec.url)
    raise ValueError(f"unsupported dialect: {spec.dialect}")


def _normalise_pg_driver(url: str) -> str:
    """Force the psycopg (v3) driver for bare ``postgresql://`` DSNs.

    SQLAlchemy resolves an unqualified ``postgresql://`` to the psycopg2 driver,
    which is not installed here (only psycopg 3 is). Left unqualified, every
    Postgres connection would die with ModuleNotFoundError — which is exactly
    why the Postgres path had never actually run. Explicit ``+psycopg`` /
    ``+psycopg2`` DSNs are respected as-is.
    """
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def _build_postgres_readonly_engine(url: str) -> Engine:
    """Engine whose every transaction is genuinely READ ONLY.

    The read-only guarantee comes from SQLAlchemy's ``postgresql_readonly``
    execution option, which sets the connection read-only at transaction start
    (the correct point). An earlier implementation issued
    ``SET default_transaction_read_only = on`` from inside an already-open
    transaction — Postgres fixes a transaction's read-only status at BEGIN, so
    that statement was a no-op for the current transaction and the "layer 1"
    read-only defence never actually engaged.
    """
    return create_engine(
        _normalise_pg_driver(url),
        future=True,
        pool_pre_ping=True,
        execution_options={"postgresql_readonly": True},
    )


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
        # Run on a DBAPI cursor with NO parameters, because every parameterised
        # path mangles a literal that real SQL contains:
        #   - SQLAlchemy `text()` reads `:__` as a bind parameter, breaking gold
        #     like `LIKE '_:%:__.___'` (BIRD qids 959/989/990, formula_1 times).
        #   - `exec_driver_sql` passes an (empty) parameter set to the driver, so
        #     psycopg's pyformat parser scans for placeholders and rejects `%`:
        #     `LIKE '%variance%'` → "only '%s', '%b', '%t' are allowed as
        #     placeholders". That killed LIKE filters *and* the `%` modulo
        #     operator on Postgres — see tests/test_postgres_readonly.py.
        # A cursor executed with no parameters interprets neither, on either driver.
        cursor = conn.connection.cursor()
        try:
            cursor.execute(sql)
            columns = [str(d[0]) for d in cursor.description or ()]
            rows = cursor.fetchmany(row_cap + 1)
        except Exception as raw_exc:
            # Going through the raw cursor also means driver-native exceptions
            # (sqlite3.OperationalError, psycopg.Error) instead of SQLAlchemy's.
            # Callers classify failures on sqlalchemy.exc types — timeouts on
            # OperationalError, everything else on SQLAlchemyError (see
            # execution/runner.py) — so re-wrap and keep that contract intact.
            raise DBAPIError.instance(
                sql,
                None,
                raw_exc,
                engine.dialect.loaded_dbapi.Error,
                dialect=engine.dialect,
            ) from raw_exc
        finally:
            cursor.close()  # release server-side resources / drain remaining rows
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
        # statement_timeout takes effect immediately for subsequent statements in
        # this session, so setting it here (inside the transaction) is correct.
        # Read-only is NOT set here — it is applied at transaction start by the
        # engine's postgresql_readonly execution option (see
        # _build_postgres_readonly_engine); issuing it here would be a no-op.
        conn.execute(text(f"SET statement_timeout = {int(statement_timeout_ms)}"))
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
