from __future__ import annotations

import json
import sqlite3
import sys

from scripts import audit_rescore


def test_empty_prediction_remains_mismatch_even_when_gold_empty(
    tmp_path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    db_dir = data_root / "empty_db"
    db_dir.mkdir(parents=True)
    sqlite3.connect(db_dir / "empty_db.sqlite").close()
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_id": 1,
                        "difficulty": "simple",
                        "db_id": "empty_db",
                        "gold_sql": "SELECT 1 WHERE 0",
                        "pred_sql": "",
                        "match": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["audit_rescore.py", "--report", str(report), "--data-root", str(data_root)],
    )

    assert audit_rescore.main() == 0
