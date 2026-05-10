from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_RUNTIME_DEPS = {"pandas", "plotly", "streamlit"}


def _dependency_names(entries: list[str]) -> set[str]:
    return {re.split(r"[<>=!~;\[]", entry, maxsplit=1)[0].strip().lower() for entry in entries}


def test_streamlit_cloud_runtime_deps_are_default_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert UI_RUNTIME_DEPS <= _dependency_names(pyproject["project"]["dependencies"])


def test_uv_lock_default_package_has_streamlit_cloud_runtime_deps() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    project = next(package for package in lock["package"] if package["name"] == "nl-sql")
    locked_dependencies = {dependency["name"] for dependency in project["dependencies"]}

    assert UI_RUNTIME_DEPS <= locked_dependencies
