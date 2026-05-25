from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts import (
    eval_baseline,
    run_critique_retry,
    run_groq_voting,
    run_helallao_voting,
    run_openrouter_voting,
    run_selfcon_retry,
    run_sonnet_voting,
    run_wide_schema_retry,
)


@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (eval_baseline, ["eval_baseline.py", "--help"]),
        (run_critique_retry, ["run_critique_retry.py", "--help"]),
        (run_groq_voting, ["run_groq_voting.py", "--help"]),
        (run_helallao_voting, ["run_helallao_voting.py", "--help"]),
        (run_openrouter_voting, ["run_openrouter_voting.py", "--help"]),
        (run_selfcon_retry, ["run_selfcon_retry.py", "--help"]),
        (run_sonnet_voting, ["run_sonnet_voting.py", "--help"]),
        (run_wide_schema_retry, ["run_wide_schema_retry.py", "--help"]),
    ],
)
def test_retry_tools_expose_only_qids(
    module: ModuleType,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 0
    assert "--only-qids" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (
            run_critique_retry,
            [
                "run_critique_retry.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "9999",
            ],
        ),
        (
            run_groq_voting,
            [
                "run_groq_voting.py",
                "--baseline",
                "{baseline}",
                "--provider-model",
                "openai/gpt-oss-120b",
                "--out",
                "{out}",
                "--bucket",
                "any_failure",
                "--only-qids",
                "9999",
            ],
        ),
        (
            run_helallao_voting,
            [
                "run_helallao_voting.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "9999",
            ],
        ),
        (
            run_openrouter_voting,
            [
                "run_openrouter_voting.py",
                "--baseline",
                "{baseline}",
                "--provider-model",
                "openai/gpt-oss-120b:free",
                "--out",
                "{out}",
                "--only-qids",
                "9999",
            ],
        ),
        (
            run_selfcon_retry,
            [
                "run_selfcon_retry.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "9999",
            ],
        ),
        (
            run_sonnet_voting,
            [
                "run_sonnet_voting.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "9999",
            ],
        ),
        (
            run_wide_schema_retry,
            [
                "run_wide_schema_retry.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "9999",
            ],
        ),
    ],
)
def test_retry_tools_reject_missing_only_qids_before_provider_setup(
    module: ModuleType,
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.json"
    out = tmp_path / "out.json"
    baseline.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_id": 1399,
                        "match": False,
                        "pred_sql": "SELECT 0",
                        "gold_row_count": 14,
                        "pred_row_count": 1,
                        "difficulty": "moderate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [arg.format(baseline=baseline, out=out) for arg in argv],
    )
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: pytest.fail("provider settings should not be loaded for missing qid"),
    )

    assert module.main() == 3
    assert "qids not found" in capsys.readouterr().err


def test_eval_baseline_rejects_missing_only_qids_before_provider_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        eval_baseline,
        "load_bird_mini_dev",
        lambda path: [],
    )
    monkeypatch.setattr(
        eval_baseline,
        "get_settings",
        lambda: pytest.fail("provider settings should not be loaded for missing qid"),
    )

    result = eval_baseline.main(
        ["--config", "A", "--only-qids", "9999", "--reports", str(tmp_path)]
    )

    assert result == 3
    assert "qids not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (
            eval_baseline,
            ["eval_baseline.py", "--config", "A", "--only-qids", "abc"],
        ),
        (
            run_critique_retry,
            [
                "run_critique_retry.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
        (
            run_groq_voting,
            [
                "run_groq_voting.py",
                "--baseline",
                "{baseline}",
                "--provider-model",
                "openai/gpt-oss-120b",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
        (
            run_helallao_voting,
            [
                "run_helallao_voting.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
        (
            run_openrouter_voting,
            [
                "run_openrouter_voting.py",
                "--baseline",
                "{baseline}",
                "--provider-model",
                "openai/gpt-oss-120b:free",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
        (
            run_selfcon_retry,
            [
                "run_selfcon_retry.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
        (
            run_sonnet_voting,
            [
                "run_sonnet_voting.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
        (
            run_wide_schema_retry,
            [
                "run_wide_schema_retry.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "abc",
            ],
        ),
    ],
)
def test_retry_tools_reject_non_integer_only_qids(
    module: ModuleType,
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.json"
    out = tmp_path / "out.json"
    baseline.write_text(json.dumps({"records": []}), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [arg.format(baseline=baseline, out=out) for arg in argv],
    )

    result = module.main() if module is not eval_baseline else module.main(argv[1:])

    assert result == 3
    assert "invalid --only-qids" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (
            run_groq_voting,
            [
                "run_groq_voting.py",
                "--baseline",
                "{baseline}",
                "--provider-model",
                "openai/gpt-oss-120b",
                "--out",
                "{out}",
                "--bucket",
                "any_failure",
                "--only-qids",
                "1399",
                "--skip-qids",
                "1399",
            ],
        ),
        (
            run_helallao_voting,
            [
                "run_helallao_voting.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "1399",
                "--skip-qids",
                "1399",
            ],
        ),
        (
            run_openrouter_voting,
            [
                "run_openrouter_voting.py",
                "--baseline",
                "{baseline}",
                "--provider-model",
                "openai/gpt-oss-120b:free",
                "--out",
                "{out}",
                "--only-qids",
                "1399",
                "--skip-qids",
                "1399",
            ],
        ),
        (
            run_sonnet_voting,
            [
                "run_sonnet_voting.py",
                "--baseline",
                "{baseline}",
                "--out",
                "{out}",
                "--only-qids",
                "1399",
                "--skip-qids",
                "1399",
            ],
        ),
    ],
)
def test_retry_tools_skip_all_only_qids_before_provider_setup(
    module: ModuleType,
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.json"
    out = tmp_path / "out.json"
    baseline.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_id": 1399,
                        "match": False,
                        "pred_sql": "SELECT 0",
                        "gold_row_count": 14,
                        "pred_row_count": 1,
                        "difficulty": "moderate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [arg.format(baseline=baseline, out=out) for arg in argv],
    )
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: pytest.fail("provider settings should not be loaded for empty qid set"),
    )

    assert module.main() == 0
    assert "0" in capsys.readouterr().err
