"""Regression tests for scripts/merge_voting_rescues.py reverify gate.

Closes Codex audit 2026-05-25 #2: stale `alt_match=True` from pre-fix
voting JSONs (where `compare_results([], [])` blessed empty-empty as match)
must NOT silently inflate baseline EA at merge time. Default `--reverify`
re-executes pred+gold via `safe_compare_pred` to reject stale flips.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import merge_voting_rescues


class _FakeRegistry:
    def __init__(self, engine: object) -> None:
        self._engine = engine

    def engine_for(self, db_id: str) -> object:
        return self._engine


def _baseline_record(question_id: int = 1, gold_sql: str = "SELECT 1") -> dict[str, Any]:
    return {
        "question_id": question_id,
        "db_id": "demo",
        "difficulty": "moderate",
        "question": "stub",
        "gold_sql": gold_sql,
        "pred_sql": "SELECT 0",
        "match": False,
    }


def test_reverify_rejects_stale_empty_empty_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale voting record with alt_match=True where alt_pred raises must be rejected."""

    def _exec_validated_raises(*args: object, **kwargs: object) -> object:
        raise RuntimeError("SQL syntax error on alt_pred")

    def _exec_gold_empty(*args: object, **kwargs: object) -> tuple[list, list, bool]:
        return [], [], False  # gold returned empty (legitimate empty set)

    monkeypatch.setattr(merge_voting_rescues, "execute_validated", _exec_validated_raises)
    monkeypatch.setattr(merge_voting_rescues, "_execute_gold_with_status", _exec_gold_empty)

    br = _baseline_record()
    verified, reason = merge_voting_rescues._reverify_candidate(
        br, "CTE_MISSING_WITH SELECT 1", _FakeRegistry(engine=object())
    )
    assert verified is False
    assert "pred execution failed" in reason


def test_reverify_accepts_real_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legitimate alt rescue: pred and gold both return identical non-empty rows."""

    class _Result:
        def __init__(self) -> None:
            self.rows: list[tuple[Any, ...]] = [(1, "a")]

    class _Outcome:
        def __init__(self) -> None:
            self.result = _Result()

    monkeypatch.setattr(
        merge_voting_rescues,
        "execute_validated",
        lambda *a, **k: _Outcome(),
    )
    monkeypatch.setattr(
        merge_voting_rescues,
        "_execute_gold_with_status",
        lambda *a, **k: ([(1, "a")], ["col"], False),
    )

    br = _baseline_record()
    verified, _ = merge_voting_rescues._reverify_candidate(
        br, "SELECT 1, 'a'", _FakeRegistry(engine=object())
    )
    assert verified is True


def test_reverify_rejects_gold_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gold-side failure must be rejected via safe_compare_pred(gold_failed=True)."""

    class _Result:
        def __init__(self) -> None:
            self.rows: list[tuple[Any, ...]] = []

    class _Outcome:
        def __init__(self) -> None:
            self.result = _Result()

    monkeypatch.setattr(
        merge_voting_rescues,
        "execute_validated",
        lambda *a, **k: _Outcome(),
    )
    monkeypatch.setattr(
        merge_voting_rescues,
        "_execute_gold_with_status",
        lambda *a, **k: ([], [], True),
    )

    br = _baseline_record()
    verified, reason = merge_voting_rescues._reverify_candidate(
        br, "SELECT * FROM tbl WHERE 1=0", _FakeRegistry(engine=object())
    )
    assert verified is False
    assert "gold execution failed" in reason


def test_no_reverify_flag_trusts_stored_alt_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`--no-reverify` opts out of the gate (escape hatch for legacy workflows)."""
    baseline_path = tmp_path / "baseline.json"
    voting_path = tmp_path / "voting.json"
    out_path = tmp_path / "merged.json"
    baseline_path.write_text(
        json.dumps(
            {
                "records": [_baseline_record(question_id=1, gold_sql="SELECT 1")],
                "overall": {"ea": 0.0, "matched": 0, "n": 1},
                "per_difficulty": {"moderate": {"ea": 0.0, "matched": 0, "n": 1}},
                "sql_model": "stub",
                "configuration": "stub-config",
            }
        ),
        encoding="utf-8",
    )
    voting_path.write_text(
        json.dumps(
            {
                "alt_model": "fake-llm",
                "records": [
                    {
                        "question_id": 1,
                        "vote_match": True,
                        "alt_match": True,
                        "alt_pred": "MALFORMED SQL",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_voting_rescues.py",
            "--baseline",
            str(baseline_path),
            "--voting",
            str(voting_path),
            "--out",
            str(out_path),
            "--no-reverify",
        ],
    )
    # If reverify is correctly skipped, the merge proceeds without calling
    # registry/execute_validated/_execute_gold_with_status. Make those raise
    # to prove the no-reverify path doesn't touch them.

    def _explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("reverify path must not run under --no-reverify")

    monkeypatch.setattr(merge_voting_rescues, "get_default_registry", _explode)
    monkeypatch.setattr(merge_voting_rescues, "execute_validated", _explode)
    monkeypatch.setattr(merge_voting_rescues, "_execute_gold_with_status", _explode)

    assert merge_voting_rescues.main() == 0
    merged = json.loads(out_path.read_text(encoding="utf-8"))
    assert merged["records"][0]["match"] is True
    assert merged["records"][0]["voted_by"] == "fake-llm"
