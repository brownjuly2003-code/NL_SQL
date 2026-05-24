from __future__ import annotations

import json
from pathlib import Path

from scripts import p3f_acceptance


def _report(records: list[dict[str, object]]) -> dict[str, object]:
    return {"records": records}


def test_p3f_acceptance_flags_current_failure_shapes() -> None:
    results = p3f_acceptance.evaluate_report(
        _report(
            [
                {
                    "question_id": 1404,
                    "match": False,
                    "pred_sql": (
                        "SELECT expense.expense_description AS type, SUM(expense.cost) "
                        "FROM expense JOIN budget ON expense.link_to_budget = budget.budget_id "
                        "JOIN event ON budget.link_to_event = event.event_id "
                        "WHERE event.event_name = 'October Meeting' "
                        "GROUP BY expense.expense_description"
                    ),
                },
                {
                    "question_id": 207,
                    "match": False,
                    "pred_sql": (
                        "SELECT DISTINCT a.element FROM atom a "
                        "JOIN bond b ON a.molecule_id = b.molecule_id "
                        "JOIN connected c ON b.bond_id = c.bond_id "
                        "WHERE b.bond_type = '='"
                    ),
                },
                {
                    "question_id": 902,
                    "match": False,
                    "pred_sql": (
                        "SELECT races.name FROM races "
                        "JOIN results ON races.raceId = results.raceId "
                        "JOIN drivers ON results.driverId = drivers.driverId "
                        "WHERE drivers.forename = 'Alex' AND drivers.surname = 'Yoong' "
                        "AND results.position < 20"
                    ),
                },
                {
                    "question_id": 1531,
                    "match": False,
                    "pred_sql": (
                        "SELECT customers.CustomerID, "
                        "SUM(transactions_1k.Price) / SUM(transactions_1k.Amount), "
                        "customers.Currency "
                        "FROM transactions_1k "
                        "JOIN customers ON transactions_1k.CustomerID = customers.CustomerID "
                        "GROUP BY transactions_1k.CustomerID, customers.Currency "
                        "ORDER BY SUM(transactions_1k.Price) DESC LIMIT 1"
                    ),
                },
            ]
        )
    )

    assert [r.qid for r in results] == [1404, 207, 902, 1531]
    assert [r.accepted for r in results] == [False, False, False, False]
    assert any("event.type" in reason for reason in results[0].reasons)
    assert any("connected.atom_id" in reason for reason in results[1].reasons)
    assert any("driverstandings.position" in reason for reason in results[2].reasons)
    assert any("yearmonth.consumption" in reason for reason in results[3].reasons)


def test_p3f_acceptance_accepts_ea_pass_with_target_columns() -> None:
    results = p3f_acceptance.evaluate_report(
        _report(
            [
                {
                    "question_id": 1404,
                    "match": True,
                    "pred_sql": (
                        "SELECT e.type, SUM(x.cost) FROM event AS e "
                        "JOIN budget AS b ON e.event_id = b.link_to_event "
                        "JOIN expense AS x ON b.budget_id = x.link_to_budget "
                        "WHERE e.event_name = 'October Meeting'"
                    ),
                },
                {
                    "question_id": 207,
                    "match": True,
                    "pred_sql": (
                        "SELECT DISTINCT a.element FROM atom AS a "
                        "JOIN bond AS b ON a.molecule_id = b.molecule_id "
                        "JOIN connected AS c ON a.atom_id = c.atom_id "
                        "WHERE b.bond_type = '='"
                    ),
                },
                {
                    "question_id": 902,
                    "match": True,
                    "pred_sql": (
                        "SELECT races.name FROM races "
                        "JOIN driverStandings ON races.raceId = driverStandings.raceId "
                        "JOIN drivers ON driverStandings.driverId = drivers.driverId "
                        "WHERE drivers.forename = 'Alex' AND drivers.surname = 'Yoong' "
                        "AND driverStandings.position < 20"
                    ),
                },
                {
                    "question_id": 1531,
                    "match": True,
                    "pred_sql": (
                        "SELECT T2.CustomerID, SUM(T2.Price / T2.Amount), T1.Currency "
                        "FROM customers AS T1 "
                        "INNER JOIN transactions_1k AS T2 ON T1.CustomerID = T2.CustomerID "
                        "WHERE T2.CustomerID = (SELECT CustomerID FROM yearmonth "
                        "ORDER BY yearmonth.Consumption DESC LIMIT 1) "
                        "GROUP BY T2.CustomerID, T1.Currency"
                    ),
                },
            ]
        )
    )

    assert [r.accepted for r in results] == [True, True, True, True]


def test_p3f_acceptance_cli_requires_pass(tmp_path: Path, capsys) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            _report(
                [
                    {"question_id": 1404, "match": False, "pred_sql": "SELECT 1"},
                    {"question_id": 207, "match": False, "pred_sql": "SELECT 1"},
                    {"question_id": 902, "match": False, "pred_sql": "SELECT 1"},
                    {"question_id": 1531, "match": False, "pred_sql": "SELECT 1"},
                ]
            )
        ),
        encoding="utf-8",
    )

    result = p3f_acceptance.main(["--report", str(report), "--require-pass"])

    assert result == 1
    assert "FAIL qid=1404" in capsys.readouterr().out


def test_p3f_acceptance_rejects_missing_targets(tmp_path: Path, capsys) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report([])), encoding="utf-8")

    result = p3f_acceptance.main(["--report", str(report)])

    assert result == 3
    assert "missing target qids: [1404, 207, 902, 1531]" in capsys.readouterr().err
