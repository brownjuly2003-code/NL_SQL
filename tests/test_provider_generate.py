"""HTTP-mocked tests for provider .generate() across all three slots.

We mock the wire protocol via respx, so a single mock shape verifies that
every provider correctly maps OpenAI-compatible /v1/chat/completions JSON
to a normalized GenerateResponse.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from nl_sql.llm.providers import GenerateRequest, ProviderError
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider
from nl_sql.llm.providers.zen import ZenProvider

ZEN_URL = "https://opencode.ai/zen/v1/chat/completions"


def _completion_payload(model: str, text: str) -> dict[str, object]:
    return {
        "id": "cmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 17, "completion_tokens": 5, "total_tokens": 22},
    }


@respx.mock
def test_mistral_generate_returns_normalized_response() -> None:
    route = respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion_payload("codestral-latest", "SELECT 1;"))
    )
    provider = MistralProvider(api_key="test-key")

    response = provider.generate(GenerateRequest(prompt="say SELECT 1"))

    assert route.called
    assert response.text == "SELECT 1;"
    assert response.model == "codestral-latest"
    assert response.input_tokens == 17
    assert response.output_tokens == 5
    assert response.latency_ms >= 0


@respx.mock
def test_github_models_generate_returns_normalized_response() -> None:
    route = respx.post("https://models.github.ai/inference/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_completion_payload("openai/gpt-4o-mini", "the answer is 42")
        )
    )
    provider = GitHubModelsProvider(token="test-pat")

    response = provider.generate(GenerateRequest(prompt="hello"))

    assert route.called
    assert response.text == "the answer is 42"
    assert response.model == "openai/gpt-4o-mini"
    assert response.input_tokens == 17
    assert response.output_tokens == 5


@respx.mock
def test_ollama_generate_returns_normalized_response() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json=_completion_payload("qwen2.5-coder:7b-instruct", "SELECT count(*) FROM t;"),
        )
    )
    provider = OllamaProvider()

    response = provider.generate(GenerateRequest(prompt="count rows"))

    assert route.called
    assert response.text == "SELECT count(*) FROM t;"
    assert response.model == "qwen2.5-coder:7b-instruct"


@respx.mock
def test_ollama_generate_does_not_retry_failures() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "local model timed out"})
    )
    provider = OllamaProvider()

    with pytest.raises(ProviderError):
        provider.generate(GenerateRequest(prompt="count rows"))

    assert route.call_count == 1


@respx.mock
def test_generate_passes_system_prompt_when_provided() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.update(_json.loads(request.content))
        return httpx.Response(200, json=_completion_payload("codestral-latest", "ok"))

    respx.post("https://api.mistral.ai/v1/chat/completions").mock(side_effect=_capture)

    provider = MistralProvider(api_key="test-key")
    provider.generate(
        GenerateRequest(prompt="user q", system="you are a SQL expert", temperature=0.2)
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": "you are a SQL expert"}
    assert messages[1] == {"role": "user", "content": "user q"}
    assert captured["temperature"] == pytest.approx(0.2)


@respx.mock
def test_mistral_generate_retries_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from nl_sql.llm.providers import _openai_compat

    naps: list[float] = []
    monkeypatch.setattr(_openai_compat.time, "sleep", naps.append)
    rate_limited = httpx.Response(429, json={"object": "error", "type": "rate_limited"})
    # The openai SDK itself retries a 429 twice before raising RateLimitError,
    # so three 429s exhaust one SDK call and hand control to our backoff layer.
    route = respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        side_effect=[
            rate_limited,
            rate_limited,
            rate_limited,
            httpx.Response(200, json=_completion_payload("codestral-latest", "SELECT 1;")),
        ]
    )
    provider = MistralProvider(api_key="test-key")

    response = provider.generate(GenerateRequest(prompt="say SELECT 1"))

    assert route.call_count == 4
    assert response.text == "SELECT 1;"
    assert [nap for nap in naps if nap >= 15.0] == [15.0]


@respx.mock
def test_zen_generate_returns_normalized_response() -> None:
    route = respx.post(ZEN_URL).mock(
        return_value=httpx.Response(
            200, json=_completion_payload("deepseek-v4-flash-free", "SELECT 1;")
        )
    )
    provider = ZenProvider(api_key="test-key")

    response = provider.generate(GenerateRequest(prompt="say SELECT 1"))

    assert route.called
    assert response.text == "SELECT 1;"
    assert response.model == "deepseek-v4-flash-free"


@respx.mock
def test_zen_floors_max_tokens_so_reasoning_cannot_eat_the_answer() -> None:
    """Every free Zen model is a reasoning model and reasoning bills against
    max_tokens. At the caller's 2048 the model thinks past the budget and returns
    an empty completion (4/5 on the first n=5 smoke). The floor lives here, not in
    GenerateRequest, because the LLM cache keys on max_tokens — raising the shared
    default would invalidate every cached codestral response behind the product number.
    """
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.update(_json.loads(request.content))
        return httpx.Response(200, json=_completion_payload("deepseek-v4-flash-free", "SELECT 1;"))

    respx.post(ZEN_URL).mock(side_effect=_capture)
    provider = ZenProvider(api_key="test-key", min_max_tokens=16384)

    provider.generate(GenerateRequest(prompt="q", max_tokens=2048))

    assert captured["max_tokens"] == 16384


@respx.mock
def test_zen_rotates_to_a_spare_key_before_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zen free tiers meter per key, so a 429 on one key is not a 429 on the next.
    Rotating costs a round-trip; sleeping costs 15s+ per question across n=200."""
    from nl_sql.llm.providers import _openai_compat

    naps: list[float] = []
    monkeypatch.setattr(_openai_compat.time, "sleep", naps.append)
    seen: list[str] = []

    def _by_key(request: httpx.Request) -> httpx.Response:
        auth = request.headers["authorization"]
        seen.append(auth)
        if auth == "Bearer key-one":
            return httpx.Response(429, json={"object": "error", "type": "rate_limited"})
        return httpx.Response(200, json=_completion_payload("deepseek-v4-flash-free", "SELECT 1;"))

    respx.post(ZEN_URL).mock(side_effect=_by_key)
    provider = ZenProvider(api_key="key-one, key-two")

    response = provider.generate(GenerateRequest(prompt="q"))

    assert response.text == "SELECT 1;"
    assert seen[-1] == "Bearer key-two"
    assert not [nap for nap in naps if nap >= 15.0], "a spare key must be tried before backoff"


def test_zen_requires_at_least_one_key() -> None:
    with pytest.raises(ProviderError, match="non-empty api_key"):
        ZenProvider(api_key="  ,  ")
