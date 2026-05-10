"""Deterministic format / chart-type picker.

Pure Python heuristics. No LLM call. Replaces the v1 plan that asked the LLM
to emit Vega-Lite specs (high failure rate per CX/KM review).

Decision tree (in order, first match wins):

1. Empty result -> Sentence("the query returned no rows")
2. 1 row, 1 column -> Scalar
3. <= 200 rows, >= 2 columns, first col temporal -> LineChart (with numeric Y cols)
4. 2 columns, <= 12 rows, col 0 categorical and col 1 numeric -> BarChart
   (or PieChart if it looks like a share-of-total breakdown)
5. 2 numeric columns, >= 6 rows -> ScatterChart
6. Otherwise -> Table
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from nl_sql.render.formats import (
    BarChart,
    LineChart,
    OutputFormat,
    PieChart,
    Scalar,
    ScatterChart,
    Sentence,
    Table,
)

_MAX_LINE_ROWS = 200
_MAX_BAR_ROWS = 12
_MAX_PIE_ROWS = 6
_MIN_SCATTER_ROWS = 6


def pick_format(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> OutputFormat:
    """Choose the right output format from the executed query result shape."""
    cols = list(columns)
    data = [list(r) for r in rows]
    n_rows = len(data)
    n_cols = len(cols)

    if n_rows == 0:
        return Sentence(text="the query returned no rows")

    if n_rows == 1 and n_cols == 1:
        return Scalar(value=data[0][0], column=cols[0])

    if n_cols >= 2 and _is_temporal_column(data, 0) and n_rows <= _MAX_LINE_ROWS:
        return LineChart(
            columns=cols,
            rows=data,
            x_field=cols[0],
            y_fields=[c for c in cols[1:] if _is_numeric_column(data, cols.index(c))],
        ) if any(_is_numeric_column(data, i) for i in range(1, n_cols)) else Table(
            columns=cols, rows=data
        )

    if (
        n_cols == 2
        and n_rows <= _MAX_BAR_ROWS
        and _is_categorical_column(data, 0)
        and _is_numeric_column(data, 1)
    ):
        if n_rows <= _MAX_PIE_ROWS and _looks_like_share(data):
            return PieChart(columns=cols, rows=data, x_field=cols[0], y_fields=[cols[1]])
        return BarChart(columns=cols, rows=data, x_field=cols[0], y_fields=[cols[1]])

    if (
        n_cols == 2
        and n_rows >= _MIN_SCATTER_ROWS
        and _is_numeric_column(data, 0)
        and _is_numeric_column(data, 1)
    ):
        return ScatterChart(columns=cols, rows=data, x_field=cols[0], y_fields=[cols[1]])

    return Table(columns=cols, rows=data)


def _is_temporal_column(rows: Sequence[Sequence[Any]], idx: int) -> bool:
    if not rows:
        return False
    sample = [row[idx] for row in rows if row[idx] is not None][:10]
    if not sample:
        return False
    if all(isinstance(v, dt.date | dt.datetime) for v in sample):
        return True
    return all(isinstance(v, str) and _looks_like_iso_date(v) for v in sample)


def _looks_like_iso_date(s: str) -> bool:
    if len(s) < 7:
        return False
    try:
        dt.date.fromisoformat(s[:10])
    except ValueError:
        return False
    return True


def _is_numeric_column(rows: Sequence[Sequence[Any]], idx: int) -> bool:
    if not rows:
        return False
    sample = [row[idx] for row in rows if row[idx] is not None][:20]
    if not sample:
        return False
    return all(isinstance(v, int | float) and not isinstance(v, bool) for v in sample)


def _is_categorical_column(rows: Sequence[Sequence[Any]], idx: int) -> bool:
    if not rows:
        return False
    sample = [row[idx] for row in rows if row[idx] is not None][:20]
    if not sample:
        return False
    if _is_numeric_column(rows, idx):
        return False
    return all(isinstance(v, str) for v in sample)


def _looks_like_share(rows: Sequence[Sequence[Any]]) -> bool:
    """Heuristic: looks like a share-of-total breakdown if the numeric column
    is non-negative and the largest category is < 80% of the total."""
    values = [row[1] for row in rows if isinstance(row[1], int | float) and not isinstance(row[1], bool)]
    if len(values) < 2 or any(v < 0 for v in values):
        return False
    total = sum(values)
    if total <= 0:
        return False
    return max(values) / total < 0.80
