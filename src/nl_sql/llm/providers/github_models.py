"""GitHub Models provider — frontier slot in $0-budget bakeoff.

Endpoint: https://models.inference.ai.azure.com (OpenAI-compatible).
Auth: GitHub Personal Access Token (no scope required, or read:user).
Free for personal GitHub accounts with daily rate limits.
"""

from __future__ import annotations

from openai import OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)


class GitHubModelsProvider:
    name: str = "github_models"

    def __init__(
        self,
        token: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://models.inference.ai.azure.com",
    ) -> None:
        if not token:
            raise ProviderError("GitHubModelsProvider requires non-empty GitHub PAT")
        self.model = model
        self._client = OpenAI(api_key=token, base_url=base_url)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        return chat_complete(self._client, self.model, req)
