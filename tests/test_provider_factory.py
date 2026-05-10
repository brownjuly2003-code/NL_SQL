from __future__ import annotations

import pytest

from nl_sql.config import Settings
from nl_sql.llm.providers import ProviderError, build_provider
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider


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
    assert provider.model == "gpt-4o-mini"


def test_factory_builds_ollama_without_credentials() -> None:
    settings = Settings()  # type: ignore[call-arg]
    provider = build_provider("ollama", settings=settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


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
