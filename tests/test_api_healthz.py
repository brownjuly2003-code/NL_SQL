from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nl_sql import __version__
from nl_sql.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert "ollama" in body["providers_configured"]


def test_healthz_lists_mistral_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    client = TestClient(create_app())

    body = client.get("/healthz").json()

    assert "mistral" in body["providers_configured"]


def test_healthz_lists_github_models_when_token_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-pat")
    client = TestClient(create_app())

    body = client.get("/healthz").json()

    assert "github_models" in body["providers_configured"]
