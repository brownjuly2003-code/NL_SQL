"""Smoke tests for `eval.runner.run_config_a` with a fake LLM + tiny SQLite.

We script the LLM to return three responses:
- question 1: correct SQL → match=True
- question 2: invalid SQL (DELETE) → caught by guard, match=False
- question 3: wrong SQL (different aggregate) → executes but mismatch

That covers the three EA outcomes we report on.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nl_sql.db.connection import DatabaseSpec, sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.eval.dataset import BirdExample
from nl_sql.eval.report import write_html_report, write_json_report
from nl_sql.eval.runner import (
    Configuration,
    run_config_a,
    run_config_b,
    run_config_c,
    run_config_d,
    run_config_e,
)
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse


class ScriptedLLM:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.call_count += 1
        return GenerateResponse(
            text=self._responses.pop(0),
            model=self.model,
            input_tokens=10,
            output_tokens=20,
        )


@pytest.fixture
def chinook_registry(tmp_path: Path) -> DatabaseRegistry:
    db_path = tmp_path / "chinook.sqlite"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE Artist (ArtistId INTEGER PRIMARY KEY, Name TEXT NOT NULL);
        CREATE TABLE Album (
            AlbumId INTEGER PRIMARY KEY,
            Title TEXT NOT NULL,
            ArtistId INTEGER NOT NULL,
            FOREIGN KEY (ArtistId) REFERENCES Artist(ArtistId)
        );
        INSERT INTO Artist VALUES (1, 'AC/DC'), (2, 'Aerosmith');
        INSERT INTO Album VALUES (10, 'Back in Black', 1), (11, 'Highway to Hell', 1), (12, 'Pump', 2);
        """
    )
    raw.commit()
    raw.close()

    spec = DatabaseSpec(id="bird_chinook", dialect="sqlite", url=sqlite_url_readonly(db_path))
    registry = DatabaseRegistry()
    registry.register(spec)
    return registry


def _example(qid: int, q: str, sql: str, difficulty: str = "simple") -> BirdExample:
    return BirdExample(
        question_id=qid,
        db_id="chinook",
        question=q,
        evidence="",
        sql=sql,
        difficulty=difficulty,  # type: ignore[arg-type]
    )


def test_run_config_a_correct_match(chinook_registry: DatabaseRegistry) -> None:
    sql_response = json.dumps(
        {
            "sql": "SELECT COUNT(*) FROM Album",
            "tables_used": ["Album"],
            "confidence": 0.9,
        }
    )
    llm = ScriptedLLM([sql_response])
    examples = [_example(1, "how many albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    assert run.configuration == Configuration.A_FULL_SCHEMA
    assert run.overall.n == 1
    assert run.overall.ea == 1.0
    assert run.records[0].match
    assert run.records[0].schema_recall is True
    assert run.records[0].error_kind is None
    assert run.records[0].input_tokens == 10
    assert run.records[0].output_tokens == 20


def test_run_config_a_invalid_sql_counts_as_miss(
    chinook_registry: DatabaseRegistry,
) -> None:
    bad = json.dumps({"sql": "DELETE FROM Album", "confidence": 0.1})
    llm = ScriptedLLM([bad])
    examples = [_example(2, "danger", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    rec = run.records[0]
    assert rec.match is False
    assert rec.error_kind == ExecutionErrorKind.INVALID_SQL.value
    assert run.overall.validity_rate == 0.0


def test_run_config_a_wrong_value_counts_as_miss(
    chinook_registry: DatabaseRegistry,
) -> None:
    wrong = json.dumps(
        {"sql": "SELECT COUNT(*) FROM Artist", "tables_used": ["Artist"], "confidence": 0.5}
    )
    llm = ScriptedLLM([wrong])
    examples = [_example(3, "albums?", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    rec = run.records[0]
    assert rec.match is False
    assert rec.error_kind is None  # SQL ran fine, just wrong answer
    assert rec.gold_row_count == 1
    assert rec.pred_row_count == 1


def test_run_config_a_per_difficulty_slices(chinook_registry: DatabaseRegistry) -> None:
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    wrong = json.dumps({"sql": "SELECT COUNT(*) FROM Artist"})
    llm = ScriptedLLM([correct, wrong, correct])
    examples = [
        _example(1, "q1", "SELECT COUNT(*) FROM Album", "simple"),
        _example(2, "q2", "SELECT COUNT(*) FROM Album", "moderate"),
        _example(3, "q3", "SELECT COUNT(*) FROM Album", "challenging"),
    ]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    assert run.per_difficulty["simple"].ea == 1.0
    assert run.per_difficulty["moderate"].ea == 0.0
    assert run.per_difficulty["challenging"].ea == 1.0
    assert run.overall.ea == pytest.approx(2 / 3)


def test_progress_callback_invoked(chinook_registry: DatabaseRegistry) -> None:
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    llm = ScriptedLLM([correct, correct])
    examples = [
        _example(1, "q1", "SELECT COUNT(*) FROM Album"),
        _example(2, "q2", "SELECT COUNT(*) FROM Album"),
    ]
    seen: list[tuple[int, int]] = []
    run_config_a(
        examples,
        sql_provider=llm,
        registry=chinook_registry,
        progress=lambda i, total, _r: seen.append((i, total)),
    )
    assert seen == [(1, 2), (2, 2)]


def test_other_configs_not_implemented_yet() -> None:
    for fn in (run_config_b, run_config_c, run_config_d, run_config_e):
        with pytest.raises(NotImplementedError):
            fn()


def test_report_writers_round_trip(
    chinook_registry: DatabaseRegistry, tmp_path: Path
) -> None:
    correct = json.dumps({"sql": "SELECT COUNT(*) FROM Album"})
    llm = ScriptedLLM([correct])
    examples = [_example(1, "q1", "SELECT COUNT(*) FROM Album")]
    run = run_config_a(examples, sql_provider=llm, registry=chinook_registry)

    json_path = write_json_report(run, root=tmp_path)
    assert json_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["configuration"] == "A_full_schema"
    assert len(payload["records"]) == 1
    assert payload["records"][0]["match"] is True

    html_path = write_html_report([run], root=tmp_path)
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "A_full_schema" in html
