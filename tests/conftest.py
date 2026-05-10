"""Shared pytest fixtures.

We intentionally clear the `.env` lookup and the cached settings before each
test so providers can be configured per-test without leaking real secrets
from the developer machine into CI runs.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from nl_sql.config import settings as settings_module


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # SettingsConfigDict is a TypedDict-style dict, mutate via setitem.
    monkeypatch.setitem(settings_module.Settings.model_config, "env_file", None)
    settings_module.get_settings.cache_clear()
    yield
    settings_module.get_settings.cache_clear()


@pytest.fixture
def fake_mistral_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test-mistral-key"
    monkeypatch.setenv("MISTRAL_API_KEY", key)
    return key


@pytest.fixture
def fake_github_token(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "test-github-pat"
    monkeypatch.setenv("GITHUB_TOKEN", token)
    return token
