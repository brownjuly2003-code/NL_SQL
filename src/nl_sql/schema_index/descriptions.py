"""Load BIRD's per-column descriptions so the schema block carries meaning.

BIRD ships a `database_description/<table>.csv` next to every database. It is
where the dataset explains what its columns actually are — `sname` is "school
name", `dname` is "district segment", `StatusType` enumerates its own valid
values. Without them the model is left guessing from cryptic identifiers, and
BIRD's identifiers are cryptic on purpose: reading the descriptions is part of
the task. Every serious BIRD system feeds them to the model; this pipeline
never opened the files.

The CSVs are best-effort artefacts, not a contract: encodings vary
(utf-8-sig / cp1252), rows are ragged, and most `column_description` cells just
repeat the column name. We keep only what adds information, and a database with
no description directory (Chinook, any Postgres target) simply yields nothing.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

# One column's worth of prose, trimmed. Long enough for BIRD's real definitions
# ("the abbreviated street address of the school…"), short enough that 50-column
# tables don't crowd the schema out of the prompt.
_MAX_DESC = 90
_MAX_VALUE_DESC = 70

ColumnDescriptions = dict[str, dict[str, str]]
"""``table_name (lowercased) → column_name (lowercased) → description``."""


def load_column_descriptions(db_url: str) -> ColumnDescriptions:
    """Read `<db_dir>/database_description/*.csv` for a SQLite database path.

    Returns an empty mapping for anything that isn't a local file with a
    description directory — that is the normal case outside BIRD.
    """
    try:
        db_path = Path(db_url)
    except (TypeError, ValueError):
        return {}
    desc_dir = db_path.parent / "database_description"
    if not desc_dir.is_dir():
        return {}

    out: ColumnDescriptions = {}
    for csv_path in sorted(desc_dir.glob("*.csv")):
        columns = _load_one(csv_path)
        if columns:
            out[csv_path.stem.lower()] = columns
    return out


def _load_one(csv_path: Path) -> dict[str, str]:
    # utf-8-sig strips the BOM BIRD leaves on these files; cp1252 is the
    # fallback for the ones that carry Windows curly quotes and degree signs.
    raw = csv_path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")

    columns: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = _clean(row.get("original_column_name") or row.get("column_name"))
        if not name:
            continue
        described = _describe(row, name)
        if described:
            columns[name.lower()] = described
    return columns


def _describe(row: dict[str, str | None], name: str) -> str:
    """Compose one column's line, dropping cells that restate the column name."""
    desc = _clean(row.get("column_description"))
    value_desc = _clean(row.get("value_description"))

    parts: list[str] = []
    # A description that merely echoes the identifier teaches the model nothing;
    # BIRD fills a lot of cells that way ("CDSCode" → "CDSCode").
    if desc and not _echoes(desc, name):
        parts.append(_truncate(desc, _MAX_DESC))
    # Value descriptions carry the enums and units — often the deciding detail
    # for a WHERE clause. "unuseful" is BIRD's own placeholder for "ignore me".
    if value_desc and value_desc.lower() != "unuseful" and not _echoes(value_desc, name):
        parts.append(f"values: {_truncate(value_desc, _MAX_VALUE_DESC)}")
    return "; ".join(parts)


def _echoes(text: str, name: str) -> bool:
    squash = name.replace(" ", "").replace("_", "").lower()
    return text.replace(" ", "").replace("_", "").lower() == squash


def _clean(value: str | None) -> str:
    if not value:
        return ""
    # These cells are hand-typed: newlines, tabs and doubled spaces are common.
    return " ".join(value.split())


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
