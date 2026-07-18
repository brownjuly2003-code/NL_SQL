"""Question enrichment (phase A4, E-SQL arXiv:2409.16751).

E-SQL reports ~+5 EA on challenging BIRD from a single extra LLM call that
rewrites the question into an explicit specification — conditions, steps and
schema names spelled out. The enriched text goes into the generate prompt
*in addition to* the original question (never instead: the original stays
authoritative, so an enrichment mistake cannot override it).

Default OFF — wired only when ``PipelineConfig.enrich_question`` is True and
``enrichment_provider`` is set. The call rides the ordinary provider stack,
so it is cached alongside generation calls and replays on reruns.
"""

from __future__ import annotations

import re

from nl_sql.agent.prompts import load_prompt
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider

_ENRICH_MAX_TOKENS = 1024
_MAX_ENRICHED_CHARS = 2000
_FENCE_RE = re.compile(r"```\w*\s*|\s*```")


def clean_enriched_text(text: str) -> str:
    """Normalise the model reply into a short plain-text restatement.

    Strips code fences and whitespace; truncates runaway replies (the block
    is auxiliary — a wall of text would drown the actual question). Returns
    ``""`` for empty/whitespace replies so the caller can skip the block.
    """
    cleaned = _FENCE_RE.sub("", text or "").strip()
    if len(cleaned) > _MAX_ENRICHED_CHARS:
        cleaned = cleaned[:_MAX_ENRICHED_CHARS].rsplit("\n", 1)[0].strip()
    return cleaned


def enrich_question(
    provider: LLMProvider,
    *,
    question: str,
    schema_text: str,
) -> str:
    """One LLM call → explicit restatement of the question ("" on empty)."""
    prompt = load_prompt(
        "enrich_question",
        schema_block=schema_text,
        question=question,
    )
    response = provider.generate(
        GenerateRequest(prompt=prompt, max_tokens=_ENRICH_MAX_TOKENS, temperature=0.0)
    )
    return clean_enriched_text(response.text)
