"""Local vLLM provider — GPU-session student-model slot (S2, `plan_autotune.md`).

Endpoint: an OpenAI-compatible server started by `vllm serve <model>` on a
rented GPU box — one process, one model. Same shape as `ollama.py` (local,
no real auth needed) with one difference: Ollama always lives at a fixed
`localhost:11434`, but the GPU host changes every rental (and may be exposed
through an SSH tunnel or a public URL), so `base_url` has no meaningful code
default here — it must come from `.env` (`NL_SQL_LOCAL_LLM_BASE_URL`) at
session time. The code default below is only a same-box fallback for local
smoke-testing against `vllm serve` on the default port.

Auth: vLLM's OpenAI-compatible server accepts any bearer token unless
started with `--api-key` (rare for a single-tenant rented box). The openai
SDK still requires a non-empty string, so `NL_SQL_LOCAL_LLM_API_KEY`
defaults to the literal `"dummy"` — override it only if the box enforces one.
"""

from __future__ import annotations

from openai import OpenAI

from nl_sql.llm.providers._openai_compat import chat_complete
from nl_sql.llm.providers.base import GenerateRequest, GenerateResponse


class LocalVLLMProvider:
    name: str = "local_vllm"

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
        api_key: str = "dummy",
        timeout_seconds: float = 180.0,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = OpenAI(
            api_key=api_key or "dummy",
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        return chat_complete(self._client, self.model, req)
