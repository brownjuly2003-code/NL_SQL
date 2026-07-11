"""Shared helpers used by multiple nodes.

Public surface (imported by `generate_sql`, `repair_once`, `plan_query`,
`eval.runner`, `tests.test_agent_support`, `scripts.wider_sc_poc`,
`tests.agent.nodes.test_schema_link_hints`):

- `parse_generate_sql_output` — robust JSON-parsing of LLM output
- `render_m_schema` — XiYan-style compact schema rendering
- `render_schema_block` — full schema-card block with hint appendices
- `render_fewshot_block` — few-shot example rendering

Internal helpers are split into two sibling modules (Kimi audit P1.4):

- `_text_utils` — JSON-fence stripping, safe-loads, NaN-safe float coerce,
  best-effort SELECT extraction. Used only by `parse_generate_sql_output`.
- `_hints` — M-Schema regexes (`_M_COL_RE`, `_M_FK_RE`), join-hints
  appendix, schema-link hints (one if-block per landed P3.F rescue),
  extended-samples appendix. Used by `render_m_schema` and
  `render_schema_block`.

Both sibling modules import nothing from this file — no circular paths.
"""

from __future__ import annotations

import re

from nl_sql.agent.nodes._hints import (
    _M_COL_RE,
    _M_FK_RE,
    _render_extended_samples_appendix,
    _render_join_hints_appendix,
    _render_schema_link_hints_appendix,
)
from nl_sql.agent.nodes._text_utils import (
    _coerce_float,
    _safe_loads,
    _strip_code_fence,
    _strip_to_sql,
)
from nl_sql.agent.state import GenerateSQLOutput
from nl_sql.schema_index.retriever import ContextBundle


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
    enable_bird_rescue_hints: bool = False,
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
    all_hits = list(context.schema_hits) + list(context.fk_neighbours)
    if sort_alphabetically:
        all_hits.sort(key=lambda h: h.table_name.lower())
        blocks.extend(hit.text for hit in all_hits)
    else:
        blocks.extend(hit.text for hit in context.schema_hits)
        if context.fk_neighbours:
            blocks.append("# FK-related tables")
            blocks.extend(hit.text for hit in context.fk_neighbours)
    if not blocks:
        return "(no tables matched)"
    join_hints = _render_join_hints_appendix(all_hits)
    if join_hints:
        blocks.append(join_hints)
    # BIRD per-question rescue hints are eval-only (they encode gold answers for
    # specific benchmark questions). Off by default so the product path never
    # serves a canned answer — see PipelineConfig.enable_bird_rescue_hints.
    if enable_bird_rescue_hints:
        schema_link_hints = _render_schema_link_hints_appendix(context, all_hits)
        if schema_link_hints:
            blocks.append(schema_link_hints)
    appendix = _render_extended_samples_appendix(context.extended_samples)
    if appendix:
        blocks.append(appendix)
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
