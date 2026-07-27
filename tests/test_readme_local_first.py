"""README Quick start contract: clone-first vs full rebuild (pathlib-only)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"


def _quick_start_through_documentation() -> str:
    """Slice from ``## Quick start`` up to the next H2."""
    text = README.read_text(encoding="utf-8")
    start = text.index("## Quick start")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_readme_quick_start_local_first_contract() -> None:
    section = _quick_start_through_documentation()

    assert "Python 3.13" in section

    assert "cp .env.example .env" in section
    assert "Copy-Item .env.example .env" in section

    assert "MISTRAL_API_KEY" in section
    assert "your own Mistral key" in section
    assert "not claimed free" in section
    assert "free-tier" not in section.lower()
    assert "$0" not in section

    assert "9 SQLite DBs" in section
    assert "prebuilt Chroma" in section
    assert "No download or reindex is needed for the first run" in section

    assert "uv run python scripts/download_data.py chinook" in section
    assert "uv run python scripts/download_data.py bird-mini-dev" in section
    assert "uv run python scripts/build_index.py --db all" in section

    assert "required for embeddings" in section
    assert "NL_SQL_DEFAULT_PROVIDER" in section
    assert "GITHUB_TOKEN" in section
    assert "GROQ_API_KEY" in section
    assert "Ollama" in section

    assert "Postgres is optional" in section
    assert "SQLite-only" in section

    assert "uv sync --extra dev --extra ui" in section
    assert "uv run streamlit run app/streamlit_app.py" in section
