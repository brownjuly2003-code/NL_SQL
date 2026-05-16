"""Tests for ``nl_sql.render.labels``.

Closes audit P2 #5: scalar metric cards on the UI showed raw SQL expressions
(``COUNT(DISTINCT s.CDSCode)``) instead of business labels. The classifier
in ``labels.py`` translates these into stable kinds the UI can localize.
"""

from __future__ import annotations

import pytest

from nl_sql.render.labels import classify_scalar_label, humanize_scalar_label


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("COUNT(*)", "count"),
        ("COUNT(DISTINCT s.CDSCode)", "count"),
        ("count(id)", "count"),
        ("SUM(amount)", "sum"),
        ("sum(total)", "sum"),
        ("AVG(score)", "average"),
        ("average(price)", "average"),
        ("MIN(year)", "minimum"),
        ("MAX(year)", "maximum"),
    ],
)
def test_aggregate_functions(raw: str, expected: str) -> None:
    assert classify_scalar_label(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "a * 100.0 / b",
        "score - baseline",
        "revenue / customers",
        "(num + denom)",
    ],
)
def test_ratios_and_arithmetic(raw: str) -> None:
    assert classify_scalar_label(raw) == "ratio"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("total_revenue", "identifier"),
        ("name", "identifier"),
        ("schools_count", "identifier"),
        ("", "result"),
        ("   ", "result"),
    ],
)
def test_identifiers_and_empty(raw: str, expected: str) -> None:
    assert classify_scalar_label(raw) == expected


def test_count_with_extra_arithmetic_still_count() -> None:
    """``COUNT(*) * 1.0`` is still semantically a count — the aggregate
    function check fires before the ratio check."""
    assert classify_scalar_label("COUNT(*) * 1.0") == "count"


def test_humanize_with_fallback() -> None:
    """For identifier labels the engine column name *is* readable; the
    humanize wrapper preserves it via the fallback argument."""
    assert humanize_scalar_label("total_revenue") == "total_revenue"
    assert humanize_scalar_label("total_revenue", fallback="Revenue") == "Revenue"
    assert humanize_scalar_label("COUNT(*)", fallback="ignored") == "Count"
    assert humanize_scalar_label("") == "Result"
