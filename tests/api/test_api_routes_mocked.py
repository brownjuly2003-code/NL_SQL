"""Mocked-singletons coverage for /readyz, /databases, /ask.

The existing `test_api_routes.py` only hits endpoints that never touch the
pipeline (`/healthz`, `/eval/latest`, route registration). This module
fills the Kimi P1.6 gap: it exercises every business-logic path through
``app.dependency_overrides[get_singletons]`` with fakes, so coverage no
longer requires a live Chroma + Mistral key + DB index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from nl_sql.agent.graph import PipelineRunResult
from nl_sql.api.main import Singletons, create_app, get_singletons
from nl_sql.db.connection import QueryResult
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.guards import ValidationReport
from nl_sql.execution.runner import ExecutionOutcome

# ---------------------------------------------------------- fakes


@dataclass
class _FakeSpec:
    dialect: str = "sqlite"
    description: str = "fake test db"


class _FakeRegistry:
    def __init__(self, db_ids: list[str] | None = None) -> None:
        self._ids = db_ids if db_ids is not None else ["chinook", "bird_california_schools"]

    def ids(self) -> list[str]:
        return list(self._ids)

    def get(self, db_id: str) -> _FakeSpec:
        if db_id not in self._ids:
            raise KeyError(db_id)
        return _FakeSpec()


class _FakeCollection:
    def __init__(self, *, chunks_per_db: int = 4, total: int = 12) -> None:
        self.chunks_per_db = chunks_per_db
        self.total = total

    def get(self, *, where: dict[str, Any], include: list[str]) -> dict[str, Any]:
        return {"metadatas": [{"db_id": where["db_id"]}] * self.chunks_per_db}

    def count(self) -> int:
        return self.total


class _FakeSchemaIndex:
    def __init__(self, *, chunks_per_db: int = 4, total: int = 12) -> None:
        self.schema_collection = _FakeCollection(chunks_per_db=chunks_per_db, total=total)


class _FakeProvider:
    model = "fake-sql-model"

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("fake provider — not actually invoked")


def _make_fake_singletons(
    *,
    db_ids: list[str] | None = None,
    schema_total: int = 12,
) -> Singletons:
    return Singletons(
        pipeline=object(),  # opaque — run_pipeline is patched in /ask tests
        registry=_FakeRegistry(db_ids=db_ids),  # type: ignore[arg-type]
        schema_index=_FakeSchemaIndex(total=schema_total),  # type: ignore[arg-type]
        sql_provider=_FakeProvider(),  # type: ignore[arg-type]
    )


def _make_pipeline_result() -> PipelineRunResult:
    query_result = QueryResult(
        rows=[(1, "AC/DC"), (2, "Accept")],
        columns=["id", "name"],
        row_count=2,
        truncated=False,
        elapsed_ms=4.2,
    )
    validation = ValidationReport(sql="SELECT id, name FROM Artist LIMIT 2", dialect="sqlite")
    outcome = ExecutionOutcome(
        sql="SELECT id, name FROM Artist LIMIT 2",
        validation=validation,
        result=query_result,
    )
    return PipelineRunResult(
        question="who are the first two artists",
        db_id="chinook",
        sql="SELECT id, name FROM Artist LIMIT 2",
        rationale="trivial",
        confidence=0.92,
        outcome=outcome,
        output_format=None,
        caption="2 rows",
        error_kind=None,
        error_message="",
        repair_attempted=False,
        trace=[
            {
                "node": "generate_sql",
                "model": "fake-sql-model",
                "input_tokens": 12,
                "output_tokens": 8,
                "confidence": 0.92,
            },
        ],
    )


@pytest.fixture
def client_with_fakes() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    return TestClient(app)


# ---------------------------------------------------------- /readyz


def test_readyz_returns_ok_when_singletons_healthy(client_with_fakes: TestClient) -> None:
    r = client_with_fakes.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["chroma_ok"] is True
    assert body["registry_ok"] is True
    assert body["registered_dbs"] == 2
    assert body["schema_chunks"] == 12


def test_readyz_reports_not_ready_when_chroma_empty() -> None:
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons(schema_total=0)
    r = TestClient(app).get("/readyz")
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["chroma_ok"] is False
    assert body["schema_chunks"] == 0


def test_readyz_reports_not_ready_when_registry_empty() -> None:
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons(db_ids=[])
    r = TestClient(app).get("/readyz")
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["registry_ok"] is False
    assert body["registered_dbs"] == 0


def test_readyz_handles_factory_exception_gracefully() -> None:
    app = create_app()

    def broken() -> Singletons:
        raise RuntimeError("Chroma persist dir missing")

    app.dependency_overrides[get_singletons] = broken
    r = TestClient(app).get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["chroma_ok"] is False
    assert body["registry_ok"] is False


# ---------------------------------------------------------- /databases


def test_databases_returns_list_with_table_counts(client_with_fakes: TestClient) -> None:
    r = client_with_fakes.get("/databases")
    assert r.status_code == 200
    dbs = r.json()["databases"]
    assert len(dbs) == 2
    ids = {row["db_id"] for row in dbs}
    assert ids == {"chinook", "bird_california_schools"}
    for row in dbs:
        assert row["dialect"] == "sqlite"
        assert row["table_count"] == 4


def test_databases_rejects_missing_api_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NL_SQL_API_KEY", "test-secret")
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    r = TestClient(app).get("/databases")
    assert r.status_code == 401


def test_databases_accepts_correct_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NL_SQL_API_KEY", "test-secret")
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    r = TestClient(app).get("/databases", headers={"X-API-Key": "test-secret"})
    assert r.status_code == 200
    assert len(r.json()["databases"]) == 2


def test_databases_handles_schema_collection_error() -> None:
    """Table count gracefully falls back to 0 if schema collection raises."""

    class _BoomCollection:
        def get(self, *, where: dict[str, Any], include: list[str]) -> dict[str, Any]:
            raise RuntimeError("chroma vacuum in progress")

        def count(self) -> int:
            return 0

    class _BoomSchema:
        schema_collection = _BoomCollection()

    singletons = Singletons(
        pipeline=object(),
        registry=_FakeRegistry(),  # type: ignore[arg-type]
        schema_index=_BoomSchema(),  # type: ignore[arg-type]
        sql_provider=_FakeProvider(),  # type: ignore[arg-type]
    )

    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: singletons
    r = TestClient(app).get("/databases")
    assert r.status_code == 200
    for row in r.json()["databases"]:
        assert row["table_count"] == 0


# ---------------------------------------------------------- /ask


def test_ask_rejects_unknown_db(client_with_fakes: TestClient) -> None:
    r = client_with_fakes.post(
        "/ask",
        json={"question": "anything", "db_id": "not_a_real_db"},
    )
    assert r.status_code == 404
    assert "unknown db_id" in r.json()["detail"]


def test_ask_returns_canned_pipeline_result(client_with_fakes: TestClient) -> None:
    with patch("nl_sql.api.main.run_pipeline", return_value=_make_pipeline_result()):
        r = client_with_fakes.post(
            "/ask",
            json={"question": "who are the first two artists", "db_id": "chinook"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["sql"] == "SELECT id, name FROM Artist LIMIT 2"
    assert body["db_id"] == "chinook"
    assert body["row_count"] == 2
    assert body["rows"] == [[1, "AC/DC"], [2, "Accept"]]
    assert body["columns"] == ["id", "name"]
    assert body["confidence_label"] == "High"
    assert body["error_kind"] is None
    assert len(body["trace"]) == 1
    assert body["latency_ms"] >= 0.0


def test_ask_propagates_pipeline_error_kind() -> None:
    """When the pipeline returns an ExecutionErrorKind, the response carries it."""
    result = _make_pipeline_result()
    result.error_kind = ExecutionErrorKind.EXECUTION_FAILED
    result.error_message = "no such table: foo"
    result.outcome = None

    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    with patch("nl_sql.api.main.run_pipeline", return_value=result):
        r = TestClient(app).post("/ask", json={"question": "boom", "db_id": "chinook"})
    assert r.status_code == 200
    body = r.json()
    assert body["error_kind"] == "execution_failed"
    assert "no such table" in body["error_message"]
    assert body["row_count"] == 0


def test_ask_confidence_label_buckets() -> None:
    """Spot-check each branch of _confidence_label via /ask responses."""
    for value, expected in [(0.85, "High"), (0.6, "Medium"), (0.1, "Low"), (0.0, "Unknown")]:
        result = _make_pipeline_result()
        result.confidence = value
        app = create_app()
        app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
        with patch("nl_sql.api.main.run_pipeline", return_value=result):
            r = TestClient(app).post("/ask", json={"question": "q", "db_id": "chinook"})
        assert r.status_code == 200, value
        assert r.json()["confidence_label"] == expected, value


# ---------------------------------------------------------- rate limit


def test_rate_limit_kicks_in_after_max_req(monkeypatch: pytest.MonkeyPatch) -> None:
    """61st request with valid key inside the 60-second window → 429."""
    monkeypatch.setenv("NL_SQL_API_KEY", "rl-test-secret")
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    client = TestClient(app)
    headers = {"X-API-Key": "rl-test-secret"}

    # 60 requests should pass
    for _ in range(60):
        r = client.get("/databases", headers=headers)
        assert r.status_code == 200, r.json()

    r = client.get("/databases", headers=headers)
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"]
    assert r.headers.get("Retry-After") is not None


def test_rate_limit_applies_to_anonymous_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """No API key configured → auth is off, but the limiter still throttles by IP.

    This is the B1 regression: previously require_api_key returned "anonymous"
    before ever calling the limiter, so a keyless public deploy had no limit.
    """
    monkeypatch.delenv("NL_SQL_API_KEY", raising=False)
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    client = TestClient(app)

    for _ in range(60):
        r = client.get("/databases")
        assert r.status_code == 200, r.json()

    r = client.get("/databases")
    assert r.status_code == 429
    assert r.headers.get("Retry-After") is not None


def test_wrong_api_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A present-but-wrong key → 401 (exercises the constant-time compare path)."""
    monkeypatch.setenv("NL_SQL_API_KEY", "correct-secret")
    app = create_app()
    app.dependency_overrides[get_singletons] = lambda: _make_fake_singletons()
    r = TestClient(app).get("/databases", headers={"X-API-Key": "wrong-secret"})
    assert r.status_code == 401


def test_ask_response_exposes_truncated_flag(client_with_fakes: TestClient) -> None:
    """B3: the client can tell a full result from a row-capped one."""
    result = _make_pipeline_result()
    assert result.outcome is not None
    assert result.outcome.result is not None
    truncated_result = QueryResult(
        rows=result.outcome.result.rows,
        columns=result.outcome.result.columns,
        row_count=result.outcome.result.row_count,
        truncated=True,
        elapsed_ms=1.0,
    )
    result.outcome = ExecutionOutcome(
        sql=result.outcome.sql,
        validation=result.outcome.validation,
        result=truncated_result,
    )
    with patch("nl_sql.api.main.run_pipeline", return_value=result):
        r = client_with_fakes.post("/ask", json={"question": "q", "db_id": "chinook"})
    assert r.status_code == 200
    assert r.json()["truncated"] is True


def test_ask_500_is_redacted_with_trace_id(client_with_fakes: TestClient) -> None:
    """B2: a pipeline crash returns a generic message + trace_id, not the exc text."""
    secret_detail = "psycopg.OperationalError: password=hunter2 at /srv/secret/path"
    with patch("nl_sql.api.main.run_pipeline", side_effect=RuntimeError(secret_detail)):
        r = client_with_fakes.post("/ask", json={"question": "q", "db_id": "chinook"})
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert "hunter2" not in detail
    assert "/srv/secret/path" not in detail
    assert "trace_id=" in detail
