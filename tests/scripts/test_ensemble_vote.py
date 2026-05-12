from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from nl_sql.db.connection import QueryResult
from nl_sql.eval.metrics.execution_accuracy import ResultComparison
from nl_sql.eval.runner import EvalRun
from nl_sql.execution.guards import ValidationReport
from nl_sql.execution.runner import ExecutionOutcome
from scripts import ensemble_vote


class FakeEngine:
    def dispose(self) -> None:
        pass


class FakeSpec:
    def make_engine(self) -> FakeEngine:
        return FakeEngine()


class FakeRegistry:
    def get(self, db_id: str) -> FakeSpec:
        return FakeSpec()


def test_quorum_wins_and_first_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    written = _patch_runtime(monkeypatch, tmp_path)
    reports = _write_reports(tmp_path)

    result = ensemble_vote.main(
        [
            "--reports",
            *(str(path) for path in reports),
            "--out",
            str(tmp_path / "out"),
            "--require-quorum",
            "2",
            "--fallback-on-no-quorum",
            "first",
        ]
    )

    assert result == 0
    assert written[0].records[0].pred_sql == "select q1_b"
    assert written[0].records[1].pred_sql == "select q2_first"
    assert "ensemble n=2 EA=100.0%, quorum=50.0%, fallback=50.0%" in capsys.readouterr().out


def test_highest_confidence_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = _patch_runtime(monkeypatch, tmp_path)
    reports = _write_reports(tmp_path)

    result = ensemble_vote.main(
        [
            "--reports",
            *(str(path) for path in reports),
            "--out",
            str(tmp_path / "out"),
            "--require-quorum",
            "2",
            "--fallback-on-no-quorum",
            "highest-confidence",
        ]
    )

    assert result == 0
    assert written[0].records[0].pred_sql == "select q1_b"
    assert written[0].records[1].pred_sql == "select q2_high"


def _patch_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[EvalRun]:
    written: list[EvalRun] = []
    rows_by_sql: dict[str, list[tuple[int, ...]]] = {
        "select q1_a": [(1,)],
        "select q1_b": [(1,)],
        "select q1_c": [(1,)],
        "select q2_first": [(10,)],
        "select q2_high": [(20,)],
        "select q2_low": [(30,)],
    }

    def fake_execute_validated(
        engine: object,
        sql: str,
        *,
        dialect: object = "sqlite",
        statement_timeout_ms: int = 30_000,
        row_cap: int = 10_000,
    ) -> ExecutionOutcome:
        return _outcome(sql, rows_by_sql[sql])

    def fake_execute_gold(
        engine: object,
        sql: str,
        *,
        statement_timeout_ms: int,
        row_cap: int,
    ) -> tuple[list[tuple[int, ...]], list[str]]:
        return ([(1,)] if "q1" in sql else [(10,)]), ["c"]

    def fake_compare_results(
        gold_rows: Sequence[Sequence[Any]],
        pred_rows: Sequence[Sequence[Any]],
        *,
        gold_sql: str | None = None,
    ) -> ResultComparison:
        return ResultComparison(
            match=True,
            gold_rows=len(gold_rows),
            pred_rows=len(pred_rows),
        )

    def fake_write_json_report(
        run: EvalRun,
        *,
        root: Path | str,
        name_suffix: str = "",
    ) -> Path:
        written.append(run)
        return tmp_path / "out" / "2026-05-12" / "ensemble.json"

    def fake_write_html_report(runs: Sequence[EvalRun], *, root: Path | str) -> Path:
        return tmp_path / "out" / "2026-05-12" / "index.html"

    monkeypatch.setattr(ensemble_vote, "get_default_registry", lambda: FakeRegistry())
    monkeypatch.setattr(ensemble_vote, "execute_validated", fake_execute_validated)
    monkeypatch.setattr(ensemble_vote, "_execute_gold", fake_execute_gold)
    monkeypatch.setattr(ensemble_vote, "compare_results", fake_compare_results)
    monkeypatch.setattr(ensemble_vote, "write_json_report", fake_write_json_report)
    monkeypatch.setattr(ensemble_vote, "write_html_report", fake_write_html_report)
    return written


def _outcome(sql: str, rows: list[tuple[int, ...]]) -> ExecutionOutcome:
    return ExecutionOutcome(
        sql=sql,
        validation=ValidationReport(sql=sql, dialect="sqlite", violations=[]),
        result=QueryResult(
            rows=rows,
            columns=["c"],
            row_count=len(rows),
            truncated=False,
            elapsed_ms=1.0,
        ),
    )


def _write_reports(tmp_path: Path) -> list[Path]:
    payloads = [
        _payload(
            "model-a",
            [
                _record(1, "simple", "select q1_a", confidence=0.2),
                _record(2, "moderate", "select q2_first", confidence=0.1),
            ],
        ),
        _payload(
            "model-b",
            [
                _record(1, "simple", "select q1_b", confidence=0.9),
                _record(2, "moderate", "select q2_high", confidence=0.8),
            ],
        ),
        _payload(
            "model-c",
            [
                _record(1, "simple", "select q1_c", confidence=0.4),
                _record(2, "moderate", "select q2_low", confidence=0.3),
            ],
        ),
    ]
    paths: list[Path] = []
    for idx, payload in enumerate(payloads, start=1):
        path = tmp_path / f"r{idx}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    return paths


def _payload(model: str, records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "configuration": "G_dense_fewshot_verify_retry",
        "sql_model": model,
        "overall": _summary(),
        "per_difficulty": {
            "simple": _summary(),
            "moderate": _summary(),
            "challenging": _summary(),
        },
        "records": records,
    }


def _summary() -> dict[str, object]:
    return {
        "n": 0,
        "ea": 0.0,
        "validity_rate": 0.0,
        "schema_recall_at_k": 0.0,
        "repair_success_rate": 0.0,
        "first_pass_ea": 0.0,
        "empty_result_rate": 0.0,
        "latency_p50_ms": 0.0,
        "latency_p95_ms": 0.0,
        "tokens_p50": 0.0,
        "tokens_p95": 0.0,
    }


def _record(
    question_id: int,
    difficulty: str,
    pred_sql: str,
    *,
    confidence: float,
) -> dict[str, object]:
    return {
        "question_id": question_id,
        "db_id": "demo",
        "difficulty": difficulty,
        "dialect": "sqlite",
        "question": f"q{question_id}",
        "gold_sql": f"select gold_q{question_id}",
        "pred_sql": pred_sql,
        "match": False,
        "schema_recall": True,
        "error_kind": None,
        "error_message": "",
        "repair_attempted": False,
        "first_pass_match": False,
        "latency_ms": 1.0,
        "input_tokens": 10,
        "output_tokens": 5,
        "gold_tables": ["t"],
        "retrieved_tables": ["t"],
        "pred_row_count": 1,
        "gold_row_count": 1,
        "comparison_reason": "",
        "confidence": confidence,
    }
