from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl_sql.eval.dataset import BirdExample
from scripts import run_helallao_voting


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
    out_path = tmp_path / "helallao.json"
    baseline.write_text(
        json.dumps(
            {
                "records": [
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

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_helallao_voting.py",
            "--baseline",
            str(baseline),
            "--bird-root",
            str(tmp_path / "bird"),
            "--out",
            str(out_path),
            "--max-cases",
            "1",
            "--model",
            "grok-4.1",
            "--sleep-between",
            "0",
        ],
    )
    monkeypatch.setattr(
        run_helallao_voting,
        "get_settings",
        lambda: SimpleNamespace(mistral_api_key="key", llm_cache_dir=tmp_path / "cache"),
    )
    monkeypatch.setattr(run_helallao_voting, "load_bird_mini_dev", lambda root: [example])
    monkeypatch.setattr(run_helallao_voting, "get_default_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        run_helallao_voting,
        "HelallaoPerplexityProvider",
        lambda **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(run_helallao_voting, "MistralProvider", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(
        run_helallao_voting,
        "CachingEmbeddingProvider",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(run_helallao_voting, "SchemaIndex", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(run_helallao_voting, "build_pipeline", lambda cfg: SimpleNamespace())
    monkeypatch.setattr(run_helallao_voting.time, "sleep", lambda seconds: None)

    def raise_tokenizer_error(*args: object, **kwargs: object) -> object:
        raise RuntimeError("tokenizer quote error around Women's Soccer")

    monkeypatch.setattr(run_helallao_voting, "run_pipeline", raise_tokenizer_error)

    assert run_helallao_voting.main() == 0

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
            "vote_source": "helallao:grok-4.1",
            "alt_error": "tokenizer quote error around Women's Soccer",
        }
    ]
