"""Tests for the Claude Code CLI provider.

The CLI rides the user's plan, so these tests never launch it: `subprocess.run` is
stubbed and we assert on the argv we would send and on the JSON envelope the CLI is
known to return (captured from the 2026-07-14 probe).
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from nl_sql.llm.providers.base import GenerateRequest, ProviderError
from nl_sql.llm.providers.claude_cli import ClaudeCliProvider

_ENVELOPE = """{
  "type": "result", "subtype": "success", "is_error": false, "num_turns": 1,
  "result": "```sql\\nSELECT 1;\\n```",
  "total_cost_usd": 0.0079,
  "usage": {"input_tokens": 2, "cache_read_input_tokens": 21656,
            "cache_creation_input_tokens": 0, "output_tokens": 94},
  "modelUsage": {"claude-sonnet-5": {"inputTokens": 2, "outputTokens": 94}}
}"""


class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _stub_run(monkeypatch: pytest.MonkeyPatch, stdout: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _fake(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        calls.append({"argv": argv, "input": kwargs.get("input")})
        return _FakeCompleted(stdout)

    monkeypatch.setattr(subprocess, "run", _fake)
    return calls


def test_claude_cli_parses_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run(monkeypatch, _ENVELOPE)

    response = ClaudeCliProvider().generate(GenerateRequest(prompt="write SQL"))

    assert "SELECT 1;" in response.text
    assert response.model == "claude-sonnet-5"
    assert response.output_tokens == 94
    # Cached prefix reads are input the model saw. Counting only `input_tokens`
    # would report 2 tokens per call and make an n=200 run look free.
    assert response.input_tokens == 21658


def test_claude_cli_sends_prompt_over_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The generation prompt runs ~40k characters — past the Windows argv limit."""
    calls = _stub_run(monkeypatch, _ENVELOPE)
    prompt = "x" * 50_000

    ClaudeCliProvider().generate(GenerateRequest(prompt=prompt))

    assert calls[0]["input"] == prompt
    assert prompt not in " ".join(calls[0]["argv"])


def test_claude_cli_replaces_the_harness_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """--system-prompt replaces; --append-system-prompt would leave the agent persona
    in place. Replacing is the whole point: we want a completion, not an agent."""
    calls = _stub_run(monkeypatch, _ENVELOPE)

    ClaudeCliProvider().generate(GenerateRequest(prompt="q", system="you are a SQL expert"))

    argv = calls[0]["argv"]
    assert argv[argv.index("--system-prompt") + 1] == "you are a SQL expert"
    assert "--append-system-prompt" not in argv


def test_claude_cli_leaves_room_for_a_denied_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disallowing tools stops an agent from touching the machine; it does not stop it
    from behaving like an agent. Even toolless, the model sometimes reaches for a tool,
    is denied, and spends the turn on it — at --max-turns 1 the CLI then returns
    `error_max_turns` instead of SQL, and the question scores as a pipeline exception.
    The same trap caught grok_cli first. Both providers must keep turns to spare.
    """
    calls = _stub_run(monkeypatch, _ENVELOPE)

    ClaudeCliProvider().generate(GenerateRequest(prompt="q"))

    argv = calls[0]["argv"]
    assert int(argv[argv.index("--max-turns") + 1]) > 1


def test_claude_cli_surfaces_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_run(
        monkeypatch,
        '{"type":"result","subtype":"error_max_turns","is_error":true,"result":null}',
    )

    with pytest.raises(ProviderError, match="error_max_turns"):
        ClaudeCliProvider().generate(GenerateRequest(prompt="q"))


def test_claude_cli_retries_a_dropped_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spawning the CLI means cmd.exe -> node.exe, and Windows drops that under load.
    On the first n=200 run, 24 questions died on a transient "not found" before the
    model was ever called and scored as misses — a harness failure masquerading as a
    wrong answer. The spawn is worth retrying; the answer is not."""
    monkeypatch.setattr("nl_sql.llm.providers.claude_cli.time.sleep", lambda _s: None)
    attempts: list[int] = []

    def _flaky(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        attempts.append(1)
        if len(attempts) == 1:
            raise FileNotFoundError("claude.cmd")
        return _FakeCompleted(_ENVELOPE)

    monkeypatch.setattr(subprocess, "run", _flaky)

    response = ClaudeCliProvider().generate(GenerateRequest(prompt="q"))

    assert "SELECT 1;" in response.text
    assert len(attempts) == 2, "the dropped spawn must be retried, not surfaced"


def test_claude_cli_gives_up_after_repeated_spawn_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nl_sql.llm.providers.claude_cli.time.sleep", lambda _s: None)

    def _always_fail(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        raise FileNotFoundError("claude.cmd")

    monkeypatch.setattr(subprocess, "run", _always_fail)

    with pytest.raises(ProviderError, match="no usable output"):
        ClaudeCliProvider().generate(GenerateRequest(prompt="q"))
