from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class _FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")

    def cache_resource(self, **_: Any) -> Any:
        return lambda function: function


@pytest.fixture
def bootstrap_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delitem(sys.modules, "app.bootstrap", raising=False)
    monkeypatch.setitem(sys.modules, "streamlit", _FakeStreamlit())
    return importlib.import_module("app.bootstrap")


def _settings(tmp_path: Path, **overrides: Any) -> SimpleNamespace:
    values = {
        "default_provider": "ollama",
        "mistral_api_key": "embed-key",
        "mistral_gen_model": "codestral-latest",
        "mistral_embed_model": "mistral-embed",
        "mistral_base_url": "https://api.mistral.ai/v1",
        "chroma_data_dir": "chroma_data",
        "llm_cache_dir": tmp_path / "cache",
        "llm_cache_size_limit_gb": 1.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_bootstrap_uses_configured_sql_provider(
    bootstrap_module: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    persist_dir = tmp_path / "repo" / "chroma_data"
    persist_dir.mkdir(parents=True)
    foreign_cwd = tmp_path / "foreign"
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)

    registry = object()
    schema_index = object()
    sql_provider = object()
    provider_calls: list[tuple[str, object]] = []
    client_paths: list[str] = []

    monkeypatch.setattr(bootstrap_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        bootstrap_module,
        "under_root",
        lambda *parts: persist_dir.parent.joinpath(*parts),
        raising=False,
    )
    monkeypatch.setattr(bootstrap_module, "get_default_registry", lambda: registry)
    monkeypatch.setattr(
        bootstrap_module.chromadb,
        "PersistentClient",
        lambda **kwargs: client_paths.append(kwargs["path"]) or object(),
    )
    monkeypatch.setattr(bootstrap_module, "MistralProvider", lambda **_: object())
    monkeypatch.setattr(bootstrap_module, "CachingEmbeddingProvider", lambda *_, **__: object())
    monkeypatch.setattr(bootstrap_module, "SchemaIndex", lambda **_: schema_index)
    monkeypatch.setattr(
        bootstrap_module,
        "build_provider",
        lambda name, settings: provider_calls.append((name, settings)) or object(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "CachingLLMProvider",
        lambda *_, **__: sql_provider,
    )

    result = bootstrap_module.bootstrap()

    assert provider_calls == [("ollama", settings)]
    assert client_paths == [str(persist_dir)]
    assert result == (registry, schema_index, sql_provider, sql_provider)


def test_bootstrap_reports_mistral_key_is_for_embeddings(
    bootstrap_module: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        bootstrap_module,
        "get_settings",
        lambda: _settings(tmp_path, mistral_api_key=""),
    )

    with pytest.raises(RuntimeError, match="required for embeddings"):
        bootstrap_module.bootstrap()


def test_chroma_persist_dir_accepts_runtime_absolute_path(
    bootstrap_module: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_copy = tmp_path / "runtime-chroma"
    monkeypatch.setattr(
        bootstrap_module,
        "under_root",
        lambda *_: pytest.fail("absolute runtime path must not be joined to repo root"),
    )

    assert bootstrap_module.chroma_persist_dir(runtime_copy) == runtime_copy
