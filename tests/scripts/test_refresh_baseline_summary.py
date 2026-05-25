from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import refresh_baseline_summary as rbs


@pytest.fixture
def stale_report(tmp_path: Path) -> Path:
    report = tmp_path / "stale.json"
    report.write_text(
        json.dumps(
            {
                "overall": {"ea": 0.93, "matched": 186, "n": 200},
                "records": [{"question_id": i, "match": i < 185} for i in range(200)],
            }
        ),
        encoding="utf-8",
    )
    return report


def test_refresh_fixes_stale_summary(stale_report: Path) -> None:
    changed, _ = rbs.refresh(stale_report)
    assert changed is True
    data = json.loads(stale_report.read_text(encoding="utf-8"))
    assert data["overall"]["matched"] == 185
    assert data["overall"]["ea"] == 0.925
    assert data["overall"]["n"] == 200


def test_refresh_is_idempotent(stale_report: Path) -> None:
    rbs.refresh(stale_report)
    changed, info = rbs.refresh(stale_report)
    assert changed is False
    assert "already consistent" in info


def test_refresh_skips_report_without_records(tmp_path: Path) -> None:
    report = tmp_path / "no-records.json"
    report.write_text(json.dumps({"overall": {"ea": 0.5}}), encoding="utf-8")
    changed, info = rbs.refresh(report)
    assert changed is False
    assert "no records" in info


def test_canonical_baselines_are_consistent() -> None:
    """Regression guard: committed v22-v29 merged reports must have overall.ea
    derived from records[]. Catches the Codex 2026-05-25 #5 finding regressing.
    """
    repo_root = Path(__file__).resolve().parents[2]
    canonical = [
        "eval/reports/2026-05-23/v22-v21-plus-p3f-207-1404-merged.json",
        "eval/reports/2026-05-23/v23-v22-plus-archive-1205-merged.json",
        "eval/reports/2026-05-23/v24-v23-plus-archive-rescore-959-merged.json",
        "eval/reports/2026-05-24/v25-v24-plus-p3f-q902-merged.json",
        "eval/reports/2026-05-24/v26-v25-plus-p3f-q1531-merged.json",
        "eval/reports/2026-05-24/v27-v26-plus-p3f-q894-q1251-merged.json",
        "eval/reports/2026-05-24/v28-v27-plus-p3f-q408-merged.json",
        "eval/reports/2026-05-24/v29-v28-plus-p3f-q1275-merged.json",
    ]
    for rel in canonical:
        path = repo_root / rel
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data["records"]
        actual_matched = sum(1 for r in records if r.get("match") is True)
        stored = data["overall"]
        assert stored["matched"] == actual_matched, (
            f"{rel}: overall.matched={stored['matched']} but records[]={actual_matched}"
        )
        n = len(records)
        assert abs(stored["ea"] - actual_matched / n) < 1e-6, (
            f"{rel}: overall.ea={stored['ea']} but actual {actual_matched}/{n}"
        )
