"""Unit tests for the GraceKelly orchestrate provider (AgentFlow ADR 0008 slot).

Mock the HTTP layer so these run without a live GraceKelly server; a live smoke
is done separately against a running instance.
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest import mock
from urllib import error as urlerror

import pytest

from nl_sql.llm.providers import GenerateRequest, ProviderError, build_provider
from nl_sql.llm.providers.gracekelly import GraceKellyProvider


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _orchestrate_body(**overrides: Any) -> bytes:
    payload = {
        "status": "completed",
        "output_text": "SELECT COUNT(*) FROM orders_v2 WHERE status = 'cancelled';",
        "model": {"id": "claude-sonnet-5-0", "display_name": "Claude Sonnet 5.0"},
        "failure_message": None,
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def test_factory_builds_gracekelly_with_sonnet_5() -> None:
    provider = build_provider("gracekelly")
    assert isinstance(provider, GraceKellyProvider)
    assert provider.name == "gracekelly"
    assert provider.model == "claude-sonnet-5"


def test_generate_posts_orchestrate_and_parses_output_text() -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(_orchestrate_body())

    provider = GraceKellyProvider(model="claude-sonnet-5", base_url="http://127.0.0.1:8011")
    with mock.patch("nl_sql.llm.providers.gracekelly.urlrequest.urlopen", fake_urlopen):
        resp = provider.generate(GenerateRequest(prompt="how many orders were cancelled?"))

    assert captured["url"] == "http://127.0.0.1:8011/api/v1/orchestrate"
    assert captured["body"] == {
        "prompt": "how many orders were cancelled?",
        "model": "claude-sonnet-5",
    }
    assert resp.text == "SELECT COUNT(*) FROM orders_v2 WHERE status = 'cancelled';"
    assert resp.model == "claude-sonnet-5-0"


def test_generate_prepends_system_prompt() -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(_orchestrate_body())

    provider = GraceKellyProvider()
    with mock.patch("nl_sql.llm.providers.gracekelly.urlrequest.urlopen", fake_urlopen):
        provider.generate(
            GenerateRequest(system="You are a DuckDB SQL generator.", prompt="revenue?")
        )

    assert captured["body"]["prompt"] == "You are a DuckDB SQL generator.\n\nrevenue?"


def test_generate_unwraps_sql_json_envelope() -> None:
    envelope = json.dumps({"sql": "SELECT 1", "rationale": "trivial"})

    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(_orchestrate_body(output_text=envelope))

    provider = GraceKellyProvider()
    with mock.patch("nl_sql.llm.providers.gracekelly.urlrequest.urlopen", fake_urlopen):
        resp = provider.generate(GenerateRequest(prompt="q"))

    assert resp.text == "SELECT 1"


def test_generate_raises_on_orchestrate_failure() -> None:
    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(_orchestrate_body(output_text="", failure_message="browser timeout"))

    provider = GraceKellyProvider()
    with (
        mock.patch("nl_sql.llm.providers.gracekelly.urlrequest.urlopen", fake_urlopen),
        pytest.raises(ProviderError, match="browser timeout"),
    ):
        provider.generate(GenerateRequest(prompt="q"))


def test_generate_wraps_http_error() -> None:
    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        raise urlerror.HTTPError(req.full_url, 422, "Unsupported model", {}, io.BytesIO(b"nope"))  # type: ignore[arg-type]

    provider = GraceKellyProvider()
    with (
        mock.patch("nl_sql.llm.providers.gracekelly.urlrequest.urlopen", fake_urlopen),
        pytest.raises(ProviderError, match="422"),
    ):
        provider.generate(GenerateRequest(prompt="q"))


def test_empty_model_rejected() -> None:
    with pytest.raises(ProviderError):
        GraceKellyProvider(model="  ")
