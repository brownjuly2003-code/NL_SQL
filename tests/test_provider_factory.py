from __future__ import annotations

import pytest

from nl_sql.config import Settings
from nl_sql.llm.providers import ProviderError, build_provider
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.local_vllm import LocalVLLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider
from nl_sql.llm.providers.openrouter import OpenRouterProvider


def test_factory_builds_mistral() -> None:
    settings = Settings(mistral_api_key="test-key")  # type: ignore[call-arg]
    provider = build_provider("mistral", settings=settings)
    assert isinstance(provider, MistralProvider)
    assert provider.name == "mistral"
    assert provider.model == "codestral-latest"


def test_factory_builds_github_models() -> None:
    settings = Settings(github_token="test-pat")  # type: ignore[call-arg]
    provider = build_provider("github_models", settings=settings)
    assert isinstance(provider, GitHubModelsProvider)
    assert provider.name == "github_models"
    assert provider.model == "openai/gpt-4o-mini"


def test_factory_builds_ollama_without_credentials() -> None:
    settings = Settings(ollama_timeout_seconds=42.0)  # type: ignore[call-arg]
    provider = build_provider("ollama", settings=settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"
    assert provider.timeout_seconds == 42.0


def test_factory_raises_on_unknown_provider() -> None:
    settings = Settings()  # type: ignore[call-arg]
    with pytest.raises(ProviderError, match="unknown provider"):
        build_provider("definitely-not-a-provider", settings=settings)


def test_mistral_provider_requires_api_key() -> None:
    with pytest.raises(ProviderError, match="non-empty api_key"):
        MistralProvider(api_key="")


def test_github_models_provider_requires_token() -> None:
    with pytest.raises(ProviderError, match="non-empty GitHub PAT"):
        GitHubModelsProvider(token="")


def test_factory_builds_openrouter() -> None:
    settings = Settings(openrouter_api_key="test-or-key")  # type: ignore[call-arg]
    provider = build_provider("openrouter", settings=settings)
    assert isinstance(provider, OpenRouterProvider)
    assert provider.name == "openrouter"
    # The old default (deepseek-v4-flash:free) no longer exists — OpenRouter 404s
    # and points at the paid slug, so this provider had been quietly dead.
    assert provider.model == "qwen/qwen3-coder:free"


def test_openrouter_provider_requires_api_key() -> None:
    with pytest.raises(ProviderError, match="non-empty api_key"):
        OpenRouterProvider(api_key="")


def test_factory_builds_local_vllm() -> None:
    settings = Settings(  # type: ignore[call-arg]
        local_llm_base_url="http://10.0.0.1:8000/v1",
        local_llm_model="Qwen/Qwen2.5-Coder-7B-Instruct",
    )
    provider = build_provider("local_vllm", settings=settings)
    assert isinstance(provider, LocalVLLMProvider)
    assert provider.name == "local_vllm"
    assert provider.model == "Qwen/Qwen2.5-Coder-7B-Instruct"


def test_factory_builds_local_vllm_without_credentials() -> None:
    """No GPU box rented yet: base_url/api_key fall back to code defaults
    (localhost + "dummy"), matching the ollama slot's no-credentials case."""
    settings = Settings()  # type: ignore[call-arg]
    provider = build_provider("local_vllm", settings=settings)
    assert isinstance(provider, LocalVLLMProvider)
    assert provider.model == "Qwen/Qwen2.5-Coder-7B-Instruct"
