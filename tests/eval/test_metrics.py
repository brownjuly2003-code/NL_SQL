"""Unit tests for execution_accuracy + schema_recall metrics."""

from __future__ import annotations

from nl_sql.eval.metrics.execution_accuracy import (
    compare_results,
    execution_accuracy,
)
from nl_sql.eval.metrics.schema_recall import schema_recall_at_k


class TestCompareResults:
    def test_identical_rows_match_set_eq(self) -> None:
        gold = [(1, "a"), (2, "b")]
        pred = [(2, "b"), (1, "a")]
        c = compare_results(gold, pred)
        assert c.match
        assert c.gold_rows == 2
        assert c.pred_rows == 2

    def test_row_count_mismatch_fails(self) -> None:
        gold = [(1,), (2,)]
        pred = [(1,)]
        c = compare_results(gold, pred)
        assert not c.match
        assert "row count mismatch" in c.reason

    def test_set_eq_with_duplicates_uses_multiset(self) -> None:
        # If gold has 2 copies and pred has 1, that's NOT a match.
        gold = [(1,), (1,)]
        pred = [(1,), (2,)]
        c = compare_results(gold, pred)
        assert not c.match

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
