#!/usr/bin/env python
"""Run the complete source checkout as a loopback-only Streamlit demo.

Unlike the Hugging Face deployment, this launcher requires all 12 local SQLite
databases and a Chroma schema index covering the same database ids. The Mistral
key must come from the process environment or the gitignored local ``.env``;
its value is never accepted as a CLI argument or printed.

Usage::

    uv run python scripts/run_local_demo.py --check
    uv run python scripts/run_local_demo.py

See ``LOCAL_DEMO.md`` for the complete PowerShell runbook.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Collection, Mapping, Sequence
from contextlib import closing
from pathlib import Path

from dotenv import dotenv_values

FULL_LOCAL_DB_IDS: frozenset[str] = frozenset(
    {
        "bird_california_schools",
        "bird_card_games",
        "bird_codebase_community",
        "bird_debit_card_specializing",
        "bird_european_football_2",
        "bird_financial",
        "bird_formula_1",
        "bird_student_club",
        "bird_superhero",
        "bird_thrombosis_prediction",
        "bird_toxicology",
        "chinook",
    }
)


def repo_root() -> Path:
    """Return the source checkout root independently of the caller's CWD."""
    return Path(__file__).resolve().parents[1]


def _mistral_key_is_configured(*, root: Path, environ: Mapping[str, str]) -> bool:
    process_value = environ.get("MISTRAL_API_KEY", "")
    if process_value.strip():
        return True

    env_path = root / ".env"
    if not env_path.is_file():
        return False
    file_value = dotenv_values(env_path).get("MISTRAL_API_KEY")
    return isinstance(file_value, str) and bool(file_value.strip())


def registered_database_ids() -> frozenset[str]:
    """Return SQLite databases discoverable by the normal application registry."""
    from nl_sql.db.registry import get_default_registry

    return frozenset(get_default_registry().ids())


def indexed_database_ids(*, root: Path) -> frozenset[str]:
    """Read schema database ids directly from Chroma SQLite in read-only mode."""
    sqlite_path = (root / "chroma_data" / "chroma.sqlite3").resolve()
    uri = f"{sqlite_path.as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT em.string_value
            FROM embedding_metadata AS em
            JOIN embeddings AS e ON e.id = em.id
            JOIN segments AS s ON s.id = e.segment_id
            JOIN collections AS c ON c.id = s.collection
            WHERE c.name = 'schema_chunks'
              AND em.key = 'db_id'
              AND em.string_value IS NOT NULL
            ORDER BY em.string_value
            """
        ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def copy_runtime_chroma(*, root: Path, destination: Path) -> None:
    """Copy the complete source index so Chroma housekeeping cannot dirty git."""
    shutil.copytree(root / "chroma_data", destination)


def streamlit_environment(
    *,
    runtime_chroma: Path,
    environ: Mapping[str, str],
) -> dict[str, str]:
    """Return child-only environment with the runtime Chroma override."""
    child = dict(environ)
    child["NL_SQL_CHROMA_DATA_DIR"] = str(runtime_chroma)
    return child


def preflight_issues(
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    registered_ids: Collection[str] | None = None,
    indexed_ids: Collection[str] | None = None,
) -> list[str]:
    """Return local-demo prerequisite failures without making network calls."""
    base = repo_root() if root is None else root
    current_environ = os.environ if environ is None else environ
    issues: list[str] = []

    if not _mistral_key_is_configured(root=base, environ=current_environ):
        issues.append("MISTRAL_API_KEY is not configured in the process environment or local .env.")

    available_databases = (
        registered_database_ids() if registered_ids is None else frozenset(registered_ids)
    )
    missing_databases = sorted(FULL_LOCAL_DB_IDS - available_databases)
    if missing_databases:
        issues.append(
            "Full-source database set is incomplete; missing database ids: "
            + ", ".join(missing_databases)
        )

    chroma_sqlite = base / "chroma_data" / "chroma.sqlite3"
    if not chroma_sqlite.is_file():
        issues.append(
            "Chroma index is missing; run `uv run python scripts/build_index.py --db all`."
        )
    else:
        try:
            available_index = (
                indexed_database_ids(root=base) if indexed_ids is None else frozenset(indexed_ids)
            )
        except Exception as exc:
            issues.append(f"Chroma index could not be read ({type(exc).__name__}).")
        else:
            missing_index = sorted(FULL_LOCAL_DB_IDS - available_index)
            if missing_index:
                issues.append(
                    "Full-source Chroma index is incomplete; missing index database ids: "
                    + ", ".join(missing_index)
                )

    return issues


def streamlit_command(*, port: int) -> list[str]:
    """Build a secret-free command that serves the source checkout on loopback."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app/streamlit_app.py",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]


def run_streamlit(*, root: Path, port: int) -> int:
    """Run Streamlit against a temporary byte-for-byte copy of Chroma."""
    with tempfile.TemporaryDirectory(prefix="nl_sql_local_demo_") as temporary:
        runtime_chroma = Path(temporary) / "chroma_data"
        copy_runtime_chroma(root=root, destination=runtime_chroma)
        child_environ = streamlit_environment(
            runtime_chroma=runtime_chroma,
            environ=os.environ,
        )
        print("[local-demo] using a temporary full Chroma copy; source bytes stay unchanged.")
        completed = subprocess.run(
            streamlit_command(port=port),
            cwd=root,
            env=child_environ,
            check=False,
        )
    return completed.returncode


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the full local source prerequisites without starting Streamlit.",
    )
    parser.add_argument("--port", type=_port, default=8501, help="Loopback port (default: 8501).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repo_root()
    issues = preflight_issues(root=root)
    if issues:
        print("[local-demo] preflight FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print(
        f"[local-demo] preflight OK: full source checkout "
        f"({len(FULL_LOCAL_DB_IDS)} SQLite DBs + Chroma); "
        "MISTRAL_API_KEY configured (value not printed)."
    )
    if args.check:
        return 0

    print(f"[local-demo] starting http://127.0.0.1:{args.port}")
    try:
        return run_streamlit(root=root, port=args.port)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
