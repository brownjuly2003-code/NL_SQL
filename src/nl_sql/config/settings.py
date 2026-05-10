from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["mistral", "github_models", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NL_SQL_",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    log_level: str = "INFO"

    default_provider: ProviderName = "mistral"
    frontier_provider: ProviderName = "github_models"
    local_provider: ProviderName = "ollama"

    mistral_gen_model: str = "codestral-latest"
    mistral_nl_model: str = "mistral-large-latest"
    mistral_embed_model: str = "mistral-embed"
    mistral_base_url: str = "https://api.mistral.ai/v1"

    github_models_model: str = "gpt-4o-mini"
    github_models_base_url: str = "https://models.inference.ai.azure.com"

    ollama_gen_model: str = "qwen2.5-coder:7b-instruct"
    ollama_base_url: str = "http://localhost:11434/v1"

    mistral_api_key: str = Field(default="", validation_alias="MISTRAL_API_KEY")
    github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
