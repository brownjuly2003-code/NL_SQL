"""Humanize raw column labels coming back from the SQL engine.

When the question is "How many schools are exclusively virtual?", the SQL is
``SELECT COUNT(DISTINCT s.CDSCode) ...`` and the engine returns a column
literally named ``COUNT(DISTINCT s.CDSCode)``. Streamlit's metric widget
shows this raw — engineering-correct, recruiter-hostile.

This module maps the raw label to a stable semantic key the UI can localize:

    >>> classify_scalar_label("COUNT(DISTINCT s.CDSCode)")
    'count'
    >>> classify_scalar_label("AVG(score)")
    'average'
    >>> classify_scalar_label("total_revenue")
    'identifier'
    >>> classify_scalar_label("")
    'result'

Keep the function pure / dependency-free so it can be unit-tested without
touching Streamlit.
"""

from __future__ import annotations

import re

ScalarLabelKind = str
"""One of: count, sum, average, minimum, maximum, ratio, identifier, result.

Returned as a plain string so callers can ``_t(f"scalar_label_{kind}")`` or
build their own lookup. New aggregation kinds can be added without bumping a
type alias."""

_AGGREGATE_PATTERNS: list[tuple[re.Pattern[str], ScalarLabelKind]] = [
    (re.compile(r"^\s*count\s*\(", re.IGNORECASE), "count"),
    (re.compile(r"^\s*sum\s*\(", re.IGNORECASE), "sum"),
    (re.compile(r"^\s*(avg|average)\s*\(", re.IGNORECASE), "average"),
    (re.compile(r"^\s*min\s*\(", re.IGNORECASE), "minimum"),
    (re.compile(r"^\s*max\s*\(", re.IGNORECASE), "maximum"),
]

_RATIO_PATTERN = re.compile(r"[+\-*/]")
"""A scalar label containing an arithmetic operator outside of a function
call is almost always a ratio / computed expression (``a*100.0/b``,
``a-b``, ``a/b``). The pattern is loose on purpose — `_classify_scalar_label`
checks it only *after* the aggregate functions, so ``COUNT(*) * 1.0``-style
labels still classify as ``count``."""

_LOOKS_LIKE_EXPRESSION = re.compile(r"[()*]")
"""Parens or ``*`` in a label = SQL expression, not a column name."""


def classify_scalar_label(raw: str) -> ScalarLabelKind:
    """Map an engine-returned column label to a UI-localizable kind.

    The classifier is intentionally simple — string-level pattern matching,
    no SQL parser. The pipeline already validated the SQL upstream
    (``execution/guards.py``) so we trust the shape; we only need to decide
    *what to show on the metric card* when the label is a raw expression.
    """
    if not raw or not raw.strip():
        return "result"

    for pattern, kind in _AGGREGATE_PATTERNS:
        if pattern.search(raw):
            return kind

    if _RATIO_PATTERN.search(raw):
        return "ratio"

    if _LOOKS_LIKE_EXPRESSION.search(raw):
        return "result"

    return "identifier"


def humanize_scalar_label(raw: str, *, fallback: str | None = None) -> str:
    """English-only convenience wrapper for callers that don't want to
    localize. Returns a short noun phrase suitable for ``st.metric(label, ...)``.

    Pass ``fallback`` to recover the raw label for the ``identifier`` case
    (where the engine's column name *was* readable, e.g. ``total_revenue``).
    """
    kind = classify_scalar_label(raw)
    if kind == "identifier":
        return fallback or raw
    return _ENGLISH_LABELS[kind]


_ENGLISH_LABELS: dict[ScalarLabelKind, str] = {
    "count": "Count",
    "sum": "Sum",
    "average": "Average",
    "minimum": "Minimum",
    "maximum": "Maximum",
    "ratio": "Ratio",
    "result": "Result",
}
