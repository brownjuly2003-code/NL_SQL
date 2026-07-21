"""Tests for the autotune cycle orchestrator (plan_autotune S7).

The stakes here are the two mistakes this track actually made by hand: two
runs sharing a `--report-suffix` (they overwrite the same file), and reading a
raw EA off a run full of transport holes. Both are pinned below.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from scripts.autotune import run_cycle


def _report_payload(
    *,
    matches: dict[int, bool],
    exceptions: tuple[int, ...] = (),
    difficulty: str = "simple",
) -> dict[str, Any]:
    records = []
    for qid, match in matches.items():
        records.append(
            {
                "question_id": qid,
                "difficulty": difficulty,
                "match": match,
                "error_kind": None,
            }
        )
    for qid in exceptions:
        records.append(
            {
                "question_id": qid,
                "difficulty": difficulty,
                "match": False,
                "error_kind": "pipeline_exception",
            }
        )
    hits = sum(1 for m in matches.values() if m)
    return {
        "configuration": "E_dense_fewshot_repair",
        "sql_model": "test",
        "overall": {"ea": hits / len(records), "validity_rate": 1.0},
        "per_difficulty": {difficulty: {"ea": hits / len(records)}},
        "records": records,
    }


def _write_report(root: Path, date: str, suffix: str, payload: dict[str, Any]) -> Path:
    out_dir = root / date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"E_dense_fewshot_repair-{suffix}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_repo_config_parses() -> None:
    cfg = run_cycle.load_config(run_cycle.DEFAULT_CONFIG)
    assert [t.label for t in cfg.targets] == ["tuned", "base"]
    assert cfg.fewshot_top_k == 0
    assert cfg.eval_n == 200


def test_duplicate_suffix_is_rejected(tmp_path: Path) -> None:
    """Two targets, one suffix → one report file, silently overwritten."""
    config = tmp_path / "cycle.toml"
    config.write_text(
        """
name = "dup"
[[eval.targets]]
label = "a"
model = "m1"
suffix = "same"
[[eval.targets]]
label = "b"
model = "m2"
suffix = "same"
""",
        encoding="utf-8",
    )
    with pytest.raises(run_cycle.ConfigError, match="duplicate suffixes"):
        run_cycle.load_config(config)


def test_unknown_train_mode_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "cycle.toml"
    config.write_text(
        """
[train]
mode = "on-a-whim"
[[eval.targets]]
label = "a"
model = "m"
suffix = "s"
""",
        encoding="utf-8",
    )
    with pytest.raises(run_cycle.ConfigError, match=r"train\.mode"):
        run_cycle.load_config(config)


def test_eval_argv_keeps_fewshot_off() -> None:
    """The tuning replaces few-shot; a non-zero top-k is a train/eval mismatch."""
    cfg = run_cycle.load_config(run_cycle.DEFAULT_CONFIG)
    argv = run_cycle.eval_argv(cfg, cfg.targets[0])
    assert argv[argv.index("--fewshot-top-k") + 1] == "0"
    assert argv[argv.index("--report-suffix") + 1] == "student-tuned"
    assert argv[argv.index("--sql-model") + 1] == "sqltuned"


def test_selected_stages_keeps_pipeline_order() -> None:
    assert run_cycle.selected_stages("report,eval") == ("eval", "report")
    assert run_cycle.selected_stages("") == run_cycle.STAGES
    with pytest.raises(run_cycle.ConfigError, match="unknown stage"):
        run_cycle.selected_stages("evaluate")


def test_mcnemar_exact_matches_known_values() -> None:
    assert run_cycle.mcnemar_exact(0, 0) == 1.0
    assert run_cycle.mcnemar_exact(24, 13) == pytest.approx(0.099, abs=0.001)
    assert run_cycle.mcnemar_exact(13, 24) == pytest.approx(run_cycle.mcnemar_exact(24, 13))
    assert run_cycle.mcnemar_exact(10, 0) == pytest.approx(2 / 2**10)


def test_summary_separates_raw_ea_from_answered_ea(tmp_path: Path) -> None:
    payload = _report_payload(matches={1: True, 2: False}, exceptions=(3, 4))
    path = _write_report(tmp_path, "2026-07-21", "holed", payload)
    target = run_cycle.EvalTarget(label="x", model="m", suffix="holed")

    summary = run_cycle.summarise(target, path)
    assert summary.n == 4
    assert summary.answered == 2
    assert summary.exceptions == 2
    assert summary.ea_raw == pytest.approx(0.25)  # holes counted as wrong
    assert summary.ea_answered == pytest.approx(0.5)
    assert summary.per_difficulty["simple"] == pytest.approx(0.5)


def test_paired_comparison_uses_only_shared_questions(tmp_path: Path) -> None:
    left = run_cycle.summarise(
        run_cycle.EvalTarget(label="tuned", model="m", suffix="l"),
        _write_report(
            tmp_path,
            "2026-07-21",
            "l",
            _report_payload(matches={1: True, 2: True, 3: False, 4: True}),
        ),
    )
    right = run_cycle.summarise(
        run_cycle.EvalTarget(label="base", model="m", suffix="r"),
        _write_report(
            tmp_path,
            "2026-07-21",
            "r",
            _report_payload(matches={1: True, 2: False, 3: True}, exceptions=(4,)),
        ),
    )

    paired = run_cycle.compare_paired(left, right)
    assert paired is not None
    assert paired.n_pairs == 3  # q4 is a hole on the right, excluded
    assert paired.left_ea == pytest.approx(2 / 3)
    assert paired.right_ea == pytest.approx(2 / 3)
    assert (paired.fixed, paired.broke) == (1, 1)


def test_paired_comparison_without_overlap_is_none(tmp_path: Path) -> None:
    left = run_cycle.summarise(
        run_cycle.EvalTarget(label="a", model="m", suffix="a"),
        _write_report(tmp_path, "2026-07-21", "a", _report_payload(matches={1: True})),
    )
    right = run_cycle.summarise(
        run_cycle.EvalTarget(label="b", model="m", suffix="b"),
        _write_report(tmp_path, "2026-07-21", "b", _report_payload(matches={9: True})),
    )
    assert run_cycle.compare_paired(left, right) is None


def test_find_report_picks_the_newest(tmp_path: Path) -> None:
    old = _write_report(tmp_path, "2026-07-20", "s", _report_payload(matches={1: True}))
    new = _write_report(tmp_path, "2026-07-21", "s", _report_payload(matches={1: False}))
    stale = time.time() - 600
    os.utime(old, (stale, stale))

    assert run_cycle.find_report(tmp_path, "s") == new
    assert run_cycle.find_report(tmp_path, "absent") is None


def test_dry_run_executes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: object, **kwargs: object) -> int:
        raise AssertionError("dry run must not spawn processes")

    monkeypatch.setattr(run_cycle.subprocess, "call", explode)
    assert run_cycle.main(["--dry-run"]) == 0


def test_bad_config_path_exits_two() -> None:
    assert run_cycle.main(["--config", "no/such/cycle.toml"]) == 2


def test_report_stage_writes_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports = tmp_path / "reports"
    _write_report(
        reports, "2026-07-21", "student-tuned", _report_payload(matches={1: True, 2: True})
    )
    _write_report(
        reports, "2026-07-21", "student-base", _report_payload(matches={1: True, 2: False})
    )
    out = tmp_path / "cycle.md"

    cfg = run_cycle.load_config(run_cycle.DEFAULT_CONFIG)
    monkeypatch.setattr(run_cycle, "ROOT", tmp_path)
    patched = type(cfg)(
        **{
            **{f: getattr(cfg, f) for f in cfg.__slots__},
            "reports_root": reports,
            "report_out": out,
        }
    )

    assert run_cycle.stage_report(patched, dry_run=False) == 0
    text = out.read_text(encoding="utf-8")
    assert "Paired comparison" in text
    assert "fixed 1 / broke 0" in text
    assert "codestral (product): 61.5%" in text
