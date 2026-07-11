"""Execution Accuracy (EA) — primary BIRD Mini-Dev metric.

Reference implementation: bird-bench/mini_dev `evaluation_ex.py`. The official
script does set-equality on row tuples after running gold + pred against the
same sqlite DB. We match that behaviour and add three guards:

1. Floats compared with absolute tolerance (1e-6) so trivial CAST/precision
   differences don't flip a correct query to a fail.
2. Rows are normalised to tuples; columns names are NOT compared (BIRD
   accepts any aliasing as long as values match).
3. ORDER BY in gold → order-sensitive comparison. Otherwise set equality.
   This is stricter than the stock BIRD script (which is always set-eq), but
   more honest: a "top 5 by sales" question with gold ORDER BY is wrong
   when the predicted result is in arbitrary order.

`compare_results` is the single source of truth used by `runner.py` and by
unit tests; `execution_accuracy(records)` aggregates a list of comparisons
into a percentage.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_FLOAT_TOLERANCE = 1e-6
_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ResultComparison:
    """Outcome of comparing one (gold, pred) row pair.

    `match` is the EA bit. `reason` describes why a comparison failed, used
    for slicing the report (e.g. "row count mismatch" vs "value mismatch").
    """

    match: bool
    reason: str = ""
    gold_rows: int = 0
    pred_rows: int = 0


def compare_results(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    *,
    gold_sql: str | None = None,
) -> ResultComparison:
    """Compare two result sets BIRD-style with two extensions.

    Default — BIRD-official set-equality on row tuples (so reported EA stays
    apples-to-apples with the BIRD Mini-Dev leaderboard, AskData+GPT-4o,
    CHESS, XiYan, etc.). A pred with ``DISTINCT`` over a gold without one is
    still a match if the underlying unique rows agree — which is exactly how
    the official `bird-bench/mini_dev/evaluation_ex.py` script scores it.

    Extensions on top of vanilla BIRD:

    - Float tolerance: ``abs(a - b) <= 1e-6``.
    - Order-sensitive iff ``gold_sql`` contains ``ORDER BY`` (case-insensitive).
      Pass ``gold_sql=None`` to force set-equality (matches stock BIRD).

    Earlier revisions of this function used multiset (``collections.Counter``)
    equality. That was strictly more conservative than BIRD's own scoring and
    silently penalised pred SQLs that legitimately deduplicated, making
    reported numbers incomparable to the leaderboard. Use the dedicated
    multiset helper below if you ever need strict-duplicate semantics.
    """
    gold_norm = [_normalise_row(r) for r in gold_rows]
    pred_norm = [_normalise_row(r) for r in pred_rows]

    order_sensitive = gold_sql is not None and bool(_ORDER_BY_RE.search(gold_sql))

    if order_sensitive:
        if len(gold_norm) != len(pred_norm):
            return ResultComparison(
                match=False,
                reason=f"ordered row count mismatch: gold={len(gold_norm)}, pred={len(pred_norm)}",
                gold_rows=len(gold_norm),
                pred_rows=len(pred_norm),
            )
        for i, (g, p) in enumerate(zip(gold_norm, pred_norm, strict=True)):
            if not _row_equal(g, p):
                return ResultComparison(
                    match=False,
                    reason=f"ordered row {i} mismatch: gold={g!r}, pred={p!r}",
                    gold_rows=len(gold_norm),
                    pred_rows=len(pred_norm),
                )
        return ResultComparison(match=True, gold_rows=len(gold_norm), pred_rows=len(pred_norm))

    gold_set = {_hashable(g) for g in gold_norm}
    pred_set = {_hashable(p) for p in pred_norm}
    if gold_set != pred_set:
        return ResultComparison(
            match=False,
            reason=f"set mismatch (unique rows differ): |gold|={len(gold_set)}, |pred|={len(pred_set)}",
            gold_rows=len(gold_norm),
            pred_rows=len(pred_norm),
        )
    return ResultComparison(match=True, gold_rows=len(gold_norm), pred_rows=len(pred_norm))


def safe_compare_pred(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    *,
    gold_sql: str | None = None,
    pred_failed: bool,
    gold_failed: bool = False,
) -> ResultComparison:
    """Comparison wrapper that short-circuits pred OR gold execution failures.

    Plain `compare_results` is row-level: it treats `pred_rows=[]` identically
    whether pred returned zero rows or pred raised before producing any. When
    gold also returns zero rows (BIRD quirks: empty filter results, missing
    Banned legalities, etc.), `compare_results([], [])` returns match=True —
    a silent false positive for malformed pred SQL.

    Symmetric defect on the gold side: `_execute_gold` historically returned
    `([], [])` when BIRD's gold SQL crashed (~1% of cases), and any pred that
    happened to also return zero rows would then be blessed as match=True.

    The runner's `_run_one` and `_run_one_via_pipeline` paths already route
    pred-failure and gold-failure through `_compare_outcome` / direct
    `ResultComparison(match=False)`. Voting and rescoring scripts that bypass
    the runner must use this helper instead of calling `compare_results`
    directly. Pass `pred_failed=True` when pred SQL raised, `gold_failed=True`
    when gold SQL raised.

    Discovered via Codex review of c74b46c → qid 518 (card_games moderate
    "format with most banned cards"): pred CTE missing the WITH prefix,
    SyntaxError on every execution, gold returns 0 rows for that DB, scoring
    blessed it as match=True since v13 (helallao grok-4.1-reasoning rescue).
    Re-merge v22-v29 + 2026-05-25 EOD fix lands the correction.
    Gold-side mirror is Codex audit 2026-05-25 #1 (`runner.py:960`).
    """
    if gold_failed:
        return ResultComparison(
            match=False,
            reason="gold execution failed",
            gold_rows=0,
            pred_rows=len(pred_rows),
        )
    if pred_failed:
        return ResultComparison(
            match=False,
            reason="pred execution failed",
            gold_rows=len(gold_rows),
            pred_rows=0,
        )
    return compare_results(gold_rows, pred_rows, gold_sql=gold_sql)


def execution_accuracy(matches: Sequence[bool]) -> float:
    """Return EA as a fraction in [0, 1]. Empty → 0.0."""
    if not matches:
        return 0.0
    return sum(1 for m in matches if m) / len(matches)


def _normalise_row(row: Sequence[Any]) -> tuple[Any, ...]:
    """Strip type quirks before comparison.

    - Decimal → float (BIRD gold has CAST AS REAL; some drivers return Decimal).
    - bytes → str (sqlite returns BLOB sometimes; strings compare by content).
    - Tuples preserved; everything else stays as-is.
    """
    return tuple(_normalise_cell(v) for v in row)


def _normalise_cell(value: Any) -> Any:
    if isinstance(value, bool):  # bool is a subclass of int — don't promote
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        # Postgres hands back numeric — AVG, SUM, any division — as Decimal, while
        # SQLite hands back float. Left as Decimal it skips the float tolerance
        # grid in `_hashable`, so a correct answer that differs from gold in the
        # 16th decimal lands in a different bucket and scores a miss. This line is
        # what the docstring above always claimed; it was never actually here, and
        # every Postgres ratio/average question paid for it.
        return float(value)
    if isinstance(value, float):
        # NaN compares unequal to itself; map all NaN to a sentinel so two
        # NaN rows from the same query compare equal.
        if value != value:
            return "__NaN__"
        return float(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def _row_equal(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
    if len(a) != len(b):
        return False
    return all(_cell_equal(x, y) for x, y in zip(a, b, strict=True))


def _cell_equal(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= _FLOAT_TOLERANCE
        except (TypeError, ValueError):
            return False
    return bool(a == b)


def _hashable(row: tuple[Any, ...]) -> tuple[Any, ...]:
    """Project a row into a hashable representation for set comparison.

    Every number — int, float, and (post-`_normalise_cell`) Decimal — goes onto
    the same tolerance grid, so 1.0000001, 1.0 and 1 all bucket together.
    Strings/None pass through.

    Quantising floats but *not* ints used to split the two apart: gold `5` hashed
    to 5 while pred `5.0` hashed to 5_000_000, and the set comparison called a
    correct answer a miss. That was stricter than BIRD's own scorer, which sets
    raw Python tuples where `5 == 5.0` and the two collapse — precisely the
    apples-to-apples property `compare_results` claims. The ordered path never
    had the bug (it compares with `_cell_equal`'s tolerance), so the same
    (gold, pred) pair scored differently depending on whether gold had ORDER BY.

    `bool` is a subclass of `int` and is quantised with them, keeping `True`
    equal to `1` exactly as a raw Python set would.

    Grid precision: `v / 1e-6` is exact for |v| < 2**53 / 1e6 ≈ 9e9 and stays
    injective (float step < 1e6) up to ~4.5e15 — far beyond any BIRD magnitude.
    """
    out: list[Any] = []
    for v in row:
        if isinstance(v, int | float):
            if isinstance(v, float) and v != v:  # NaN
                out.append("__NaN__")
            else:
                out.append(round(v / _FLOAT_TOLERANCE))
        else:
            out.append(v)
    return tuple(out)
