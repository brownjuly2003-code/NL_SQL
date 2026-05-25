"""Unit tests for execution_accuracy + schema_recall metrics."""

from __future__ import annotations

from nl_sql.eval.metrics.execution_accuracy import (
    compare_results,
    execution_accuracy,
    safe_compare_pred,
)
from nl_sql.eval.metrics.schema_recall import schema_recall_at_k


class TestSafeComparePred:
    """Regression guards for the 2026-05-25 fix (CX [P2] from c74b46c review).

    Before the fix, qid 518 v13 helallao rescue silently sat at match=True
    across the v22-v29 chain because pred SQL was syntactically broken
    (`compare_results([], [])` returns match=True when gold is also empty).
    """

    def test_pred_failed_short_circuits_to_false_even_when_both_empty(self) -> None:
        # Reproduces the qid 518 pattern: gold=[], pred=[] but pred actually
        # raised on execution. Plain compare_results returns match=True;
        # safe_compare_pred must return match=False when pred_failed=True.
        cmp = safe_compare_pred([], [], pred_failed=True)
        assert not cmp.match
        assert cmp.reason == "pred execution failed"
        # Sanity: plain compare_results would incorrectly bless this.
        baseline = compare_results([], [])
        assert baseline.match  # the bug the wrapper guards against

    def test_pred_succeeded_passes_through_to_compare_results(self) -> None:
        gold = [(1, "a"), (2, "b")]
        pred = [(2, "b"), (1, "a")]
        cmp = safe_compare_pred(gold, pred, pred_failed=False)
        assert cmp.match

    def test_pred_failed_but_gold_nonempty_still_false(self) -> None:
        cmp = safe_compare_pred([(1,), (2,)], [], pred_failed=True)
        assert not cmp.match
        assert cmp.gold_rows == 2
        assert cmp.pred_rows == 0

    def test_gold_failed_short_circuits_to_false_even_when_both_empty(self) -> None:
        # Codex audit 2026-05-25 #1 — gold-side mirror of the qid 518 bug.
        # _execute_gold returned ([], []) when BIRD gold crashed; if pred also
        # happened to return zero rows, compare_results([], []) blessed match=True.
        cmp = safe_compare_pred([], [], pred_failed=False, gold_failed=True)
        assert not cmp.match
        assert cmp.reason == "gold execution failed"
        # gold_failed takes precedence over pred_failed in the reason field
        # because gold-side failure invalidates the whole scoring attempt.
        cmp2 = safe_compare_pred([], [], pred_failed=True, gold_failed=True)
        assert not cmp2.match
        assert cmp2.reason == "gold execution failed"

    def test_gold_failed_with_nonempty_pred_still_false(self) -> None:
        cmp = safe_compare_pred([], [(1, "a")], pred_failed=False, gold_failed=True)
        assert not cmp.match
        assert cmp.gold_rows == 0
        assert cmp.pred_rows == 1


class TestCompareResults:
    def test_identical_rows_match_set_eq(self) -> None:
        gold = [(1, "a"), (2, "b")]
        pred = [(2, "b"), (1, "a")]
        c = compare_results(gold, pred)
        assert c.match
        assert c.gold_rows == 2
        assert c.pred_rows == 2

    def test_set_size_mismatch_fails(self) -> None:
        # gold has 2 unique rows, pred has 1 — sets differ, no match.
        gold = [(1,), (2,)]
        pred = [(1,)]
        c = compare_results(gold, pred)
        assert not c.match
        assert "set mismatch" in c.reason

    def test_duplicate_in_gold_with_extra_value_in_pred(self) -> None:
        # gold = {1}, pred = {1, 2} → sets differ → not a match.
        # BIRD-official set semantics: dedup before comparing.
        gold = [(1,), (1,)]
        pred = [(1,), (2,)]
        c = compare_results(gold, pred)
        assert not c.match

    def test_distinct_vs_non_distinct_is_match_under_bird_set(self) -> None:
        # Real-world case (BIRD qid 407): gold returns rows with duplicates,
        # pred has SELECT DISTINCT. Underlying unique row sets are equal.
        # BIRD's official scoring counts this as a match.
        gold = [(1, "a"), (1, "a"), (2, "b"), (1, "a")]
        pred = [(1, "a"), (2, "b")]
        c = compare_results(gold, pred)
        assert c.match

    def test_order_sensitive_when_gold_has_order_by(self) -> None:
        gold = [(1,), (2,), (3,)]
        pred = [(3,), (2,), (1,)]  # reversed
        c = compare_results(gold, pred, gold_sql="SELECT id FROM t ORDER BY id")
        assert not c.match
        assert "ordered row" in c.reason

    def test_order_insensitive_when_gold_has_no_order_by(self) -> None:
        gold = [(1,), (2,), (3,)]
        pred = [(3,), (2,), (1,)]
        c = compare_results(gold, pred, gold_sql="SELECT id FROM t")
        assert c.match

    def test_float_tolerance_within_1e6(self) -> None:
        gold = [(1.0000001,)]
        pred = [(1.0,)]
        # Order-sensitive path
        c1 = compare_results(gold, pred, gold_sql="SELECT x FROM t ORDER BY x")
        assert c1.match
        # Set path (multiset)
        c2 = compare_results(gold, pred, gold_sql="SELECT x FROM t")
        assert c2.match

    def test_float_outside_tolerance_fails(self) -> None:
        gold = [(1.001,)]
        pred = [(1.0,)]
        c = compare_results(gold, pred, gold_sql="SELECT x FROM t ORDER BY x")
        assert not c.match

    def test_bytes_decoded_as_utf8(self) -> None:
        gold = [("hello",)]
        pred = [(b"hello",)]
        c = compare_results(gold, pred)
        assert c.match

    def test_nan_compares_equal_to_nan(self) -> None:
        gold = [(float("nan"),)]
        pred = [(float("nan"),)]
        c = compare_results(gold, pred)
        assert c.match

    def test_empty_results_match(self) -> None:
        c = compare_results([], [])
        assert c.match
        assert c.gold_rows == 0


class TestExecutionAccuracy:
    def test_aggregate_zero_for_empty(self) -> None:
        assert execution_accuracy([]) == 0.0

    def test_aggregate_fraction(self) -> None:
        assert execution_accuracy([True, True, False, True]) == 0.75

    def test_aggregate_all_false(self) -> None:
        assert execution_accuracy([False, False]) == 0.0


class TestSchemaRecall:
    def test_all_tables_present(self) -> None:
        assert schema_recall_at_k(["Album", "Artist"], ["Album", "Artist", "Track"])

    def test_missing_table_fails(self) -> None:
        assert not schema_recall_at_k(["Album", "Artist"], ["Album", "Track"])

    def test_case_insensitive_default(self) -> None:
        assert schema_recall_at_k(["album"], ["Album"])

    def test_case_sensitive_when_disabled(self) -> None:
        assert not schema_recall_at_k(["album"], ["Album"], case_insensitive=False)

    def test_empty_gold_is_trivially_true(self) -> None:
        assert schema_recall_at_k([], ["whatever"])
