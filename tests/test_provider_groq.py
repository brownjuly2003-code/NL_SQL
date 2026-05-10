from __future__ import annotations

import httpx
import pytest
import respx

from nl_sql.config import Settings
from nl_sql.llm.providers import GenerateRequest, ProviderError, build_provider
from nl_sql.llm.providers.groq import GroqProvider


def _completion_payload(model: str, text: str) -> dict[str, object]:
    return {
        "id": "cmpl-groq",
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
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def test_factory_builds_groq() -> None:
    settings = Settings(groq_api_key="test-groq")  # type: ignore[call-arg]
    provider = build_provider("groq", settings=settings)
    assert isinstance(provider, GroqProvider)
    assert provider.name == "groq"
    assert provider.model == "llama-3.3-70b-versatile"


def test_groq_provider_requires_api_key() -> None:
    with pytest.raises(ProviderError, match="non-empty api_key"):
        GroqProvider(api_key="")


@respx.mock
def test_groq_generate_returns_normalized_response() -> None:
    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json=_completion_payload("llama-3.3-70b-versatile", "SELECT 1 AS answer;"),
        )
    )
    provider = GroqProvider(api_key="test-key")

    response = provider.generate(GenerateRequest(prompt="emit a SELECT"))

    assert route.called
    assert response.text == "SELECT 1 AS answer;"
    assert response.model == "llama-3.3-70b-versatile"
    assert response.input_tokens == 11
    assert response.output_tokens == 7
