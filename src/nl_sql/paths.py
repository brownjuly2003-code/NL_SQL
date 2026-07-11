"""Repo-root-anchored filesystem paths.

Code that opens files with paths relative to the current working directory
(e.g. ``Path("chroma_data")``) breaks silently when the process is launched
from anywhere other than the repo root — Streamlit, uvicorn, pytest, and
deployment entrypoints (Docker CMD, HF Spaces) don't all guarantee that CWD.
This module resolves the repo root once, from this file's own location, so
downstream code stays correct regardless of CWD.
"""

from __future__ import annotations

from pathlib import Path

# src/nl_sql/paths.py -> parents[0]=src/nl_sql, [1]=src, [2]=repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def under_root(*parts: str) -> Path:
    """Return ``PROJECT_ROOT`` joined with ``parts``, CWD-independent."""
    return PROJECT_ROOT.joinpath(*parts)
