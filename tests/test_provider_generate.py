"""HTTP-mocked tests for provider .generate() across all three slots.

We mock the wire protocol via respx, so a single mock shape verifies that
every provider correctly maps OpenAI-compatible /v1/chat/completions JSON
to a normalized GenerateResponse.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from nl_sql.llm.providers import GenerateRequest
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider


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
        return_value=httpx.Response(
            200, json=_completion_payload("codestral-latest", "SELECT 1;")
        )
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
    route = respx.post(
        "https://models.inference.ai.azure.com/chat/completions"
    ).mock(
        return_value=httpx.Response(
            200, json=_completion_payload("gpt-4o-mini", "the answer is 42")
        )
    )
    provider = GitHubModelsProvider(token="test-pat")

    response = provider.generate(GenerateRequest(prompt="hello"))

    assert route.called
    assert response.text == "the answer is 42"
    assert response.model == "gpt-4o-mini"
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
def test_generate_passes_system_prompt_when_provided() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.update(_json.loads(request.content))
        return httpx.Response(
            200, json=_completion_payload("codestral-latest", "ok")
        )

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
