"""Unit tests for `nl_sql.schema_index.chunker.to_chunks`.

We feed synthetic `TableInfo` records (no DB) to keep these tests fast
and to pin the rendered text format that downstream prompts rely on.
"""

from __future__ import annotations

from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.introspector import ColumnInfo, ForeignKeyInfo, TableInfo


def _table(
    name: str,
    columns: list[ColumnInfo],
    pk: tuple[str, ...] = (),
    fks: tuple[ForeignKeyInfo, ...] = (),
    row_count: int = 100,
) -> TableInfo:
    return TableInfo(
        name=name,
        columns=tuple(columns),
        primary_key_columns=pk,
        foreign_keys=fks,
        row_count=row_count,
    )


def test_chunk_id_is_db_scoped_and_stable() -> None:
    table = _table(
        "Album",
        [
            ColumnInfo("AlbumId", "INTEGER", False, True, (1, 2, 3), 0, 347),
        ],
        pk=("AlbumId",),
    )
    [chunk] = to_chunks([table], db_id="chinook")
    assert chunk.chunk_id == "chinook::Album"
    assert chunk.db_id == "chinook"
    assert chunk.table_name == "Album"


def test_chunk_metadata_carries_fk_targets_and_pk() -> None:
    table = _table(
        "Album",
        [ColumnInfo("AlbumId", "INTEGER", False, True, (1,), 0, 347)],
        pk=("AlbumId",),
        fks=(
            ForeignKeyInfo(("ArtistId",), "Artist", ("ArtistId",)),
            ForeignKeyInfo(("PublisherId",), "Publisher", ("Id",)),
        ),
    )
    [chunk] = to_chunks([table], db_id="chinook")
    assert chunk.fk_targets == ("Artist", "Publisher")
    assert chunk.metadata["primary_key"] == "AlbumId"
    assert chunk.metadata["fk_targets"] == "Artist,Publisher"
    assert chunk.metadata["row_count"] == 100
    assert chunk.metadata["column_count"] == 1


def test_chunk_text_contains_table_columns_and_samples() -> None:
    table = _table(
        "Customer",
        [
            ColumnInfo("CustomerId", "INTEGER", False, True, (1, 2), 0, 59),
            ColumnInfo("Country", "TEXT", True, False, ("USA", "Canada"), 0, 24),
        ],
        pk=("CustomerId",),
    )
    [chunk] = to_chunks([table], db_id="chinook")
    text = chunk.text
    assert "Table: Customer (rows=100)" in text
    assert "Primary key: CustomerId" in text
    assert "CustomerId: INTEGER [PK NOT NULL]" in text
    assert "Country: TEXT [NULL]" in text
    assert "samples: 'USA', 'Canada'" in text
    assert "distinct=24" in text


def test_chunk_text_emits_foreign_keys_block() -> None:
    table = _table(
        "Album",
        [ColumnInfo("AlbumId", "INTEGER", False, True, (1,), 0, 347)],
        pk=("AlbumId",),
        fks=(ForeignKeyInfo(("ArtistId",), "Artist", ("ArtistId",)),),
    )
    [chunk] = to_chunks([table], db_id="chinook")
    assert "Foreign keys:" in chunk.text
    assert "(ArtistId) -> Artist(ArtistId)" in chunk.text


def test_chunk_text_includes_business_hints_when_provided() -> None:
    table = _table(
        "Customer",
        [ColumnInfo("CustomerId", "INTEGER", False, True, (1,), 0, 59)],
        pk=("CustomerId",),
    )
    [chunk] = to_chunks(
        [table],
        db_id="chinook",
        business_hints={"Customer": ["active = invoice in last 90 days"]},
    )
    assert "Business hints:" in chunk.text
    assert "active = invoice in last 90 days" in chunk.text
    assert chunk.metadata["business_hints"] == "active = invoice in last 90 days"


def test_chunk_text_handles_empty_table_gracefully() -> None:
    table = _table(
        "Empty",
        [ColumnInfo("Id", "INTEGER", False, True, (), 0, 0)],
        pk=("Id",),
        row_count=0,
    )
    [chunk] = to_chunks([table], db_id="x")
    assert "rows=0" in chunk.text
    assert "empty" in chunk.text  # the "empty" stats marker
    assert "samples:" not in chunk.text
