"""Shared OpenAI-compatible chat-completion helper.

All three slots (Mistral La Plateforme, GitHub Models, Ollama) expose an
OpenAI-compatible /v1/chat/completions endpoint, so we use the official
openai SDK with a per-provider base_url + api_key. This keeps generation
code uniform and makes test mocking trivial (one HTTP shape to mock).
"""

from __future__ import annotations

import time
from typing import Any, cast

from openai import APIError, OpenAI, RateLimitError

from nl_sql.llm.providers.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderError,
)

# Mistral La Plateforme free tier meters per-minute windows: a burst of calls
# passes, then every request 429s until the window refills. The SDK's built-in
# retries give up within seconds, so batch callers (eval) need minute-scale
# patience here.
RATE_LIMIT_BACKOFF_SECONDS: tuple[float, ...] = (15.0, 30.0, 60.0, 120.0)


def chat_complete(
    client: OpenAI,
    model: str,
    req: GenerateRequest,
) -> GenerateResponse:
    """Run a single chat-completion call against an OpenAI-compatible endpoint.

    Returns a normalized GenerateResponse. Wraps SDK errors into ProviderError so
    upstream code never needs to care which SDK raised what.
    """
    messages: list[dict[str, str]] = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    messages.append({"role": "user", "content": req.prompt})

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": cast("list[Any]", messages),
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }
    if req.json_mode:
        # OpenAI-compatible servers (Groq, GitHub Models) accept this; Mistral
        # ignores or 400s depending on model. Caller controls when to set it.
        kwargs["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    completion = None
    for delay in RATE_LIMIT_BACKOFF_SECONDS:
        try:
            completion = client.chat.completions.create(**kwargs)
            break
        except RateLimitError:
            time.sleep(delay)
        except APIError as exc:
            raise ProviderError(f"chat.completions failed for model={model}: {exc}") from exc
    if completion is None:
        try:
            completion = client.chat.completions.create(**kwargs)
        except APIError as exc:
            raise ProviderError(f"chat.completions failed for model={model}: {exc}") from exc

    latency_ms = (time.perf_counter() - started) * 1000.0
    choice = completion.choices[0]
    text = choice.message.content or ""

    usage = completion.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    return GenerateResponse(
        text=text,
        model=completion.model or model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
