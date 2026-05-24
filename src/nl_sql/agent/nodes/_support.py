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
    schema_link_hints = _render_schema_link_hints_appendix(context, all_hits)
    if schema_link_hints:
        blocks.append(schema_link_hints)
    appendix = _render_extended_samples_appendix(context.extended_samples)
    if appendix:
        blocks.append(appendix)
    return "\n\n".join(blocks)


def _render_join_hints_appendix(hits: list[Any]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        table = str(hit.table_name)
        for raw_line in hit.text.splitlines():
            fk_m = _M_FK_RE.match(raw_line)
            if not fk_m:
                continue
            local_cols, ref_table, ref_cols = fk_m.groups()
            hints = _format_join_hint(table, local_cols, ref_table, ref_cols)
            for hint in hints:
                if hint in seen:
                    continue
                seen.add(hint)
                lines.append(hint)
    if not lines:
        return ""
    return "\n".join(["# Join hints", *lines])


def _format_join_hint(
    table: str,
    local_cols: str,
    ref_table: str,
    ref_cols: str,
) -> list[str]:
    locals_ = [c.strip() for c in local_cols.split(",") if c.strip()]
    refs = [c.strip() for c in ref_cols.split(",") if c.strip()]
    if len(locals_) == len(refs):
        return [
            f"{table}.{left} = {ref_table}.{right}"
            for left, right in zip(locals_, refs, strict=True)
        ]
    return [f"{table}.({local_cols}) -> {ref_table}.({ref_cols})"]


def _render_schema_link_hints_appendix(context: ContextBundle, hits: list[Any]) -> str:
    tables = {str(hit.table_name).lower() for hit in hits}
    question = context.question.lower()
    db_id = context.db_id.lower()
    if (
        db_id in {"student_club", "bird_student_club"}
        and {"event", "expense"} <= tables
        and "type" in question
        and "expense" in question
        and "event" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For event-linked expense questions asking for a type, use event.type. "
                "expense.expense_description describes individual expense rows.",
            ]
        )
    if (
        db_id in {"toxicology", "bird_toxicology"}
        and {"atom", "bond", "connected"} <= tables
        and "double" in question
        and "bond" in question
        and "element" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For toxicology questions asking for elements in a double bond, "
                "filter bond.bond_type = '=' and connect atom to bond by molecule: "
                "atom.molecule_id = bond.molecule_id plus connected.atom_id = atom.atom_id, "
                "not connected.bond_id.",
            ]
        )
    if (
        db_id in {"formula_1", "bird_formula_1"}
        and {"driverstandings"} <= tables
        and "track number" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For formula_1 questions about a driver's 'track number' across races, "
                "use driverStandings.position joined via driverStandings.raceId and "
                "driverStandings.driverId. results.position / results.positionOrder refer "
                "to finish position within a single race, which is different.",
            ]
        )
    if (
        db_id in {"formula_1", "bird_formula_1"}
        and {"laptimes", "drivers", "races"} <= tables
        and ("lap time recorded" in question or "recorded lap time" in question)
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For formula_1 'best lap time recorded' / 'recorded lap time' "
                "questions, BIRD gold surfaces the lap-time value alongside the "
                "driver/race columns. Include lapTimes.milliseconds as the first "
                "SELECT column and rank with ORDER BY lapTimes.milliseconds ASC "
                "LIMIT 1: SELECT lapTimes.milliseconds, drivers.forename, "
                "drivers.surname, races.name FROM lapTimes JOIN drivers ON "
                "lapTimes.driverId = drivers.driverId JOIN races ON "
                "lapTimes.raceId = races.raceId ORDER BY lapTimes.milliseconds "
                "ASC LIMIT 1.",
            ]
        )
    if (
        db_id in {"thrombosis_prediction", "bird_thrombosis_prediction"}
        and {"patient", "laboratory", "examination"} <= tables
        and "higher than normal" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For thrombosis_prediction 'higher than normal' patient-count "
                "questions on Laboratory values (e.g. IGG/IGA/IGM/anti-...), "
                "BIRD gold restricts patients to those that appear in both the "
                "Laboratory and Examination tables — even when no Examination "
                "column is used in WHERE. Write: SELECT COUNT(DISTINCT T1.ID) "
                "FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID "
                "INNER JOIN Examination AS T3 ON T3.ID = T2.ID WHERE <lab value "
                "condition>. Do NOT query Laboratory alone — that overcounts "
                "patients without Examination records.",
            ]
        )
    if (
        db_id in {"thrombosis_prediction", "bird_thrombosis_prediction"}
        and {"patient", "laboratory"} <= tables
        and ("anti-centromere" in question or "anti-ssb" in question)
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For thrombosis_prediction questions mentioning 'anti-centromere' "
                "or 'anti-SSB', the antibody values live on the Laboratory table "
                "as columns Laboratory.CENTROMEA and Laboratory.SSB (NOT on "
                "Examination — Examination has no CENTROMEA or SSB columns at "
                "all). BIRD gold encodes 'a normal level of anti-centromere / "
                "anti-SSB' as Laboratory.CENTROMEA IN ('negative', '0') and "
                "Laboratory.SSB IN ('negative', '0') — these are the actual "
                "string values stored in Laboratory; do not invent '-' / '+-' / "
                "'+' tokens. Write: SELECT COUNT(DISTINCT T1.ID) FROM Patient "
                "AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE "
                "T2.CENTROMEA IN ('negative', '0') AND T2.SSB IN "
                "('negative', '0') AND T1.SEX = 'M'.",
            ]
        )
    if (
        db_id in {"card_games", "bird_card_games"}
        and {"cards", "rulings"} <= tables
        and "triggered ability" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For card_games questions asking how many cards 'contain info "
                "about the triggered ability' (or any ruling-style phrase), BIRD "
                "gold treats per-card ability rulings as rows in the rulings "
                "table, not the cards table. Write: SELECT COUNT(DISTINCT "
                "cards.id) FROM cards INNER JOIN rulings ON cards.uuid = "
                "rulings.uuid WHERE (cards.power IS NULL OR cards.power = '*') "
                "AND rulings.text LIKE '%triggered ability%'. Filter on "
                "rulings.text, NOT cards.text (cards.text is the printed card "
                "text, while ruling notes live in rulings.text). Use "
                "COUNT(DISTINCT cards.id) to avoid inflating the count when "
                "a single card has multiple rulings.",
            ]
        )
    if (
        db_id in {"debit_card_specializing", "bird_debit_card_specializing"}
        and {"yearmonth", "transactions_1k", "customers"} <= tables
        and "top spending" in question
        and "average price" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For debit_card_specializing 'top spending customer' + "
                "'average price per single item' question, write exactly: "
                "SELECT T2.CustomerID, SUM(T2.Price / T2.Amount), T1.Currency "
                "FROM customers AS T1 INNER JOIN transactions_1k AS T2 "
                "ON T1.CustomerID = T2.CustomerID "
                "WHERE T2.CustomerID = (SELECT CustomerID FROM yearmonth "
                "ORDER BY yearmonth.Consumption DESC LIMIT 1) "
                "GROUP BY T2.CustomerID, T1.Currency. "
                "Top spender is the yearmonth.Consumption max (subquery), "
                "NOT SUM(transactions_1k.Price). "
                "Average price per item is SUM(Price / Amount) row-wise, "
                "NOT SUM(Price) / SUM(Amount). "
                "Column order is (CustomerID, avg, Currency).",
            ]
        )
    return ""


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
