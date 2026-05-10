from __future__ import annotations

from nl_sql.llm.providers import EmbeddingProvider, LLMProvider
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider


def test_mistral_satisfies_both_protocols() -> None:
    provider = MistralProvider(api_key="test-key")
    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, EmbeddingProvider)


def test_github_models_satisfies_llm_protocol() -> None:
    provider = GitHubModelsProvider(token="test-pat")
    assert isinstance(provider, LLMProvider)
    assert not isinstance(provider, EmbeddingProvider)


def test_ollama_satisfies_llm_protocol() -> None:
    provider = OllamaProvider()
    assert isinstance(provider, LLMProvider)
    assert not isinstance(provider, EmbeddingProvider)
