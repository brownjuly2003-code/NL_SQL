"""Provider factory — builds an LLMProvider by name from settings."""

from __future__ import annotations

from nl_sql.config import Settings, get_settings
from nl_sql.llm.providers.base import LLMProvider, ProviderError
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider


def build_provider(name: str, settings: Settings | None = None) -> LLMProvider:
    """Build an LLMProvider by short name.

    Recognized names: "mistral", "github_models", "ollama".
    Raises ProviderError for unknown names or missing credentials.
    """
    s = settings or get_settings()
    match name:
        case "mistral":
            return MistralProvider(
                api_key=s.mistral_api_key,
                gen_model=s.mistral_gen_model,
                embed_model=s.mistral_embed_model,
                base_url=s.mistral_base_url,
            )
        case "github_models":
            return GitHubModelsProvider(
                token=s.github_token,
                model=s.github_models_model,
                base_url=s.github_models_base_url,
            )
        case "ollama":
            return OllamaProvider(
                model=s.ollama_gen_model,
                base_url=s.ollama_base_url,
            )
        case _:
            raise ProviderError(f"unknown provider name: {name!r}")
