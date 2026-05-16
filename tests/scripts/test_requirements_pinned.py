"""Drift guard for ``requirements.txt``.

Streamlit Cloud / HF Spaces install runtime from ``requirements.txt`` and have
no access to ``uv.lock``. If the two drift, the deployed app silently runs on
a different resolution than local + CI, which has bitten this project before
(see ``audit_codex_12_05_26.md`` §7 "Wide dependency ranges").

The pinned file is regenerated from ``uv.lock`` via the command pinned at the
top of ``requirements.txt``. This test re-runs that command and asserts the
result matches what is committed — so a forgotten regeneration after
``uv lock`` fails CI instead of breaking deploy.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "requirements.txt"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
def test_requirements_txt_matches_uv_lock() -> None:
    result = subprocess.run(
        [
            "uv",
            "export",
            "--format",
            "requirements.txt",
            "--no-dev",
            "--extra",
            "ui",
            "--no-emit-project",
            "--no-hashes",
            "--no-annotate",
            "--no-header",
            "--prune",
            "psycopg",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = _strip_comments_and_blanks(result.stdout)
    actual = _strip_comments_and_blanks(REQUIREMENTS.read_text(encoding="utf-8"))
    assert actual == expected, (
        "requirements.txt drifted from uv.lock — regenerate with:\n"
        "  uv export --format requirements.txt --no-dev --extra ui \\\n"
        "      --no-emit-project --no-hashes --no-annotate --no-header \\\n"
        "      --prune psycopg > requirements.txt"
    )


def _strip_comments_and_blanks(text: str) -> list[str]:
    return [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
