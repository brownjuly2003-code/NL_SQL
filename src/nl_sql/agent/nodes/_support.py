"""Shared helpers used by multiple nodes.

Kept separate from the public node factories so changes to JSON parsing or
schema rendering don't ripple through every node module.
"""

from __future__ import annotations

import json
import re
from typing import Any

from nl_sql.agent.state import GenerateSQLOutput
from nl_sql.schema_index.retriever import ContextBundle

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.MULTILINE)


def parse_generate_sql_output(text: str) -> GenerateSQLOutput:
    """Parse the LLM's JSON response into a GenerateSQLOutput.

    Handles common deviations: markdown fences, trailing prose, single-quoted
    keys (some local models do this). Falls back to extracting the longest
    SQL substring if JSON is unrecoverable — confidence drops to 0.
    """
    raw = (text or "").strip()
    candidate = _strip_code_fence(raw)
    parsed = _safe_loads(candidate)
    if parsed is None:
        # Last-ditch: find the first {...} block anywhere in the text.
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            parsed = _safe_loads(match.group(0))

    if not isinstance(parsed, dict):
        return GenerateSQLOutput(
            sql=_strip_to_sql(raw),
            rationale="",
            tables_used=(),
            confidence=0.0,
            raw_text=raw,
        )

    sql = str(parsed.get("sql") or "").strip().rstrip(";")
    rationale = str(parsed.get("rationale") or "")
    tables = parsed.get("tables_used") or ()
    tables_used = tuple(str(t) for t in tables) if isinstance(tables, list) else ()

    confidence = _coerce_float(parsed.get("confidence"), default=0.0)
    return GenerateSQLOutput(
        sql=sql,
        rationale=rationale,
        tables_used=tables_used,
        confidence=confidence,
        raw_text=raw,
    )


def render_schema_block(context: ContextBundle | None) -> str:
    """Render schema chunks + FK neighbours into a single text block.

    Order: top-k dense hits first, FK-extended neighbours after. Empty bundle
    yields a placeholder so prompt formatting still works.
    """
    if context is None:
        return "(no schema context)"
    blocks: list[str] = []
    for hit in context.schema_hits:
        blocks.append(hit.text)
    if context.fk_neighbours:
        blocks.append("# FK-related tables")
        for hit in context.fk_neighbours:
            blocks.append(hit.text)
    if not blocks:
        return "(no tables matched)"
    return "\n\n".join(blocks)


def render_fewshot_block(context: ContextBundle | None) -> str:
    if context is None or not context.fewshots:
        return "(none)"
    lines: list[str] = []
    for ex in context.fewshots:
        lines.append(f"Q: {ex.question}")
        lines.append(f"SQL: {ex.sql}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _strip_code_fence(text: str) -> str:
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text


def _safe_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _coerce_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN guard
        return default
    return max(0.0, min(1.0, result))


def _strip_to_sql(text: str) -> str:
    """Best-effort: pull a single SELECT statement from a free-form blob.

    Used only when JSON parsing fails entirely. We never want to emit empty
    SQL — that masks a model regression as 'empty result'.
    """
    cleaned = re.sub(r"```\w*", "", text).strip("`\n ")
    match = re.search(r"(SELECT\b[\s\S]+?)(?:;|$)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned.split("\n")[0].strip()
