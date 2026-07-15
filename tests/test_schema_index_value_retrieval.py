"""Unit tests for CHESS-style question-driven value retrieval."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from nl_sql.schema_index.value_retrieval import (
    extract_query_phrases,
    format_value_grounding,
    retrieve_value_matches,
)


@pytest.fixture
def value_engine() -> Iterator[Engine]:
    raw = sqlite3.connect(":memory:")
    raw.executescript(
        """
        CREATE TABLE schools (
            id INTEGER PRIMARY KEY,
            "District Name" TEXT NOT NULL,
            City TEXT NOT NULL
        );
        CREATE TABLE comics (
            id INTEGER PRIMARY KEY,
            publisher TEXT NOT NULL,
            title TEXT NOT NULL
        );
        INSERT INTO schools ("District Name", City) VALUES
            ('Riverside Unified', 'Riverside'),
            ('Oakland Unified', 'Oakland'),
            ('San Diego Unified', 'San Diego');
        INSERT INTO comics (publisher, title) VALUES
            ('Marvel Comics', 'X-Men'),
            ('DC Comics', 'Batman'),
            ('Image Comics', 'Spawn');
        """
    )
    raw.commit()
    eng = create_engine("sqlite://", creator=lambda: raw, future=True)
    try:
        yield eng
    finally:
        eng.dispose()
        raw.close()


def test_extract_query_phrases_prefers_quoted_and_long() -> None:
    phrases = extract_query_phrases('How many schools in "Riverside Unified"? Hint: district only')
    assert "Riverside Unified" in phrases
    # Stopwords dropped.
    assert "How" not in phrases
    assert "many" not in {p.casefold() for p in phrases}


def test_retrieve_value_matches_exact_district(value_engine: Engine) -> None:
    matches = retrieve_value_matches(
        value_engine,
        'Schools in the "Riverside Unified" district',
        ["schools", "comics"],
    )
    assert matches
    assert any(m.value == "Riverside Unified" and m.column == "District Name" for m in matches)


def test_retrieve_value_matches_publisher(value_engine: Engine) -> None:
    matches = retrieve_value_matches(
        value_engine,
        "List titles from Marvel Comics",
        ["comics"],
    )
    assert any(m.value == "Marvel Comics" and m.column == "publisher" for m in matches)


def test_retrieve_value_matches_empty_without_tables(value_engine: Engine) -> None:
    assert retrieve_value_matches(value_engine, "Marvel Comics", []) == []


def test_format_value_grounding_empty() -> None:
    assert format_value_grounding([]) == ""


def test_format_value_grounding_lists_matches(value_engine: Engine) -> None:
    matches = retrieve_value_matches(
        value_engine,
        "Marvel Comics publisher",
        ["comics"],
        max_matches=3,
    )
    text = format_value_grounding(matches)
    assert "Value grounding" in text
    assert "Marvel Comics" in text
    assert "comics.publisher" in text
