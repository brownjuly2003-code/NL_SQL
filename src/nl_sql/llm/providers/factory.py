"""Provider factory — builds an LLMProvider by name from settings."""

from __future__ import annotations

from nl_sql.config import Settings, get_settings
from nl_sql.llm.providers.base import LLMProvider, ProviderError
from nl_sql.llm.providers.claude_cli import ClaudeCliProvider
from nl_sql.llm.providers.github_models import GitHubModelsProvider
from nl_sql.llm.providers.gracekelly import GraceKellyProvider
from nl_sql.llm.providers.grok_cli import GrokCliProvider
from nl_sql.llm.providers.groq import GroqProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.llm.providers.ollama import OllamaProvider
from nl_sql.llm.providers.openrouter import OpenRouterProvider
from nl_sql.llm.providers.perplexity import PerplexityProvider
from nl_sql.llm.providers.zen import ZenProvider


def build_provider(name: str, settings: Settings | None = None) -> LLMProvider:
    """Build an LLMProvider by short name.

    Recognized names: ``mistral``, ``github_models``, ``groq``, ``ollama``,
    ``perplexity``, ``openrouter``, ``gracekelly``, ``zen``, ``grok_cli``. Raises
    ProviderError for unknown names or missing credentials.
    """
    s = settings or get_settings()
    match name:
        case "gracekelly":
            return GraceKellyProvider(
                model=s.gracekelly_model,
                base_url=s.gracekelly_base_url,
                timeout_seconds=s.gracekelly_timeout_seconds,
            )
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
        case "groq":
            return GroqProvider(
                api_key=s.groq_api_key,
                model=s.groq_model,
                base_url=s.groq_base_url,
            )
        case "ollama":
            return OllamaProvider(
                model=s.ollama_gen_model,
                base_url=s.ollama_base_url,
                timeout_seconds=s.ollama_timeout_seconds,
            )
        case "perplexity":
            return PerplexityProvider(
                model=s.perplexity_browser_model,
                base_url=s.perplexity_base_url,
            )
        case "openrouter":
            return OpenRouterProvider(
                api_key=s.openrouter_api_key,
                model=s.openrouter_model,
                base_url=s.openrouter_base_url,
            )
        case "zen":
            return ZenProvider(
                api_key=s.zen_api_key,
                model=s.zen_model,
                base_url=s.zen_base_url,
                timeout_seconds=s.zen_timeout_seconds,
            )
        case "grok_cli":
            return GrokCliProvider(
                cli_path=s.grok_cli_path,
                model=s.grok_cli_model,
                timeout_seconds=s.grok_cli_timeout_seconds,
                max_turns=s.grok_cli_max_turns,
            )
        case "claude_cli":
            return ClaudeCliProvider(
                cli_path=s.claude_cli_path,
                model=s.claude_cli_model,
                timeout_seconds=s.claude_cli_timeout_seconds,
                max_turns=s.claude_cli_max_turns,
            )
        case _:
            raise ProviderError(f"unknown provider name: {name!r}")
