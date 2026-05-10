"""Unit tests for BIRD dataset loader + dev_split + extract_gold_tables."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl_sql.eval.dataset import (
    BirdExample,
    dev_split,
    extract_gold_tables,
    is_in_dev_split,
    load_bird_mini_dev,
)


@pytest.fixture
def fake_bird_root(tmp_path: Path) -> Path:
    root = tmp_path / "MINIDEV"
    root.mkdir()
    payload = [
        {
            "question_id": 100,
            "db_id": "fake_db",
            "question": "How many albums are there?",
            "evidence": "",
            "SQL": "SELECT COUNT(*) FROM Album",
            "difficulty": "simple",
        },
        {
            "question_id": 101,
            "db_id": "fake_db",
            "question": "Top 5 artists by sales",
            "evidence": "sales = SUM(invoice.total)",
            "SQL": "SELECT a.name FROM Artist a JOIN Album al ON a.id = al.artist_id",
            "difficulty": "moderate",
        },
        {
            "question_id": 102,
            "db_id": "other_db",
            "question": "Avg consumption",
            "evidence": "",
            "SQL": "SELECT AVG(c) FROM yearmonth",
            "difficulty": "challenging",
        },
    ]
    (root / "mini_dev_sqlite.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return root


def test_load_bird_mini_dev_parses_all_fields(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    assert len(examples) == 3
    first = examples[0]
    assert isinstance(first, BirdExample)
    assert first.question_id == 100
    assert first.db_id == "fake_db"
    assert first.registry_db_id == "bird_fake_db"
    assert first.dialect == "sqlite"
    assert first.difficulty == "simple"


def test_load_bird_mini_dev_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_bird_mini_dev(tmp_path / "MINIDEV")


def test_dev_split_deterministic_across_calls(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    a = dev_split(examples, n=2, seed=0)
    b = dev_split(examples, n=2, seed=0)
    assert [e.question_id for e in a] == [e.question_id for e in b]


def test_dev_split_different_seed_can_differ(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    a = dev_split(examples, n=2, seed=0)
    b = dev_split(examples, n=2, seed=42)
    # With only 3 examples this is *occasionally* equal; either way the
    # test asserts the function does not crash and returns the right size.
    assert len(a) == 2
    assert len(b) == 2


def test_dev_split_stable_prefix_property(fake_bird_root: Path) -> None:
    """Growing n at the same seed must keep all earlier IDs.

    Without this, every cache hit from the smaller slice is wasted when
    we bump to n=100 or n=200. Property: set(n=2) ⊆ set(n=3).
    """
    examples = load_bird_mini_dev(fake_bird_root)
    small = {e.question_id for e in dev_split(examples, n=2, seed=0)}
    large = {e.question_id for e in dev_split(examples, n=3, seed=0)}
    assert small.issubset(large)


def test_dev_split_n_exceeds_pool_returns_all_sorted(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    result = dev_split(examples, n=999)
    assert len(result) == len(examples)
    assert [e.question_id for e in result] == sorted(e.question_id for e in examples)


def test_dev_split_n_zero_returns_empty(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    assert dev_split(examples, n=0) == []


class TestExtractGoldTables:
    def test_basic_from(self) -> None:
        assert extract_gold_tables("SELECT * FROM Album") == ["Album"]

    def test_join(self) -> None:
        sql = "SELECT a.name FROM Artist a JOIN Album al ON a.id = al.artist_id"
        assert set(extract_gold_tables(sql)) == {"Artist", "Album"}

    def test_quoted_identifier(self) -> None:
        assert extract_gold_tables('SELECT * FROM "Album"') == ["Album"]

    def test_schema_qualified(self) -> None:
        assert extract_gold_tables("SELECT * FROM main.Album") == ["Album"]

    def test_dedupe(self) -> None:
        sql = "SELECT * FROM Album JOIN Album b ON Album.id = b.id"
        assert extract_gold_tables(sql) == ["Album"]

    def test_correlated_subquery_in_where(self) -> None:
        """Tables referenced only inside WHERE subqueries used to escape
        the regex; sqlglot AST walks them."""
        sql = (
            "SELECT a.id FROM Album a "
            "WHERE a.artist_id IN (SELECT id FROM Artist WHERE country = 'US') "
            "AND a.id > (SELECT MIN(id) FROM Track)"
        )
        assert set(extract_gold_tables(sql)) == {"Album", "Artist", "Track"}

    def test_in_subquery_only(self) -> None:
        sql = (
            "SELECT name FROM Customer "
            "WHERE id IN (SELECT customer_id FROM Invoice WHERE total > 100)"
        )
        assert set(extract_gold_tables(sql)) == {"Customer", "Invoice"}

    def test_cte_alias_excluded(self) -> None:
        """CTE names should not count as base tables; only the underlying
        base table referenced inside the CTE body should be returned."""
        sql = (
            "WITH RecentInvoices AS (SELECT * FROM Invoice WHERE date > '2020') "
            "SELECT i.id FROM RecentInvoices i JOIN Customer c ON i.cust_id = c.id"
        )
        result = set(extract_gold_tables(sql))
        assert "Invoice" in result
        assert "Customer" in result
        assert "RecentInvoices" not in result

    def test_unparseable_falls_back_to_regex(self) -> None:
        """Strange dialect quirks should not crash — return something."""
        # Garbled but with FROM word — regex fallback returns "Album"
        bad = "SELECT @!#$ FROM Album WHERE !!? not_valid_syntax"
        result = extract_gold_tables(bad)
        assert "Album" in result


def test_is_in_dev_split_exact_match(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    assert is_in_dev_split("How many albums are there?", examples)


def test_is_in_dev_split_paraphrase_is_not_leakage(fake_bird_root: Path) -> None:
    examples = load_bird_mini_dev(fake_bird_root)
    assert not is_in_dev_split("count of albums", examples)
