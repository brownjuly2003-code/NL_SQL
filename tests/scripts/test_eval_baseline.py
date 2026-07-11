from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from nl_sql.eval.dataset import BirdExample
from nl_sql.eval.runner import Configuration, EvalRun, EvalSummary
from scripts import eval_baseline


def test_eval_baseline_skips_incompatible_prior_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = EvalRun(
        configuration=Configuration.A_FULL_SCHEMA,
        sql_model="codestral-latest",
        overall=EvalSummary(
            n=1,
            ea=1.0,
            validity_rate=1.0,
            schema_recall_at_k=1.0,
            repair_success_rate=0.0,
            first_pass_ea=1.0,
            empty_result_rate=0.0,
            latency_p50_ms=1.0,
            latency_p95_ms=1.0,
            tokens_p50=1.0,
            tokens_p95=1.0,
        ),
        per_difficulty={
            "simple": EvalSummary(1, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0),
            "moderate": EvalSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            "challenging": EvalSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        },
        records=[],
    )
    report_dir = tmp_path / "2026-05-22"
    report_dir.mkdir()
    (report_dir / "voting-merged.json").write_text(
        json.dumps(
            {
                "configuration": "C_dense_cards",
                "sql_model": "codestral-latest",
                "overall": {"matched": 1},
                "per_difficulty": {},
                "records": [],
            }
        ),
        encoding="utf-8",
    )
    html_runs: list[EvalRun] = []

    monkeypatch.setattr(
        eval_baseline,
        "get_settings",
        lambda: SimpleNamespace(
            mistral_api_key="key",
            llm_cache_dir=tmp_path / "cache",
            llm_cache_size_limit_gb=1,
        ),
    )
    monkeypatch.setattr(
        eval_baseline,
        "load_bird_mini_dev",
        lambda path, **kwargs: [
            BirdExample(
                question_id=1,
                db_id="d",
                question="q",
                evidence="",
                sql="SELECT 1",
                difficulty="simple",
            )
        ],
    )
    monkeypatch.setattr(
        eval_baseline,
        "build_provider",
        lambda provider, settings: SimpleNamespace(model="codestral-latest"),
    )
    monkeypatch.setattr(eval_baseline, "CachingLLMProvider", lambda raw, **kwargs: raw)
    monkeypatch.setattr(
        eval_baseline,
        "get_default_registry",
        lambda **kwargs: SimpleNamespace(
            ids=lambda: ["bird_d"],
            get=lambda db_id: SimpleNamespace(dialect="sqlite"),
        ),
    )
    monkeypatch.setattr(eval_baseline, "run_config_a", lambda *args, **kwargs: run)
    monkeypatch.setattr(
        eval_baseline,
        "write_json_report",
        lambda *args, **kwargs: report_dir / "A_full_schema.json",
    )

    def fake_write_html_report(runs, *, root):
        html_runs.extend(runs)
        return report_dir / "index.html"

    monkeypatch.setattr(eval_baseline, "write_html_report", fake_write_html_report)

    result = eval_baseline.main(["--config", "A", "--n", "1", "--reports", str(tmp_path)])

    assert result == 0
    assert html_runs == [run]


def test_eval_baseline_only_qids_skips_dev_split(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = EvalRun(
        configuration=Configuration.A_FULL_SCHEMA,
        sql_model="codestral-latest",
        overall=EvalSummary(
            n=2,
            ea=0.0,
            validity_rate=1.0,
            schema_recall_at_k=1.0,
            repair_success_rate=0.0,
            first_pass_ea=0.0,
            empty_result_rate=0.0,
            latency_p50_ms=1.0,
            latency_p95_ms=1.0,
            tokens_p50=1.0,
            tokens_p95=1.0,
        ),
        per_difficulty={
            "simple": EvalSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            "moderate": EvalSummary(2, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0),
            "challenging": EvalSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        },
        records=[],
    )
    report_dir = tmp_path / "2026-05-22"
    seen_qids: list[int] = []

    monkeypatch.setattr(
        eval_baseline,
        "get_settings",
        lambda: SimpleNamespace(
            mistral_api_key="key",
            llm_cache_dir=tmp_path / "cache",
            llm_cache_size_limit_gb=1,
        ),
    )
    monkeypatch.setattr(
        eval_baseline,
        "load_bird_mini_dev",
        lambda path, **kwargs: [
            BirdExample(
                question_id=1205,
                db_id="thrombosis_prediction",
                question="q1205",
                evidence="",
                sql="SELECT 1",
                difficulty="moderate",
            ),
            BirdExample(
                question_id=1399,
                db_id="student_club",
                question="q1399",
                evidence="",
                sql="SELECT 1",
                difficulty="moderate",
            ),
            BirdExample(
                question_id=1404,
                db_id="student_club",
                question="q1404",
                evidence="",
                sql="SELECT 1",
                difficulty="moderate",
            ),
        ],
    )
    monkeypatch.setattr(
        eval_baseline,
        "dev_split",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dev_split should not run")),
    )
    monkeypatch.setattr(
        eval_baseline,
        "build_provider",
        lambda provider, settings: SimpleNamespace(model="codestral-latest"),
    )
    monkeypatch.setattr(eval_baseline, "CachingLLMProvider", lambda raw, **kwargs: raw)
    monkeypatch.setattr(
        eval_baseline,
        "get_default_registry",
        lambda **kwargs: SimpleNamespace(
            ids=lambda: ["bird_student_club", "bird_thrombosis_prediction"],
            get=lambda db_id: SimpleNamespace(dialect="sqlite"),
        ),
    )

    def fake_run_config_a(examples, **kwargs):
        seen_qids.extend(e.question_id for e in examples)
        return run

    monkeypatch.setattr(eval_baseline, "run_config_a", fake_run_config_a)
    monkeypatch.setattr(
        eval_baseline,
        "write_json_report",
        lambda *args, **kwargs: report_dir / "A_full_schema.json",
    )
    monkeypatch.setattr(
        eval_baseline,
        "write_html_report",
        lambda *args, **kwargs: report_dir / "index.html",
    )

    result = eval_baseline.main(
        ["--config", "A", "--only-qids", "1399,1205", "--reports", str(tmp_path)]
    )

    assert result == 0
    assert seen_qids == [1399, 1205]
