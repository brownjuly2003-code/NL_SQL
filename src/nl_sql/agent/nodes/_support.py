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


_M_COL_RE = re.compile(
    r"  - (?P<col>[^:]+?):\s+(?P<type>[A-Za-z][A-Za-z0-9_()]*)\s+\[(?P<flags>[^\]]*)\]"
    r"(?:\s*\|\s*nulls=\d+(?:\s*\([^)]+\))?,\s*distinct=\d+)?"
    r"(?:\s*\|\s*samples:\s*(?P<samples>.+))?$"
)
_M_FK_RE = re.compile(r"  - \(([^)]+)\) -> (\S+?)\(([^)]+)\)")


def render_m_schema(context: ContextBundle | None) -> str:
    """Compact M-Schema rendering (XiYan-SQL style) parsed from chunk text.

    Replaces verbose table-card dump with: ``table.column (type) [samples]``
    per line plus a trailing FK block. Reduces tokens by ~60% and surfaces
    FK pairs as first-class signal next to columns instead of buried inside
    multi-section cards.
    """
    if context is None:
        return "(no schema context)"
    all_hits = list(context.schema_hits) + list(context.fk_neighbours)
    all_hits.sort(key=lambda h: h.table_name.lower())
    if not all_hits:
        return "(no tables matched)"
    col_lines: list[str] = []
    fk_lines: list[str] = []
    for hit in all_hits:
        table = hit.table_name
        for raw_line in hit.text.splitlines():
            m = _M_COL_RE.match(raw_line)
            if m:
                col = m.group("col").strip()
                col_type = m.group("type")
                flags = (m.group("flags") or "").strip()
                samples = (m.group("samples") or "").strip()
                pk = "PK" in flags.split()
                parts = [f"{table}.{col} ({col_type})"]
                if pk:
                    parts.append("[PK]")
                if samples:
                    parts.append(f"[{samples}]")
                col_lines.append(" ".join(parts))
                continue
            fk_m = _M_FK_RE.match(raw_line)
            if fk_m:
                local_cols, ref_table, ref_cols = fk_m.groups()
                fk_lines.append(f"{table}.({local_cols}) -> {ref_table}.({ref_cols})")
    blocks: list[str] = ["# Columns", *col_lines] if col_lines else ["(no columns parsed)"]
    if fk_lines:
        blocks.append("\n# Foreign keys")
        blocks.extend(fk_lines)
    appendix = _render_extended_samples_appendix(context.extended_samples)
    if appendix:
        blocks.append(appendix)
    return "\n".join(blocks)


def render_schema_block(
    context: ContextBundle | None,
    *,
    sort_alphabetically: bool = False,
) -> str:
    """Render schema chunks + FK neighbours into a single text block.

    Order: top-k dense hits first, FK-extended neighbours after. Empty bundle
    yields a placeholder so prompt formatting still works.

    `sort_alphabetically=True` overrides retrieval order and renders all
    tables (dense hits + FK neighbours together) in alphabetical-by-table-name
    order. The "FK-related tables" header is omitted in this mode because
    the partition no longer exists. Empirically codestral is more accurate
    when the schema block matches the alphabetical baseline order produced
    by SQLAlchemy's `inspect()` — see docs/SESSION_HANDOFF.md (column-
    ordering experiment).
    """
    if context is None:
        return "(no schema context)"
    blocks: list[str] = []
    if sort_alphabetically:
        all_hits = list(context.schema_hits) + list(context.fk_neighbours)
        all_hits.sort(key=lambda h: h.table_name.lower())
        blocks.extend(hit.text for hit in all_hits)
    else:
        blocks.extend(hit.text for hit in context.schema_hits)
        if context.fk_neighbours:
            blocks.append("# FK-related tables")
            blocks.extend(hit.text for hit in context.fk_neighbours)
    if not blocks:
        return "(no tables matched)"
    appendix = _render_extended_samples_appendix(context.extended_samples)
    if appendix:
        blocks.append(appendix)
    return "\n\n".join(blocks)


def _render_extended_samples_appendix(
    extended_samples: dict[str, dict[str, tuple[Any, ...]]] | None,
) -> str:
    """Format the per-difficulty sample mixture appendix.

    Listed values are the *tail* of top-k samples per column — i.e.
    samples beyond the primary ones already shown in each table card.
    Header is explicit so codestral treats this as supplementary
    filter-value hints, not as part of the schema definition.
    """
    if not extended_samples:
        return ""
    lines = [
        "# Additional sample values (extended density, for filter-value discovery)",
    ]
    for table in sorted(extended_samples):
        cols = extended_samples[table]
        if not cols:
            continue
        lines.append(f"Table: {table}")
        for col in sorted(cols):
            values = cols[col]
            if not values:
                continue
            rendered = ", ".join(_format_sample(v) for v in values)
            lines.append(f"  - {col}: {rendered}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _format_sample(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return repr(value)
    return str(value)


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
