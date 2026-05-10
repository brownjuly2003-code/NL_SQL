"""Tests for the deterministic format picker.

The picker is a pure function over (columns, rows). Each test pins one branch
of the decision tree so we can refactor the heuristics without regressing.
"""

from __future__ import annotations

import datetime as dt

from nl_sql.render import (
    BarChart,
    LineChart,
    PieChart,
    Scalar,
    ScatterChart,
    Sentence,
    Table,
    pick_format,
)


def test_empty_result_yields_sentence() -> None:
    fmt = pick_format(["x"], [])
    assert isinstance(fmt, Sentence)
    assert "no rows" in fmt.text


def test_single_scalar_yields_scalar() -> None:
    fmt = pick_format(["count"], [[42]])
    assert isinstance(fmt, Scalar)
    assert fmt.value == 42
    assert fmt.column == "count"


def test_temporal_axis_yields_line_chart() -> None:
    rows = [
        [dt.date(2024, 1, 1), 10],
        [dt.date(2024, 2, 1), 20],
        [dt.date(2024, 3, 1), 15],
    ]
    fmt = pick_format(["month", "value"], rows)
    assert isinstance(fmt, LineChart)
    assert fmt.x_field == "month"
    assert fmt.y_fields == ["value"]


def test_iso_date_string_axis_also_yields_line() -> None:
    rows = [
        ["2024-01-01", 10],
        ["2024-02-01", 20],
        ["2024-03-01", 15],
    ]
    fmt = pick_format(["month", "value"], rows)
    assert isinstance(fmt, LineChart)


def test_small_categorical_yields_bar_chart() -> None:
    rows = [
        ["Rock", 250],
        ["Pop", 180],
        ["Jazz", 90],
    ]
    fmt = pick_format(["genre", "n_tracks"], rows)
    assert isinstance(fmt, BarChart | PieChart)
    assert fmt.x_field == "genre"


def test_bar_falls_back_for_skewed_categories() -> None:
    """When one category dominates (>= 80%), pie chart is misleading; bar wins."""
    rows = [
        ["Rock", 950],
        ["Pop", 30],
        ["Jazz", 20],
    ]
    fmt = pick_format(["genre", "n_tracks"], rows)
    assert isinstance(fmt, BarChart)


def test_two_numeric_columns_yields_scatter() -> None:
    rows = [[float(i), float(i * 2 + 1)] for i in range(10)]
    fmt = pick_format(["price", "quantity"], rows)
    assert isinstance(fmt, ScatterChart)


def test_many_rows_two_cols_yields_table_when_neither_temporal_nor_numeric_pair() -> None:
    rows = [["Customer " + str(i), "USA"] for i in range(50)]
    fmt = pick_format(["name", "country"], rows)
    assert isinstance(fmt, Table)


def test_many_rows_yields_table() -> None:
    rows = [[i, f"name_{i}"] for i in range(100)]
    fmt = pick_format(["id", "name"], rows)
    assert isinstance(fmt, Table)


def test_three_columns_yields_table_when_first_not_temporal() -> None:
    rows = [
        ["Rock", 250, 4.2],
        ["Pop", 180, 4.1],
        ["Jazz", 90, 4.5],
    ]
    fmt = pick_format(["genre", "n_tracks", "avg_rating"], rows)
    assert isinstance(fmt, Table)


def test_temporal_with_multiple_y_fields_yields_line_with_all() -> None:
    rows = [
        ["2024-01-01", 10, 100],
        ["2024-02-01", 20, 110],
        ["2024-03-01", 15, 120],
    ]
    fmt = pick_format(["month", "active_users", "revenue"], rows)
    assert isinstance(fmt, LineChart)
    assert fmt.y_fields == ["active_users", "revenue"]


def test_temporal_with_no_numeric_y_falls_back_to_table() -> None:
    rows = [
        ["2024-01-01", "ok"],
        ["2024-02-01", "ok"],
    ]
    fmt = pick_format(["month", "status"], rows)
    assert isinstance(fmt, Table)


def test_null_values_do_not_break_temporal_detection() -> None:
    rows = [
        [None, 10],
        [dt.date(2024, 1, 1), 20],
        [dt.date(2024, 2, 1), 30],
    ]
    fmt = pick_format(["month", "value"], rows)
    assert isinstance(fmt, LineChart)


def test_bool_column_not_treated_as_numeric() -> None:
    rows = [
        [True, 10],
        [False, 20],
    ]
    fmt = pick_format(["flag", "value"], rows)
    assert isinstance(fmt, Table)
