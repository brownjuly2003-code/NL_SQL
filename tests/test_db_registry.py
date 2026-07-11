from __future__ import annotations

from pathlib import Path

import pytest

from nl_sql.db import DatabaseSpec, get_default_registry
from nl_sql.db.connection import sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry


def test_registry_register_and_get() -> None:
    reg = DatabaseRegistry()
    spec = DatabaseSpec(id="alpha", dialect="sqlite", url="sqlite:///:memory:", description="")
    reg.register(spec)

    assert reg.get("alpha") is spec
    assert reg.ids() == ["alpha"]


def test_registry_get_missing_raises() -> None:
    reg = DatabaseRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.get("missing")


def test_default_registry_picks_up_chinook(tmp_path: Path) -> None:
    chinook = tmp_path / "chinook" / "Chinook.sqlite"
    chinook.parent.mkdir(parents=True)
    chinook.touch()

    reg = get_default_registry(data_root=tmp_path)

    assert "chinook" in reg.ids()
    spec = reg.get("chinook")
    assert spec.dialect == "sqlite"
    assert spec.url == str(chinook.resolve())


def test_default_registry_picks_up_bird_subfolders(tmp_path: Path) -> None:
    bird_dev = tmp_path / "bird_mini_dev" / "MINIDEV" / "dev_databases"
    for db_name in ("california_schools", "card_games"):
        db_dir = bird_dev / db_name
        db_dir.mkdir(parents=True)
        (db_dir / f"{db_name}.sqlite").touch()

    reg = get_default_registry(data_root=tmp_path)

    assert "bird_california_schools" in reg.ids()
    assert "bird_card_games" in reg.ids()


def test_default_registry_uses_readonly_urls(tmp_path: Path) -> None:
    chinook = tmp_path / "chinook" / "Chinook.sqlite"
    chinook.parent.mkdir(parents=True)
    chinook.touch()

    reg = get_default_registry(data_root=tmp_path)
    spec = reg.get("chinook")

    assert spec.url == sqlite_url_readonly(chinook)


def test_default_registry_registers_postgres_when_dsn_given(tmp_path: Path) -> None:
    dsn = "postgresql://nl_sql_ro:pwd@localhost:5433/nl_sql_demo"
    reg = get_default_registry(data_root=tmp_path, pg_dsn=dsn, pg_db_id="pg_demo")

    assert "pg_demo" in reg.ids()
    spec = reg.get("pg_demo")
    assert spec.dialect == "postgresql"
    assert spec.url == dsn


def test_default_registry_skips_postgres_without_dsn(tmp_path: Path) -> None:
    reg = get_default_registry(data_root=tmp_path)
    assert not any(reg.get(db_id).dialect == "postgresql" for db_id in reg.ids())
