"""Tests for BIRD's per-column descriptions feeding the schema block.

BIRD names its columns cryptically (`sname`, `dname`, `Enroll12`) and explains
them in `database_description/<table>.csv`. The pipeline never read those files,
so the model was guessing what the columns meant.
"""

from __future__ import annotations

from pathlib import Path

from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.descriptions import load_column_descriptions
from nl_sql.schema_index.introspector import ColumnInfo, TableInfo


def _write_description_csv(db_dir: Path, table: str, rows: str, *, encoding: str = "utf-8") -> None:
    desc_dir = db_dir / "database_description"
    desc_dir.mkdir(exist_ok=True)
    header = "original_column_name,column_name,column_description,data_format,value_description\n"
    (desc_dir / f"{table}.csv").write_text(header + rows, encoding=encoding)


def test_loads_descriptions_and_value_enums(tmp_path: Path) -> None:
    _write_description_csv(
        tmp_path,
        "satscores",
        "sname,,school name,text,\ncharter,,identifies a charter school,integer,1 = charter\n",
    )
    loaded = load_column_descriptions(str(tmp_path / "db.sqlite"))
    assert loaded["satscores"]["sname"] == "school name"
    assert loaded["satscores"]["charter"] == ("identifies a charter school; values: 1 = charter")


def test_drops_cells_that_only_restate_the_column_name(tmp_path: Path) -> None:
    """BIRD fills a lot of rows with `CDSCode -> "CDSCode"`. That teaches nothing
    and would just pad the prompt."""
    _write_description_csv(tmp_path, "frpm", "CDSCode,,CDSCode,integer,\n")
    assert load_column_descriptions(str(tmp_path / "db.sqlite")) == {}


def test_drops_birds_own_unuseful_placeholder(tmp_path: Path) -> None:
    _write_description_csv(tmp_path, "satscores", "rtype,,rtype,text,unuseful\n")
    assert load_column_descriptions(str(tmp_path / "db.sqlite")) == {}


def test_database_without_descriptions_yields_nothing(tmp_path: Path) -> None:
    """Chinook and every Postgres target have no description directory."""
    assert load_column_descriptions(str(tmp_path / "chinook.sqlite")) == {}


def test_bom_and_cp1252_files_are_read(tmp_path: Path) -> None:
    """BIRD ships these with a BOM, and some carry Windows curly quotes."""
    _write_description_csv(
        tmp_path,
        "schools",
        "StreetAbr,,the school’s address,text,\n",  # noqa: RUF001 — the curly quote is the point
        encoding="utf-8-sig",
    )
    loaded = load_column_descriptions(str(tmp_path / "db.sqlite"))
    assert loaded["schools"]["streetabr"] == "the school’s address"  # noqa: RUF001


def test_long_description_is_truncated(tmp_path: Path) -> None:
    long_text = "x" * 300
    _write_description_csv(tmp_path, "schools", f"SOC,,{long_text},integer,\n")
    described = load_column_descriptions(str(tmp_path / "db.sqlite"))["schools"]["soc"]
    assert len(described) < 100
    assert described.endswith("…")


def test_descriptions_reach_the_schema_chunk() -> None:
    table = TableInfo(
        name="satscores",
        columns=[
            ColumnInfo(
                name="sname",
                type="TEXT",
                nullable=True,
                is_primary_key=False,
                null_count=0,
                distinct_count=10,
                sample_values=("Lowell",),
            )
        ],
        primary_key_columns=[],
        foreign_keys=[],
        row_count=10,
    )
    chunks = to_chunks(
        [table],
        db_id="bird_california_schools",
        column_descriptions={"satscores": {"sname": "school name"}},
    )
    assert "-- school name" in chunks[0].text
    # The samples must survive: they are what the model copies into WHERE literals.
    assert "samples: 'Lowell'" in chunks[0].text


def test_chunk_without_descriptions_is_unchanged() -> None:
    table = TableInfo(
        name="Album",
        columns=[
            ColumnInfo(
                name="Title",
                type="TEXT",
                nullable=False,
                is_primary_key=False,
                null_count=0,
                distinct_count=5,
                sample_values=(),
            )
        ],
        primary_key_columns=[],
        foreign_keys=[],
        row_count=5,
    )
    text = to_chunks([table], db_id="chinook")[0].text
    assert "--" not in text
