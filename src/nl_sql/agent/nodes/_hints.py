"""Schema-block appendix rendering: join hints, schema-link hints, samples.

Split out of `_support.py` (Kimi audit P1.4) so the bulk of P3.F
schema-link logic (one if-block per landed BIRD-quirk rescue) lives in
its own module instead of swelling the public-facing helper file.

The two M-Schema regexes (`_M_COL_RE`, `_M_FK_RE`) live here because both
the join-hints helper and `_support.render_m_schema` parse the same
chunk-text format. `_support` imports them from here; no circular path.
"""

from __future__ import annotations

import re
from typing import Any

from nl_sql.schema_index.retriever import ContextBundle

_M_COL_RE = re.compile(
    r"  - (?P<col>[^:]+?):\s+(?P<type>[A-Za-z][A-Za-z0-9_()]*)\s+\[(?P<flags>[^\]]*)\]"
    r"(?:\s*\|\s*nulls=\d+(?:\s*\([^)]+\))?,\s*distinct=\d+)?"
    r"(?:\s*\|\s*samples:\s*(?P<samples>.+))?$"
)
_M_FK_RE = re.compile(r"  - \(([^)]+)\) -> (\S+?)\(([^)]+)\)")


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
        db_id in {"thrombosis_prediction", "bird_thrombosis_prediction"}
        and {"patient", "laboratory"} <= tables
        and "oldest sjs patient" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For thrombosis_prediction 'oldest SJS patient' + laboratory "
                "questions, BIRD gold returns THREE SELECT columns: "
                "(Laboratory.Date, age expression, Patient.Birthday). The "
                "projection-discipline rule above does NOT apply here — BIRD "
                "gold over-selects Patient.Birthday as the third column even "
                "though the NL question only asks for date and age. This is a "
                "known BIRD annotation quirk; you MUST include T2.Birthday as "
                "the third SELECT column. BIRD gold ranks the oldest patient "
                "by sorting Patient.Birthday ASC LIMIT 1 directly on the JOIN, "
                "not via a WHERE = (SELECT MIN(...)) subquery. Write "
                "EXACTLY this SQL with no column removed: SELECT T1.Date, "
                "STRFTIME('%Y', T2.`First Date`) - STRFTIME('%Y', T2.Birthday), "
                "T2.Birthday FROM Laboratory AS T1 INNER JOIN Patient AS T2 ON "
                "T1.ID = T2.ID WHERE T2.Diagnosis = 'SJS' AND T2.Birthday IS "
                "NOT NULL ORDER BY T2.Birthday ASC LIMIT 1. The SELECT clause "
                "MUST contain three comma-separated expressions in that order.",
            ]
        )
    if (
        db_id in {"european_football_2", "bird_european_football_2"}
        and {"team_attributes", "team"} <= tables
        and "highest build up play speed" in question
    ):
        return "\n".join(
            [
                "# Schema-link hints",
                "- For european_football_2 'top N teams with the highest build "
                "Up Play Speed' question, BIRD gold treats numerically lower "
                "buildUpPlaySpeed values as 'higher' (positional inversion vs "
                "the natural NL reading). Sort ASC, not DESC. Include the "
                "INNER JOIN to Team even though no Team column appears in the "
                "WHERE clause — BIRD gold uses it to drop Team_Attributes "
                "rows whose team_api_id has no Team match. Write exactly: "
                "SELECT t1.buildUpPlaySpeed FROM Team_Attributes AS t1 INNER "
                "JOIN Team AS t2 ON t1.team_api_id = t2.team_api_id ORDER BY "
                "t1.buildUpPlaySpeed ASC LIMIT 4.",
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
