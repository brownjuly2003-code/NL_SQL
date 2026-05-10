"""Render `TableInfo` records into embed-ready `SchemaChunk`s.

Per docs/02_architecture_v2.md §4: ONE chunk per table. The chunk's `text` is
what we embed; `metadata` carries structured fields the retriever needs at
filter time (db_id, table name, FK targets) without re-parsing the rendered
text. Business-term hints are intentionally a thin stub — populated later from
a glossary file once we have one (see `03_eval_methodology.md` §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl_sql.schema_index.introspector import TableInfo

BusinessHints = dict[str, list[str]]
"""Map ``table_name → list[hint]``. Each hint is a short ≤80-char phrase
('active customer = invoice in last 90 days') merged into the chunk text."""


@dataclass(frozen=True, slots=True)
class SchemaChunk:
    """One embedded record per table.

    `chunk_id` is stable across re-indexing runs (same db + table → same id),
    so Chroma upserts replace stale chunks instead of duplicating them.
    """

    chunk_id: str
    db_id: str
    table_name: str
    text: str
    fk_targets: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


def to_chunks(
    tables: list[TableInfo],
    db_id: str,
    *,
    business_hints: BusinessHints | None = None,
) -> list[SchemaChunk]:
    """Render one chunk per table.

    `business_hints` (optional) attaches 1-2 domain phrases per table — kept
    out of the chunk if missing rather than guessed by the LLM. Same hints
    appear verbatim in chunk text and in metadata for downstream display.
    """
    hints_map = business_hints or {}
    return [_chunk_for_table(t, db_id=db_id, hints=hints_map.get(t.name, [])) for t in tables]


def _chunk_for_table(table: TableInfo, *, db_id: str, hints: list[str]) -> SchemaChunk:
    text = _render_table_text(table, hints=hints)
    fk_targets = tuple(sorted({fk.referred_table for fk in table.foreign_keys}))
    metadata = {
        "db_id": db_id,
        "table_name": table.name,
        "row_count": table.row_count,
        "column_count": len(table.columns),
        "primary_key": ",".join(table.primary_key_columns),
        "fk_targets": ",".join(fk_targets),
        "business_hints": " | ".join(hints),
    }
    return SchemaChunk(
        chunk_id=f"{db_id}::{table.name}",
        db_id=db_id,
        table_name=table.name,
        text=text,
        fk_targets=fk_targets,
        metadata=metadata,
    )


def _render_table_text(table: TableInfo, *, hints: list[str]) -> str:
    """Pretty multi-line description used as the embedded text body.

    Layout (stable for snapshot-style tests and for prompt rendering downstream):

        Table: <name> (rows=<n>)
        Primary key: <cols>
        Columns:
          - <col>: <type> [PK] [NULL?] | nulls=<n>, distinct=<n> | samples: v1, v2, v3
          ...
        Foreign keys:
          - (<col>, ...) -> <other_table>(<col>, ...)
        Business hints:
          - <hint>
    """
    lines: list[str] = [f"Table: {table.name} (rows={table.row_count})"]
    if table.primary_key_columns:
        lines.append(f"Primary key: {', '.join(table.primary_key_columns)}")

    lines.append("Columns:")
    for col in table.columns:
        flags: list[str] = []
        if col.is_primary_key:
            flags.append("PK")
        flags.append("NULL" if col.nullable else "NOT NULL")
        null_pct = _null_pct(col.null_count, table.row_count)
        stats = f"nulls={col.null_count} ({null_pct})" if table.row_count else "empty"
        stats += f", distinct={col.distinct_count}"
        samples = _format_samples(col.sample_values)
        suffix = f" | samples: {samples}" if samples else ""
        lines.append(
            f"  - {col.name}: {col.type} [{' '.join(flags)}] | {stats}{suffix}"
        )

    if table.foreign_keys:
        lines.append("Foreign keys:")
        for fk in table.foreign_keys:
            local = ", ".join(fk.columns)
            remote = ", ".join(fk.referred_columns)
            lines.append(f"  - ({local}) -> {fk.referred_table}({remote})")

    if hints:
        lines.append("Business hints:")
        lines.extend(f"  - {h}" for h in hints)

    return "\n".join(lines)


def _null_pct(null_count: int, row_count: int) -> str:
    if row_count <= 0:
        return "0%"
    pct = 100.0 * null_count / row_count
    return f"{pct:.0f}%" if pct >= 1 else f"{pct:.1f}%"


def _format_samples(values: tuple[Any, ...]) -> str:
    if not values:
        return ""
    rendered = [_format_one(v) for v in values]
    return ", ".join(rendered)


def _format_one(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return repr(value)
    return str(value)
