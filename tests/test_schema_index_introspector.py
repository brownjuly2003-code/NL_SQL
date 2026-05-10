"""Unit tests for `nl_sql.schema_index.introspector` against a tiny in-memory
SQLite database. Verifies column types, PK/FK metadata, sample values,
null/distinct counts, and graceful handling of empty tables.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from nl_sql.schema_index.introspector import introspect


@pytest.fixture
def chinook_like_engine() -> Iterator[Engine]:
    """Two-table schema with a FK and one nullable column with NULL rows."""
    raw = sqlite3.connect(":memory:")
    raw.executescript(
        """
        CREATE TABLE artist (
            artist_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT  -- nullable
        );
        CREATE TABLE album (
            album_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            artist_id INTEGER NOT NULL,
            FOREIGN KEY (artist_id) REFERENCES artist(artist_id)
        );
        INSERT INTO artist (artist_id, name, country) VALUES
            (1, 'AC/DC', 'AU'),
            (2, 'Aerosmith', 'US'),
            (3, 'Accept', NULL),
            (4, 'AC/DC', 'AU');  -- duplicate name on purpose
        INSERT INTO album (album_id, title, artist_id) VALUES
            (10, 'Back in Black', 1),
            (11, 'Highway to Hell', 1),
            (12, 'Pump', 2);
        """
    )
    raw.commit()

    eng = create_engine("sqlite://", creator=lambda: raw, future=True)
    try:
        yield eng
    finally:
        raw.close()


def test_introspect_returns_table_alphabetically(chinook_like_engine: Engine) -> None:
    tables = introspect(chinook_like_engine, sample_size=3)
    assert [t.name for t in tables] == ["album", "artist"]


def test_introspect_captures_pk_and_row_count(chinook_like_engine: Engine) -> None:
    tables = {t.name: t for t in introspect(chinook_like_engine, sample_size=3)}

    artist = tables["artist"]
    assert artist.row_count == 4
    assert artist.primary_key_columns == ("artist_id",)

    album = tables["album"]
    assert album.row_count == 3
    assert album.primary_key_columns == ("album_id",)


def test_introspect_captures_foreign_keys(chinook_like_engine: Engine) -> None:
    tables = {t.name: t for t in introspect(chinook_like_engine, sample_size=3)}
    album = tables["album"]
    assert len(album.foreign_keys) == 1
    fk = album.foreign_keys[0]
    assert fk.columns == ("artist_id",)
    assert fk.referred_table == "artist"
    assert fk.referred_columns == ("artist_id",)


def test_introspect_column_stats(chinook_like_engine: Engine) -> None:
    tables = {t.name: t for t in introspect(chinook_like_engine, sample_size=5)}
    artist = tables["artist"]
    cols = {c.name: c for c in artist.columns}

    name = cols["name"]
    assert name.type == "TEXT"
    assert name.nullable is False
    assert name.is_primary_key is False
    assert name.null_count == 0
    assert name.distinct_count == 3  # AC/DC duplicates count once
    # Top-K most frequent first; the duplicate "AC/DC" leads.
    assert name.sample_values[0] == "AC/DC"

    country = cols["country"]
    assert country.nullable is True
    assert country.null_count == 1
    assert country.distinct_count == 2


def test_introspect_handles_empty_table() -> None:
    raw = sqlite3.connect(":memory:")
    try:
        raw.executescript("CREATE TABLE empty_t (id INTEGER PRIMARY KEY, label TEXT);")
        raw.commit()
        eng = create_engine("sqlite://", creator=lambda: raw, future=True)

        tables = introspect(eng, sample_size=3)
        assert len(tables) == 1
        t = tables[0]
        assert t.row_count == 0
        for col in t.columns:
            assert col.sample_values == ()
            assert col.null_count == 0
            assert col.distinct_count == 0
    finally:
        raw.close()


def test_introspect_truncates_long_string_samples() -> None:
    raw = sqlite3.connect(":memory:")
    try:
        long_value = "x" * 200
        raw.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT);")
        raw.execute("INSERT INTO t (id, body) VALUES (1, ?)", (long_value,))
        raw.commit()
        eng = create_engine("sqlite://", creator=lambda: raw, future=True)

        tables = introspect(eng, sample_size=3, sample_value_max_chars=20)
        body = next(c for c in tables[0].columns if c.name == "body")
        assert body.sample_values
        sampled = body.sample_values[0]
        assert isinstance(sampled, str)
        assert len(sampled) <= 20
        assert sampled.endswith("…")
    finally:
        raw.close()
