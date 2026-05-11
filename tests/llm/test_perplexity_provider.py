"""Unit tests for PerplexityProvider.

The provider just posts JSON to a local GraceKelly URL and parses the
response, so we mock urllib's urlopen rather than running a live server.
The interesting branch is the ANSI-escape stripping — Perplexity's web UI
can return formatting codes around quoted strings that break downstream
JSON / SQL parsing.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from nl_sql.llm.providers.base import GenerateRequest, ProviderError
from nl_sql.llm.providers.perplexity import PerplexityProvider


def _fake_response(payload: dict[str, object]) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_generate_strips_ansi_escape_codes() -> None:
    """Perplexity sometimes wraps quoted values in ANSI underline codes.

    Without stripping, downstream JSON parsers see `\\x1b[4m"..."\\x1b[0m` (or the
    bracket variant `[4m..."[0m`) and fail with "Unexpected token".
    """
    provider = PerplexityProvider(model="claude-sonnet-4-6")
    ansi_dirty = (
        'SELECT * FROM t WHERE name IN ([4m"a"[0m, [4m"b"[0m)'
    )
    response = _fake_response({"answer": ansi_dirty, "model_id": "claude-sonnet-4-6"})

    with patch("nl_sql.llm.providers.perplexity.urlrequest.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        result = provider.generate(GenerateRequest(prompt="anything"))

    assert "[4m" not in result.text
    assert "[0m" not in result.text
    assert result.text == 'SELECT * FROM t WHERE name IN ("a", "b")'


def test_generate_preserves_clean_text() -> None:
    provider = PerplexityProvider(model="claude-sonnet-4-6")
    clean_sql = "SELECT COUNT(*) FROM Album"
    response = _fake_response({"answer": clean_sql, "model_id": "claude-sonnet-4-6"})

    with patch("nl_sql.llm.providers.perplexity.urlrequest.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        result = provider.generate(GenerateRequest(prompt="anything"))

    assert result.text == clean_sql
    assert result.model == "claude-sonnet-4-6"


def test_generate_propagates_real_ansi_csi_sequences() -> None:
    """The raw `\\x1b[...m` form (real CSI) must also strip."""
    provider = PerplexityProvider(model="claude-sonnet-4-6")
    dirty = "\x1b[31mSELECT 1\x1b[0m"
    response = _fake_response({"answer": dirty, "model_id": "claude-sonnet-4-6"})

    with patch("nl_sql.llm.providers.perplexity.urlrequest.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        result = provider.generate(GenerateRequest(prompt="x"))

    assert result.text == "SELECT 1"


def test_empty_model_rejected() -> None:
    with pytest.raises(ProviderError, match="non-empty model"):
        PerplexityProvider(model="")


def test_generate_unwraps_sql_json_envelope() -> None:
    """When Sonnet returns the full generate_sql output contract as a JSON
    string, the provider should hand the parser just the inner SQL."""
    provider = PerplexityProvider(model="claude-sonnet-4-6")
    envelope = (
        '{"sql": "SELECT COUNT(*) FROM Album", '
        '"rationale": "counted all albums", '
        '"tables_used": ["Album"], "confidence": 0.92}'
    )
    response = _fake_response({"answer": envelope, "model_id": "claude-sonnet-4-6"})
    with patch("nl_sql.llm.providers.perplexity.urlrequest.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        result = provider.generate(GenerateRequest(prompt="how many?"))
    assert result.text == "SELECT COUNT(*) FROM Album"


def test_generate_tolerates_trailing_prose_after_json() -> None:
    """Sonnet sometimes appends a sentence after the JSON block; cope."""
    provider = PerplexityProvider(model="claude-sonnet-4-6")
    envelope = (
        '{"sql": "SELECT 1", "rationale": "trivial", "tables_used": [], '
        '"confidence": 0.5}\n\nLet me know if you need anything else!'
    )
    response = _fake_response({"answer": envelope, "model_id": "claude-sonnet-4-6"})
    with patch("nl_sql.llm.providers.perplexity.urlrequest.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        result = provider.generate(GenerateRequest(prompt="x"))
    assert result.text == "SELECT 1"


def test_generate_leaves_bare_sql_alone() -> None:
    """The unwrap step must be a no-op when the answer is already a bare SQL string."""
    provider = PerplexityProvider(model="claude-sonnet-4-6")
    bare = "SELECT 1 FROM t WHERE name = 'sql'"
    response = _fake_response({"answer": bare, "model_id": "claude-sonnet-4-6"})
    with patch("nl_sql.llm.providers.perplexity.urlrequest.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        result = provider.generate(GenerateRequest(prompt="x"))
    assert result.text == bare


def test_unreachable_url_raises_provider_error() -> None:
    """If GraceKelly isn't running, the error message should point the user at the fix."""
    provider = PerplexityProvider(model="claude-sonnet-4-6", base_url="http://127.0.0.1:1")
    with pytest.raises(ProviderError, match="GraceKelly unreachable"):
        provider.generate(GenerateRequest(prompt="x"))
