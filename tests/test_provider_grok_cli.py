"""Tests for the Grok Build CLI provider.

The CLI is a subscription path with a weekly quota that belongs to the user, so
these tests never launch it: `subprocess.run` is stubbed and we assert on the argv
we would have sent and on the JSON envelope we know it returns (captured from the
2026-07-14 probe).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from nl_sql.llm.providers.base import GenerateRequest, ProviderError
from nl_sql.llm.providers.grok_cli import GrokCliProvider

_ENVELOPE = """{
  "text": "SELECT 1;",
  "stopReason": "EndTurn",
  "usage": {"input_tokens": 13472, "output_tokens": 84, "reasoning_tokens": 0},
  "modelUsage": {"grok-composer-2.5-fast": {"inputTokens": 13472, "modelCalls": 1}}
}"""


class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _stub_run(
    monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int = 0, stderr: str = ""
) -> list[list[str]]:
    """Capture argv instead of running the CLI. Returns the list of calls made."""
    calls: list[list[str]] = []

    def _fake(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        calls.append(argv)
        # The prompt must reach the CLI as a file: the generation prompt is ~40k
        # characters, well past the Windows argv limit.
        idx = argv.index("--prompt-file")
        assert Path(argv[idx + 1]).read_text(encoding="utf-8")
        return _FakeCompleted(stdout, returncode, stderr)

    monkeypatch.setattr(subprocess, "run", _fake)
    return calls


def test_grok_cli_parses_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run(monkeypatch, _ENVELOPE)
    provider = GrokCliProvider()

    response = provider.generate(GenerateRequest(prompt="write SQL"))

    assert response.text == "SELECT 1;"
    assert response.input_tokens == 13472
    assert response.output_tokens == 84
    # The label is what the tier actually served, not what we asked for.
    assert response.model == "grok-composer-2.5-fast"


def test_grok_cli_runs_toolless(monkeypatch: pytest.MonkeyPatch) -> None:
    """A generator has no business reading files or browsing, and a stray tool turn
    burns the user's weekly quota. That is an argv-level guarantee, so assert it."""
    calls = _stub_run(monkeypatch, _ENVELOPE)
    provider = GrokCliProvider()

    provider.generate(GenerateRequest(prompt="write SQL", system="you are a SQL expert"))

    argv = calls[0]
    assert argv[argv.index("--system-prompt-override") + 1] == "you are a SQL expert"
    disallowed = argv[argv.index("--disallowed-tools") + 1]
    for tool in ("bash", "read", "write", "websearch"):
        assert tool in disallowed
    assert "--verbatim" in argv
    assert "--no-memory" in argv


def test_grok_cli_leaves_room_for_the_agent_preamble(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--max-turns 1` is the obvious way to make an agent behave as a completion, and
    it is wrong. Grok spends turn one announcing what it is about to do and reaching for
    a tool; cut there, it returns that preamble as the answer (stopReason: Cancelled).
    The first n=200 run scored 47.0% with 31% invalid SQL — measuring this bug, not the
    model. Several turns let it talk past the preamble and emit the SQL.
    """
    calls = _stub_run(monkeypatch, _ENVELOPE)

    GrokCliProvider().generate(GenerateRequest(prompt="write SQL"))

    argv = calls[0]
    assert int(argv[argv.index("--max-turns") + 1]) > 1


def test_grok_cli_surfaces_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed run prints a JSON error object *and* a trailing plain-text line, so
    the parser must read the first document and report the message, not choke."""
    stdout = (
        '{"type":"error","message":"Couldn\'t set model \'x\': unknown model id"}\n'
        "Error: Couldn't set model 'x': unknown model id\n"
    )
    _stub_run(monkeypatch, stdout, returncode=1)
    provider = GrokCliProvider()

    with pytest.raises(ProviderError, match="unknown model id"):
        provider.generate(GenerateRequest(prompt="q"))


def test_grok_cli_reports_non_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run(monkeypatch, "", returncode=127, stderr="grok: command not found")
    provider = GrokCliProvider()

    with pytest.raises(ProviderError, match="no JSON"):
        provider.generate(GenerateRequest(prompt="q"))
