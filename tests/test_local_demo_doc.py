"""Local demo runbook contract (local-first full-source delivery)."""

from __future__ import annotations

from pathlib import Path

from scripts import run_local_demo

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "LOCAL_DEMO.md"


def test_local_demo_runbook_covers_safe_full_source_launch() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    lowered = text.lower()

    # Recommended full-source launcher + loopback surface.
    assert "scripts/run_local_demo.py" in text
    assert "uv run python scripts/run_local_demo.py --check" in text
    assert "uv run python scripts/run_local_demo.py" in text
    assert "127.0.0.1:8501" in text
    assert "12" in text
    assert "SQLite" in text
    assert "9" in text  # clone-first tier is smaller than full-source

    # Owner keys: documented, never injected on the command line.
    assert "MISTRAL_API_KEY" in text
    assert "uv sync --extra dev --extra ui" in text
    assert "$env:MISTRAL_API_KEY=" not in text
    assert "Set-Item env:MISTRAL_API_KEY" not in text
    assert "--api-key" not in text
    # Commands must not look like secret assignment; .env is the path.
    assert "Copy-Item -LiteralPath '.env.example'" in text or ".env.example" in text

    # Runbook must not hard-require one machine path.
    assert "Set-Location D:\\NL_SQL" not in text
    assert "корня" in lowered or "клона" in lowered

    # Product provider subset + embeddings still need Mistral even with Ollama.
    for provider in ("mistral", "github_models", "groq", "ollama"):
        assert provider in text
    assert "embeddings" in lowered
    assert "mistral_api_key" in lowered

    # Smoke + stop + clean-clone data steps.
    assert "Ctrl+C" in text
    assert "SELECT COUNT(*) FROM Album" in text
    assert "347" in text
    assert "download_data.py" in text
    assert "build_index.py" in text

    # Local-first: HF is not a runtime dependency of the demo path.
    assert "не нужен" in lowered
    assert "runtime" not in lowered or "не" in lowered
    # Optional/historical tooling may be named, but not as required launch step.
    assert "uv run python scripts/deploy_hf.py" not in text


def test_launcher_help_points_to_full_runbook() -> None:
    assert run_local_demo.__doc__ is not None
    assert "LOCAL_DEMO.md" in run_local_demo.__doc__
