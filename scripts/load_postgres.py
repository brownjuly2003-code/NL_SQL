"""Load a SQLite target database into Postgres 16.

Makes the "Postgres 16 + StackExchange-mini" claim real: it copies a shipped
SQLite database (Chinook, or any BIRD Mini-Dev slice — ``codebase_community`` is
the StackExchange-derived one) table-by-table into a Postgres schema the pipeline
can then query through its read-only connection.

Run against the docker-compose Postgres (see docker-compose.yml, profile
``postgres``). Loading requires WRITE privileges, so pass the OWNER DSN here
(``postgres`` superuser), NOT the ``nl_sql_ro`` role the pipeline uses at query
time:

    docker compose --profile postgres up -d
    uv run python scripts/load_postgres.py \
        --sqlite data/bird_mini_dev/MINIDEV/dev_databases/codebase_community/codebase_community.sqlite \
        --pg-dsn postgresql://postgres:postgres@localhost:5433/nl_sql_demo

The tables are created with ``if_exists=replace`` (idempotent re-runs). Type
mapping is delegated to pandas/SQLAlchemy, which is sufficient for these demo
databases; this is a load tool, not a general SQLite→Postgres migrator.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from nl_sql.db.connection import _normalise_pg_driver


def _sqlite_tables(sqlite_path: Path) -> list[str]:
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def load_sqlite_into_postgres(
    sqlite_path: Path,
    pg_dsn: str,
    *,
    only_tables: list[str] | None = None,
    chunk_size: int = 5_000,
) -> dict[str, int]:
    """Copy every table from the SQLite file into Postgres. Returns row counts."""
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    tables = only_tables or _sqlite_tables(sqlite_path)
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    dst = create_engine(_normalise_pg_driver(pg_dsn), future=True)
    loaded: dict[str, int] = {}
    try:
        for table in tables:
            total = 0
            first = True
            for frame in pd.read_sql_query(f'SELECT * FROM "{table}"', src, chunksize=chunk_size):
                frame.to_sql(
                    table,
                    dst,
                    if_exists="replace" if first else "append",
                    index=False,
                    method="multi",
                )
                total += len(frame)
                first = False
            if first:
                # Table was empty — still create it so the schema matches.
                pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT 0', src).to_sql(
                    table, dst, if_exists="replace", index=False
                )
            loaded[table] = total
            print(f"  {table}: {total} rows", flush=True)
        _grant_readonly(dst)
    finally:
        src.close()
        dst.dispose()
    return loaded


def _grant_readonly(engine: Engine) -> None:
    """Best-effort: grant SELECT to nl_sql_ro if that role exists.

    The role is created by scripts/sql/postgres_init.sql on first container boot.
    Newly created tables are not covered by the role's default privileges until
    granted, so re-grant after a load. Silently skipped if the role is absent.
    """
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'nl_sql_ro'")).fetchone()
        if exists:
            conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl_sql_ro"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a SQLite DB into Postgres.")
    parser.add_argument("--sqlite", required=True, type=Path, help="path to the .sqlite file")
    parser.add_argument("--pg-dsn", required=True, help="owner DSN, e.g. postgresql://postgres:...")
    parser.add_argument("--table", action="append", dest="tables", help="limit to table (repeat)")
    parser.add_argument("--chunk", type=int, default=5_000, help="rows per insert batch")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"Loading {args.sqlite} -> Postgres", flush=True)
    counts = load_sqlite_into_postgres(
        args.sqlite, args.pg_dsn, only_tables=args.tables, chunk_size=args.chunk
    )
    print(f"Done: {len(counts)} tables, {sum(counts.values())} rows total", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
