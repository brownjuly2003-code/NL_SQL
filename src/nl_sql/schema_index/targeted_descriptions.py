"""Targeted column descriptions (phase A8).

Whole-schema description injection at index-build time cost -1.5 EA — the
prose paid prompt rent on every question whether relevant or not
(docs/BACKLOG.md). This is the targeted variant: at query time, embed the
question against the description lines of the *retrieved* tables only and
keep the top-k most similar lines. No chroma rebuild — descriptions are
loaded from BIRD's ``database_description/*.csv`` next to the SQLite file,
and the per-line embeddings are cached per text, so a full run pays for
each database's lines once.

Default OFF — wired only when ``PipelineConfig.description_embedder`` is
set (``scripts/eval_baseline.py --column-descriptions targeted``).
"""

from __future__ import annotations

import math

from nl_sql.llm.providers.base import EmbeddingProvider, EmbedRequest
from nl_sql.schema_index.descriptions import load_column_descriptions

DEFAULT_TOP_K = 5


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def select_targeted_descriptions(
    embedder: EmbeddingProvider,
    *,
    question: str,
    db_url: str,
    tables: list[str],
    top_k: int = DEFAULT_TOP_K,
) -> list[str]:
    """Top-k description lines for ``tables``, ranked by similarity to the question.

    Returns ``[]`` when the database ships no descriptions (everything
    outside BIRD) or none of the retrieved tables have any.
    """
    if not question or not tables:
        return []
    desc = load_column_descriptions(db_url)
    if not desc:
        return []
    wanted = {t.lower() for t in tables}
    lines: list[str] = []
    for table, columns in desc.items():
        if table.lower() not in wanted:
            continue
        for column, text in columns.items():
            lines.append(f"{table}.{column}: {text}")
    if not lines:
        return []
    vectors = embedder.embed(EmbedRequest(texts=[question, *lines])).vectors
    question_vec = list(vectors[0])
    scored = sorted(
        zip(lines, (list(v) for v in vectors[1:]), strict=True),
        key=lambda pair: _cosine(question_vec, pair[1]),
        reverse=True,
    )
    return [line for line, _ in scored[:top_k]]


def render_column_notes(lines: list[str]) -> str:
    """Render selected lines as the prompt appendix block ("" when empty)."""
    if not lines:
        return ""
    return "Column notes (dataset descriptions for likely-relevant columns):\n" + "\n".join(
        f"- {line}" for line in lines
    )
