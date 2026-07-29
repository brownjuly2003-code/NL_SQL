"""Full-source local demo launcher contract."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from scripts import run_local_demo


def _complete_root(tmp_path: Path) -> Path:
    chroma_dir = tmp_path / "chroma_data"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").touch()
    return tmp_path


def test_preflight_accepts_full_source_with_process_key(tmp_path: Path) -> None:
    root = _complete_root(tmp_path)

    issues = run_local_demo.preflight_issues(
        root=root,
        environ={"MISTRAL_API_KEY": "test-key"},
        registered_ids=run_local_demo.FULL_LOCAL_DB_IDS,
        indexed_ids=run_local_demo.FULL_LOCAL_DB_IDS,
    )

    assert issues == []


def test_preflight_accepts_key_from_gitignored_env_file(tmp_path: Path) -> None:
    root = _complete_root(tmp_path)
    (root / ".env").write_text("MISTRAL_API_KEY=test-key\n", encoding="utf-8")

    issues = run_local_demo.preflight_issues(
        root=root,
        environ={},
        registered_ids=run_local_demo.FULL_LOCAL_DB_IDS,
        indexed_ids=run_local_demo.FULL_LOCAL_DB_IDS,
    )

    assert issues == []


def test_preflight_rejects_partial_database_and_index_sets(tmp_path: Path) -> None:
    root = _complete_root(tmp_path)
    missing = "bird_european_football_2"
    partial_ids = run_local_demo.FULL_LOCAL_DB_IDS - {missing}

    issues = run_local_demo.preflight_issues(
        root=root,
        environ={"MISTRAL_API_KEY": "test-key"},
        registered_ids=partial_ids,
        indexed_ids=partial_ids,
    )

    assert any(missing in issue and "database" in issue.lower() for issue in issues)
    assert any(missing in issue and "index" in issue.lower() for issue in issues)


def test_preflight_requires_mistral_key_without_echoing_values(tmp_path: Path) -> None:
    root = _complete_root(tmp_path)

    issues = run_local_demo.preflight_issues(
        root=root,
        environ={},
        registered_ids=run_local_demo.FULL_LOCAL_DB_IDS,
        indexed_ids=run_local_demo.FULL_LOCAL_DB_IDS,
    )

    assert issues == ["MISTRAL_API_KEY is not configured in the process environment or local .env."]


def test_streamlit_command_runs_source_checkout_on_loopback() -> None:
    command = run_local_demo.streamlit_command(port=8765)

    assert command == [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app/streamlit_app.py",
        "--server.address=127.0.0.1",
        "--server.port=8765",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]


def test_index_inspection_reads_chroma_sqlite_without_mutating_it(tmp_path: Path) -> None:
    root = _complete_root(tmp_path)
    sqlite_path = root / "chroma_data" / "chroma.sqlite3"
    connection = sqlite3.connect(sqlite_path)
    connection.executescript(
        """
        CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT NOT NULL);
        CREATE TABLE embeddings (id INTEGER PRIMARY KEY, segment_id TEXT NOT NULL);
        CREATE TABLE embedding_metadata (
            id INTEGER NOT NULL,
            key TEXT NOT NULL,
            string_value TEXT
        );
        INSERT INTO collections (id, name) VALUES ('collection', 'schema_chunks');
        INSERT INTO segments (id, collection) VALUES ('segment', 'collection');
        """
    )
    for embedding_id, db_id in enumerate(sorted(run_local_demo.FULL_LOCAL_DB_IDS), start=1):
        connection.execute(
            "INSERT INTO embeddings (id, segment_id) VALUES (?, 'segment')",
            (embedding_id,),
        )
        connection.execute(
            """
            INSERT INTO embedding_metadata (id, key, string_value)
            VALUES (?, 'db_id', ?)
            """,
            (embedding_id, db_id),
        )
    connection.commit()
    connection.close()
    original_bytes = sqlite_path.read_bytes()

    ids = run_local_demo.indexed_database_ids(root=root)

    assert ids == run_local_demo.FULL_LOCAL_DB_IDS
    assert sqlite_path.read_bytes() == original_bytes


def test_runtime_chroma_copy_preserves_complete_source(tmp_path: Path) -> None:
    root = _complete_root(tmp_path)
    segment_dir = root / "chroma_data" / "segment"
    segment_dir.mkdir()
    (segment_dir / "data.bin").write_bytes(b"original")
    destination = tmp_path / "runtime" / "chroma_data"

    run_local_demo.copy_runtime_chroma(root=root, destination=destination)

    assert (destination / "segment" / "data.bin").read_bytes() == b"original"
    assert (segment_dir / "data.bin").read_bytes() == b"original"


def test_streamlit_environment_points_only_child_at_runtime_chroma(tmp_path: Path) -> None:
    source = {"MISTRAL_API_KEY": "test-key", "UNCHANGED": "yes"}
    runtime_chroma = tmp_path / "runtime-chroma"

    child = run_local_demo.streamlit_environment(
        runtime_chroma=runtime_chroma,
        environ=source,
    )

    assert child == {
        "MISTRAL_API_KEY": "test-key",
        "UNCHANGED": "yes",
        "NL_SQL_CHROMA_DATA_DIR": str(runtime_chroma),
    }
    assert "NL_SQL_CHROMA_DATA_DIR" not in source
