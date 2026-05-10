"""Ollama local provider — local slot in bakeoff.

Ollama serves an OpenAI-compatible API at /v1 (default port 11434).
No api_key needed; we pass a placeholder string because the openai SDK
requires a non-empty value.
"""

from __future__ import annotations

from openai import OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse


class OllamaProvider:
    name: str = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b-instruct",
        base_url: str = "http://localhost:11434/v1",
    ) -> None:
        self.model = model
        self._client = OpenAI(api_key="ollama-local", base_url=base_url)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        return chat_complete(self._client, self.model, req)
