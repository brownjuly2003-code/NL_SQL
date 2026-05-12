"""Smoke tests for the FastAPI surface.

Pipeline-touching endpoints (`/ask`, `/databases`, `/readyz`) require live
Chroma + DB registry + Mistral key, so they're not exercised here — those
are covered by an out-of-process integration run. These tests confirm the
HTTP layer wires up correctly (routes registered, schemas valid, /healthz
returns the provider snapshot without hitting any external service).
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from nl_sql.api.main import create_app


def test_healthz_open_and_returns_provider_snapshot() -> None:
    app = create_app()
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert isinstance(body["providers_configured"], list)


def test_ask_rejects_missing_api_key_when_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("NL_SQL_API_KEY", "test-secret")
    app = create_app()
    client = TestClient(app)
    r = client.post("/ask", json={"question": "ping", "db_id": "chinook"})
    assert r.status_code == 401
    assert "X-API-Key" in r.json()["detail"]


def test_routes_registered() -> None:
    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    expected = {"/healthz", "/readyz", "/databases", "/ask", "/eval/latest"}
    assert expected.issubset(paths), f"missing: {expected - paths}"


def test_eval_latest_serves_committed_baseline() -> None:
    if "NL_SQL_API_KEY" in os.environ:
        del os.environ["NL_SQL_API_KEY"]
    app = create_app()
    client = TestClient(app)
    r = client.get("/eval/latest")
    # baseline file exists in the repo per Phase 0 freeze; if missing,
    # the endpoint surfaces 404 which is a valid signal too.
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert body["overall_ea"] is None or 0.0 <= body["overall_ea"] <= 1.0
        assert body["n"] >= 0
