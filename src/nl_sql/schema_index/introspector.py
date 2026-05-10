"""Walk a SQLAlchemy engine to extract tables, columns, PK/FK, and per-column
column-value statistics (top-K samples, null count, distinct count).

Dialect-agnostic via SQLAlchemy reflection + programmatic SELECTs (no raw SQL
strings, so identifier quoting is handled by the dialect). This module runs
*offline* during indexing and assumes the engine is read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    type: str  # str(sqltype), e.g. "INTEGER", "NVARCHAR(160)"
    nullable: bool
    is_primary_key: bool
    sample_values: tuple[Any, ...]
    null_count: int
    distinct_count: int


@dataclass(frozen=True, slots=True)
class ForeignKeyInfo:
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]
    primary_key_columns: tuple[str, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...]
    row_count: int

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


def introspect(
    engine: Engine,
    *,
    sample_size: int = 5,
    sample_value_max_chars: int = 80,
) -> list[TableInfo]:
    """Return one `TableInfo` per user table in the engine's default schema.

    Per-column stats (`sample_values`, `null_count`, `distinct_count`) are
    sourced via SELECT-only queries against the live engine; for empty tables
    (`row_count == 0`) the stats are skipped and reported as empty/zero.

    `sample_value_max_chars` truncates very long string samples so that schema
    chunks stay embed-friendly.
    """
    insp = inspect(engine)
    table_names = sorted(insp.get_table_names())
    metadata = MetaData()

    tables: list[TableInfo] = []
    with engine.connect() as conn:
        for tname in table_names:
            sa_table = Table(tname, metadata, autoload_with=engine)
            row_count = conn.execute(select(func.count()).select_from(sa_table)).scalar_one()
            row_count_int = int(row_count or 0)

            pk_constraint = insp.get_pk_constraint(tname)
            pk_cols: tuple[str, ...] = tuple(pk_constraint.get("constrained_columns") or ())

            fk_records = insp.get_foreign_keys(tname)
            fks = tuple(
                ForeignKeyInfo(
                    columns=tuple(fk.get("constrained_columns") or ()),
                    referred_table=fk["referred_table"],
                    referred_columns=tuple(fk.get("referred_columns") or ()),
                )
                for fk in fk_records
                if fk.get("referred_table")
            )

            cols: list[ColumnInfo] = []
            for col_meta in insp.get_columns(tname):
                col_name = col_meta["name"]
                col_type = str(col_meta.get("type"))
                nullable = bool(col_meta.get("nullable", True))
                is_pk = col_name in pk_cols

                sa_col = sa_table.c[col_name]
                if row_count_int == 0:
                    samples: tuple[Any, ...] = ()
                    null_count = 0
                    distinct_count = 0
                else:
                    null_count = int(
                        conn.execute(
                            select(func.count()).select_from(sa_table).where(sa_col.is_(None))
                        ).scalar_one()
                        or 0
                    )
                    distinct_count = int(
                        conn.execute(
                            select(func.count(func.distinct(sa_col))).select_from(sa_table)
                        ).scalar_one()
                        or 0
                    )
                    samples = _top_k_samples(
                        conn,
                        sa_table,
                        sa_col,
                        k=sample_size,
                        max_chars=sample_value_max_chars,
                    )

                cols.append(
                    ColumnInfo(
                        name=col_name,
                        type=col_type,
                        nullable=nullable,
                        is_primary_key=is_pk,
                        sample_values=samples,
                        null_count=null_count,
                        distinct_count=distinct_count,
                    )
                )

            tables.append(
                TableInfo(
                    name=tname,
                    columns=tuple(cols),
                    primary_key_columns=pk_cols,
                    foreign_keys=fks,
                    row_count=row_count_int,
                )
            )

    return tables


def _top_k_samples(
    conn: Any,
    sa_table: Table,
    sa_col: Any,
    *,
    k: int,
    max_chars: int,
) -> tuple[Any, ...]:
    """Return top-k most frequent non-null values for `sa_col`, truncating
    long strings. Falls back to `()` if the dialect rejects the query (e.g.
    BLOB/JSON columns that can't be GROUP BY'd on some engines).
    """
    try:
        rows = conn.execute(
            select(sa_col, func.count())
            .where(sa_col.is_not(None))
            .group_by(sa_col)
            .order_by(func.count().desc(), sa_col)
            .limit(k)
        ).all()
    except SQLAlchemyError:
        return ()
    return tuple(_truncate(row[0], max_chars) for row in rows)


def _truncate(value: Any, max_chars: int) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[: max_chars - 1] + "…"
    return value
