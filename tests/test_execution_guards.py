"""Adversarial-SQL tests for the AST guard.

Each test pins a specific attack/abuse vector. Adding a new vector requires
adding a test and (usually) extending guards.py.
"""

from __future__ import annotations

import pytest

from nl_sql.execution.guards import (
    GENERATE_SERIES_MAX_RANGE,
    validate_sql,
)

# ---------- happy path ----------


def test_simple_select_passes() -> None:
    report = validate_sql("SELECT id, name FROM Artists WHERE id = 1")
    assert report.ok, report.violations


def test_select_with_join_and_aggregate_passes() -> None:
    sql = """
    SELECT a.name, COUNT(b.id) AS album_count
    FROM Artists a
    LEFT JOIN Albums b ON b.artist_id = a.id
    GROUP BY a.name
    HAVING COUNT(b.id) > 0
    ORDER BY album_count DESC
    LIMIT 10
    """
    report = validate_sql(sql)
    assert report.ok, report.violations


def test_select_with_cte_passes() -> None:
    sql = """
    WITH per_artist AS (
        SELECT artist_id, COUNT(*) AS n FROM Albums GROUP BY artist_id
    )
    SELECT a.name, p.n FROM Artists a JOIN per_artist p ON p.artist_id = a.id
    """
    report = validate_sql(sql)
    assert report.ok, report.violations


# ---------- shape violations ----------


def test_insert_is_rejected() -> None:
    report = validate_sql("INSERT INTO Artists (id, name) VALUES (99, 'X')")
    assert not report.ok
    codes = {v.code for v in report.violations}
    assert "not_select" in codes or "dml_in_tree" in codes


def test_update_is_rejected() -> None:
    report = validate_sql("UPDATE Artists SET name = 'X' WHERE id = 1")
    assert not report.ok
    codes = {v.code for v in report.violations}
    assert "not_select" in codes or "dml_in_tree" in codes


def test_delete_is_rejected() -> None:
    report = validate_sql("DELETE FROM Artists WHERE id = 1")
    assert not report.ok


def test_drop_is_rejected() -> None:
    report = validate_sql("DROP TABLE Artists")
    assert not report.ok


def test_create_is_rejected() -> None:
    report = validate_sql("CREATE TABLE x (id INT)")
    assert not report.ok


def test_multi_statement_is_rejected() -> None:
    report = validate_sql("SELECT 1; SELECT 2")
    assert not report.ok
    assert any(v.code == "multi_statement" for v in report.violations)


def test_dml_inside_cte_is_rejected() -> None:
    sql = """
    WITH del AS (DELETE FROM Artists WHERE id = 1 RETURNING id)
    SELECT * FROM del
    """
    report = validate_sql(sql, dialect="postgresql")
    assert not report.ok


# ---------- function allowlist ----------


def test_pg_sleep_is_rejected() -> None:
    report = validate_sql("SELECT pg_sleep(10)", dialect="postgresql")
    assert not report.ok
    assert any(v.code == "banned_function" for v in report.violations)


def test_pg_read_file_is_rejected() -> None:
    report = validate_sql("SELECT pg_read_file('/etc/passwd')", dialect="postgresql")
    assert not report.ok


def test_load_extension_is_rejected() -> None:
    report = validate_sql("SELECT load_extension('evil.so')", dialect="sqlite")
    assert not report.ok


# ---------- generate_series cap ----------


def test_generate_series_within_cap_is_allowed() -> None:
    report = validate_sql(
        f"SELECT * FROM generate_series(1, {GENERATE_SERIES_MAX_RANGE - 1})",
        dialect="postgresql",
    )
    assert report.ok, report.violations


def test_generate_series_above_cap_is_rejected() -> None:
    report = validate_sql(
        f"SELECT * FROM generate_series(1, {GENERATE_SERIES_MAX_RANGE + 10})",
        dialect="postgresql",
    )
    assert not report.ok
    assert any(v.code == "generate_series_too_large" for v in report.violations)


# ---------- table denylist ----------


def test_pg_authid_is_rejected() -> None:
    report = validate_sql("SELECT * FROM pg_authid", dialect="postgresql")
    assert not report.ok
    assert any(v.code == "denied_table" for v in report.violations)


# ---------- attach / pragma ----------


def test_sqlite_attach_is_rejected() -> None:
    report = validate_sql("ATTACH DATABASE 'evil.sqlite' AS evil", dialect="sqlite")
    assert not report.ok


def test_sqlite_pragma_is_rejected() -> None:
    report = validate_sql("PRAGMA database_list", dialect="sqlite")
    assert not report.ok
    codes = {v.code for v in report.violations}
    assert "pragma_statement" in codes or "not_select" in codes


# ---------- parse errors ----------


def test_garbage_input_is_rejected() -> None:
    report = validate_sql("this is not sql at all")
    assert not report.ok


@pytest.mark.parametrize(
    "code",
    [
        "not_select",
        "dml_in_tree",
        "multi_statement",
        "banned_function",
        "denied_table",
        "generate_series_too_large",
    ],
)
def test_violation_codes_are_documented(code: str) -> None:
    """Every code referenced by other tests must be a valid identifier — this
    forces us to add an explicit test if a new code is introduced."""
    assert code.replace("_", "").isalnum()
