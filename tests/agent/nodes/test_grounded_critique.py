from __future__ import annotations

import json

from nl_sql.agent.nodes.grounded_critique import evaluate_shape


def test_how_many_single_row_ok() -> None:
    verdict = evaluate_shape("how many districts", None, 1)

    assert verdict.ok


def test_how_many_many_rows_not_ok() -> None:
    verdict = evaluate_shape("how many districts", None, 47)

    assert not verdict.ok


def test_list_zero_rows_not_ok() -> None:
    verdict = evaluate_shape("List all customers", None, 0)

    assert not verdict.ok


def test_list_some_rows_ok() -> None:
    verdict = evaluate_shape("List all customers", None, 8)

    assert verdict.ok


def test_list_too_many_rows_not_ok() -> None:
    verdict = evaluate_shape("List all customers", None, 5817)

    assert not verdict.ok


def test_plan_few_overrides_text_heuristic() -> None:
    plan_json = json.dumps({"expected_row_count": "few (2-20)"})
    verdict = evaluate_shape("List all customers", plan_json, 5817)

    assert not verdict.ok


def test_top_n_over_bound_not_ok() -> None:
    verdict = evaluate_shape("top 5 branches by loans", None, 8)

    assert not verdict.ok


def test_top_n_exact_bound_ok() -> None:
    verdict = evaluate_shape("top 5 branches by loans", None, 5)

    assert verdict.ok


def test_top_n_truncated_tail_ok() -> None:
    verdict = evaluate_shape("top 5 branches by loans", None, 3)

    assert verdict.ok


def test_average_single_row_ok() -> None:
    verdict = evaluate_shape("What is the average salary?", None, 1)

    assert verdict.ok
