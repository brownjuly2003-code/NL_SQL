"""Instance-aware synthetic few-shot generation (phase A3, CHASE-SQL 2410.01943).

CHASE-SQL Table 4 credits instance-aware synthetic examples with the largest
single lever in the literature (+9.3 EA on Gemini): instead of retrieving
train-set Q→SQL pairs, one extra LLM call writes a few fresh pairs against
the *target* schema, mirroring the structural form of the target question.
The pairs replace the retrieved few-shots in the generate prompt.

Default OFF — wired only when ``PipelineConfig.fewshot_selection ==
"synthetic"`` and ``fewshot_synthesis_provider`` is set. The synthesis call
goes through the ordinary provider stack, so it is cached alongside
generation calls and replays on reruns.
"""

from __future__ import annotations

from nl_sql.agent.nodes._text_utils import _safe_loads, _strip_code_fence
from nl_sql.agent.prompts import load_prompt
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider
from nl_sql.schema_index.indexer import FewShotHit

MAX_SYNTHETIC_FEWSHOTS = 4
_SYNTHESIS_MAX_TOKENS = 2048


def parse_synthetic_pairs(text: str) -> list[tuple[str, str]]:
    """Parse the model reply into ``(question, sql)`` pairs.

    Tolerates a fenced JSON block. Entries that are not objects with
    non-empty string ``question``/``sql`` (where sql contains a SELECT)
    are dropped; an unparseable reply yields ``[]`` so the caller can
    fall back to the retrieved shots.
    """
    data = _safe_loads(_strip_code_fence(text or ""))
    if not isinstance(data, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        sql = str(item.get("sql") or "").strip()
        if not question or not sql or "select" not in sql.lower():
            continue
        pairs.append((question, sql))
        if len(pairs) >= MAX_SYNTHETIC_FEWSHOTS:
            break
    return pairs


def synthesize_fewshots(
    provider: LLMProvider,
    *,
    question: str,
    db_id: str,
    dialect: str,
    schema_text: str,
    num_examples: int = 3,
) -> list[FewShotHit]:
    """One LLM call → synthetic few-shot hits for the current question."""
    prompt = load_prompt(
        "synthesize_fewshots",
        dialect=dialect,
        schema_block=schema_text,
        question=question,
        num_examples=num_examples,
    )
    response = provider.generate(
        GenerateRequest(prompt=prompt, max_tokens=_SYNTHESIS_MAX_TOKENS, temperature=0.0)
    )
    return [
        FewShotHit(
            example_id=f"synthetic-{idx}",
            db_id=db_id,
            question=q,
            sql=sql,
            distance=0.0,
            metadata={"source": "synthetic"},
        )
        for idx, (q, sql) in enumerate(parse_synthetic_pairs(response.text), start=1)
    ]
