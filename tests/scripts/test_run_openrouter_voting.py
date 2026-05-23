from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl_sql.eval.dataset import BirdExample
from scripts import run_openrouter_voting


class FakeEngine:
    def dispose(self) -> None:
        pass


class FakeSpec:
    def make_engine(self) -> FakeEngine:
        return FakeEngine()


class FakeRegistry:
    def get(self, db_id: str) -> FakeSpec:
        assert db_id == "bird_student_club"
        return FakeSpec()


def test_pipeline_exception_is_written_to_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = tmp_path / "baseline.json"
    out_path = tmp_path / "openrouter.json"
    baseline.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_id": 1404,
                        "match": False,
                        "pred_sql": "SELECT 2",
                    },
                    {
                        "question_id": 1399,
                        "match": False,
                        "pred_sql": "SELECT 0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    example = BirdExample(
        question_id=1399,
        db_id="student_club",
        question="Did Maya Mclean attend the 'Women's Soccer' event?",
        evidence="",
        sql="SELECT 1",
        difficulty="moderate",
    )
    other_example = BirdExample(
        question_id=1404,
        db_id="student_club",
        question="Identify the type of expenses approved for October Meeting.",
        evidence="",
        sql="SELECT 2",
        difficulty="moderate",
    )
    model = "openai/gpt-oss-120b:free"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_openrouter_voting.py",
            "--baseline",
            str(baseline),
            "--provider-model",
            model,
            "--bird-root",
            str(tmp_path / "bird"),
            "--out",
            str(out_path),
            "--only-qids",
            "1399",
            "--sleep-between",
            "0",
        ],
    )
    monkeypatch.setattr(
        run_openrouter_voting,
        "get_settings",
        lambda: SimpleNamespace(mistral_api_key="key", llm_cache_dir=tmp_path / "cache"),
    )
    monkeypatch.setattr(
        run_openrouter_voting,
        "load_bird_mini_dev",
        lambda root: [other_example, example],
    )
    monkeypatch.setattr(run_openrouter_voting, "get_default_registry", lambda: FakeRegistry())
    monkeypatch.setattr(run_openrouter_voting, "_read_openrouter_key", lambda: "key")
    monkeypatch.setattr(run_openrouter_voting, "OpenAI", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(run_openrouter_voting, "MistralProvider", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(
        run_openrouter_voting,
        "CachingEmbeddingProvider",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(run_openrouter_voting, "SchemaIndex", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(run_openrouter_voting, "build_pipeline", lambda cfg: SimpleNamespace())
    monkeypatch.setattr(run_openrouter_voting.time, "sleep", lambda seconds: None)

    def raise_openrouter_error(*args: object, **kwargs: object) -> object:
        raise RuntimeError("openrouter upstream 429")

    monkeypatch.setattr(run_openrouter_voting, "run_pipeline", raise_openrouter_error)

    assert run_openrouter_voting.main() == 0

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["summary"]["errored"] == 1
    assert payload["records"] == [
        {
            "question_id": 1399,
            "db_id": "student_club",
            "difficulty": "moderate",
            "question": "Did Maya Mclean attend the 'Women's Soccer' event?",
            "gold_sql": "SELECT 1",
            "baseline_pred": "SELECT 0",
            "alt_pred": "",
            "alt_confidence": None,
            "baseline_match": False,
            "alt_match": False,
            "vote_match": False,
            "vote_source": f"openrouter:{model}",
            "alt_error": "openrouter upstream 429",
        }
    ]
