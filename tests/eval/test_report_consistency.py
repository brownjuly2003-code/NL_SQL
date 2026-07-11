"""Canonical eval reports must not drift between their summary and their records.

Audit 2026-07-11 (A3): the v31 report's top-level `overall` said 185/0.925 while
its own `records[]` recomputed to 188/0.94 — a stale summary that contradicted the
README headline. This pins the invariant so it can't silently rot again: for every
committed report that ships a `records[]` array, `overall.matched` and `overall.ea`
must equal the recomputation from those records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl_sql.paths import under_root

CANONICAL_REPORTS = [
    under_root("eval", "baselines", "reproducible_n200.json"),
    under_root("eval", "reports", "2026-05-26", "v31-v30-plus-p3f-q37-merged.json"),
]


def _reports_with_records() -> list[Path]:
    paths = list(CANONICAL_REPORTS)
    paths += sorted(under_root("eval", "baselines").glob("*.json"))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p in seen or not p.exists():
            continue
        seen.add(p)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data.get("records"), list) and data["records"]:
            out.append(p)
    return out


@pytest.mark.parametrize("report_path", _reports_with_records(), ids=lambda p: p.name)
def test_overall_matches_recompute_from_records(report_path: Path) -> None:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    records = data["records"]
    overall = data["overall"]
    matched = sum(1 for r in records if r.get("match") is True)
    n = len(records)

    assert overall["n"] == n, f"{report_path.name}: overall.n={overall['n']} but {n} records"
    assert overall["matched"] == matched, (
        f"{report_path.name}: overall.matched={overall['matched']} but records give {matched}"
    )
    assert abs(overall["ea"] - matched / n) < 1e-4, (
        f"{report_path.name}: overall.ea={overall['ea']} but records give {matched / n:.4f}"
    )
