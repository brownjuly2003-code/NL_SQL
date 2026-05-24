"""Pin pred-exec routing in scripts/rescore_arcwise.py.

Regression guard for the 2026-05-24 fix: pred SQL must execute via
`execute_readonly` (mirrors canonical `scripts/audit_rescore.py`),
NOT via `_execute_gold`. The latter has a SQLAlchemyError fallback
through `exec_driver_sql` intended only for trusted BIRD gold; using
it on model pred can mask validator-style failures and leaves engine
state in a non-deterministic shape across sequential records.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts import rescore_arcwise


def _write_minimal_inputs(
    tmp_path: Path,
    *,
    db_dir_name: str = "card_games",
    pred_sql: str = "SELECT 1",
    gold_sql: str = "SELECT 1",
    arc_sql_only_sql: str = "SELECT 1",
    arc_full_sql: str = "SELECT 1",
) -> tuple[Path, Path, Path, Path]:
    db_root = tmp_path / "data" / "bird_mini_dev" / "MINIDEV" / "dev_databases"
    db_dir = db_root / db_dir_name
    db_dir.mkdir(parents=True)
    sqlite3.connect(db_dir / f"{db_dir_name}.sqlite").close()

    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_id": 366,
                        "difficulty": "simple",
                        "db_id": db_dir_name,
                        "gold_sql": gold_sql,
                        "pred_sql": pred_sql,
                        "match": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    sql_only = tmp_path / "sql_only.json"
    sql_only.write_text(
        json.dumps([{"question_id": 366, "SQL": arc_sql_only_sql}]),
        encoding="utf-8",
    )
    full = tmp_path / "full.json"
    full.write_text(
        json.dumps([{"question_id": 366, "SQL": arc_full_sql}]),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    return report, sql_only, full, out


def _make_registry_stub(db_root: Path, db_dir_name: str) -> MagicMock:
    from nl_sql.db import DatabaseSpec
    from nl_sql.db.connection import sqlite_url_readonly

    spec = DatabaseSpec(
        id=db_dir_name,
        dialect="sqlite",
        url=sqlite_url_readonly(
            db_root / db_dir_name / f"{db_dir_name}.sqlite"
        ),
    )
    registry = MagicMock()
    registry.get.return_value = spec
    return registry


def test_pred_routes_through_execute_readonly_not_execute_gold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pred-exec must call `execute_readonly`; `_execute_gold` is for gold only.

    Regression guard for 2026-05-24 follow-up — if someone reverts
    the import + pred-side call back to `_execute_gold`, the spy on
    `execute_readonly` will catch zero pred calls and the spy on
    `_execute_gold` will catch a pred-shaped call.
    """
    pred_sql = "SELECT 42 AS pred_only_marker"
    gold_sql = "SELECT 7 AS gold_only_marker"
    arc_sql_only_sql = "SELECT 7 AS gold_only_marker"
    arc_full_sql = "SELECT 7 AS gold_only_marker"

    report, sql_only, full, out = _write_minimal_inputs(
        tmp_path,
        pred_sql=pred_sql,
        gold_sql=gold_sql,
        arc_sql_only_sql=arc_sql_only_sql,
        arc_full_sql=arc_full_sql,
    )

    db_root = tmp_path / "data" / "bird_mini_dev" / "MINIDEV" / "dev_databases"
    registry_stub = _make_registry_stub(db_root, "card_games")
    monkeypatch.setattr(
        rescore_arcwise, "get_default_registry", lambda: registry_stub
    )

    execute_readonly_calls: list[str] = []
    execute_gold_calls: list[str] = []

    @contextmanager
    def _spy_execute_readonly(engine: Any, sql: str, **_: Any) -> Any:
        execute_readonly_calls.append(sql)
        result = MagicMock()
        result.rows = []
        yield result

    def _spy_execute_gold(
        engine: Any, sql: str, **_: Any
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        execute_gold_calls.append(sql)
        return [], []

    monkeypatch.setattr(rescore_arcwise, "execute_readonly", _spy_execute_readonly)
    monkeypatch.setattr(rescore_arcwise, "_execute_gold", _spy_execute_gold)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rescore_arcwise.py",
            "--report",
            str(report),
            "--sql-only",
            str(sql_only),
            "--full",
            str(full),
            "--out",
            str(out),
        ],
    )

    assert rescore_arcwise.main() == 0
    assert out.exists()

    assert pred_sql in execute_readonly_calls, (
        "pred_sql must execute via execute_readonly (regression: "
        "old path used _execute_gold which has SQLAlchemyError → "
        "exec_driver_sql fallback intended only for trusted gold)"
    )
    assert pred_sql not in execute_gold_calls, (
        "pred_sql must NOT execute via _execute_gold (regression: "
        "old path used _execute_gold for pred — see 2026-05-24 fix)"
    )
    assert all(
        sql in (gold_sql, arc_sql_only_sql, arc_full_sql)
        for sql in execute_gold_calls
    ), "every _execute_gold call must be for a gold variant"


def test_empty_pred_skips_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty pred_sql must not call execute_readonly (matches audit_rescore)."""
    report, sql_only, full, out = _write_minimal_inputs(tmp_path, pred_sql="")

    db_root = tmp_path / "data" / "bird_mini_dev" / "MINIDEV" / "dev_databases"
    registry_stub = _make_registry_stub(db_root, "card_games")
    monkeypatch.setattr(
        rescore_arcwise, "get_default_registry", lambda: registry_stub
    )

    execute_readonly_calls: list[str] = []

    @contextmanager
    def _spy_execute_readonly(engine: Any, sql: str, **_: Any) -> Any:
        execute_readonly_calls.append(sql)
        result = MagicMock()
        result.rows = []
        yield result

    monkeypatch.setattr(rescore_arcwise, "execute_readonly", _spy_execute_readonly)
    monkeypatch.setattr(
        rescore_arcwise,
        "_execute_gold",
        lambda *a, **k: ([], []),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rescore_arcwise.py",
            "--report",
            str(report),
            "--sql-only",
            str(sql_only),
            "--full",
            str(full),
            "--out",
            str(out),
        ],
    )

    assert rescore_arcwise.main() == 0
    assert execute_readonly_calls == [], (
        "empty pred_sql must skip execute_readonly entirely"
    )
