"""Question-driven value retrieval (CHESS-style).

For a natural-language question, scan text-like columns of the tables already
selected for the prompt and surface real cell values that match tokens or
quoted phrases from the question. The matches are short grounding lines the
generator can copy into filters (``WHERE col = 'exact literal'``).

Default off — wired only when ``PipelineConfig.enable_value_retrieval`` is set.
No Chroma rebuild; uses a live read-only engine over the same tables the
schema RAG already chose.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import MetaData, Table, cast, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.types import String

# Tokens shorter than this rarely disambiguate a cell value and flood the
# match list with noise ("the", "and", "id", "avg").
_MIN_TOKEN_LEN = 3
_MAX_MATCHES = 8
_MAX_HITS_PER_PHRASE_COL = 3
_MAX_VALUE_CHARS = 80

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "from",
        "by",
        "with",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "these",
        "those",
        "which",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "how",
        "many",
        "much",
        "more",
        "most",
        "than",
        "then",
        "each",
        "all",
        "any",
        "both",
        "few",
        "other",
        "some",
        "such",
        "no",
        "not",
        "only",
        "own",
        "same",
        "so",
        "too",
        "very",
        "can",
        "will",
        "just",
        "should",
        "now",
        "list",
        "show",
        "give",
        "find",
        "tell",
        "name",
        "names",
        "number",
        "count",
        "total",
        "average",
        "avg",
        "sum",
        "max",
        "min",
        "percentage",
        "percent",
        "ratio",
        "rate",
        "per",
        "between",
        "over",
        "under",
        "above",
        "below",
        "after",
        "before",
        "during",
        "hint",
        "please",
        "return",
        "select",
        "table",
        "column",
        "value",
        "values",
        "null",
        "true",
        "false",
        "yes",
        "did",
        "does",
        "do",
        "has",
        "have",
        "had",
        "their",
        "there",
        "its",
        "his",
        "her",
        "our",
        "your",
        "they",
        "them",
        "she",
        "he",
        "it",
        "we",
        "you",
        "i",
    }
)

# Columns whose type string looks non-textual — skip (ids, floats, blobs).
_NON_TEXT_TYPE_RE = re.compile(
    r"\b(int|integer|bigint|smallint|tinyint|float|real|double|decimal|numeric|"
    r"bool|boolean|blob|binary|bytea|date|time|timestamp|datetime|year)\b",
    re.IGNORECASE,
)

_QUOTED_RE = re.compile(r"[\"']([^\"']{2,80})[\"']")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./+\-]{1,79}")


@dataclass(frozen=True, slots=True)
class ValueMatch:
    """One grounded cell value tied to a table.column."""

    value: str
    table: str
    column: str
    score: float


def extract_query_phrases(question: str) -> list[str]:
    """Pull candidate literals from the question (quoted first, then tokens).

    Order matters: longer / quoted phrases are preferred by the matcher so a
    district name wins over its first word alone.
    """
    # Drop the structural "Hint:" label but keep its content — BIRD evidence
    # often carries the exact filter value the gold uses.
    text = question.replace("Hint:", " ")
    seen: set[str] = set()
    out: list[str] = []

    def _add(phrase: str) -> None:
        cleaned = phrase.strip()
        if len(cleaned) < _MIN_TOKEN_LEN:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        if key in _STOPWORDS:
            return
        seen.add(key)
        out.append(cleaned)

    for m in _QUOTED_RE.finditer(text):
        _add(m.group(1))

    # Multi-word proper-ish phrases: "Riverside Unified", "Marvel Comics".
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,4})\b", text):
        _add(m.group(1))

    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        if tok.casefold() in _STOPWORDS:
            continue
        if tok.isdigit() and len(tok) < 4:
            # Year-like 4-digit kept; 1-2 digit noise dropped.
            continue
        _add(tok)

    # Longest first — the scorer prefers exact equality, but when ranking
    # substring hits a longer phrase is almost always the intended literal.
    out.sort(key=lambda s: (-len(s), s.casefold()))
    return out


def retrieve_value_matches(
    engine: Engine,
    question: str,
    table_names: list[str],
    *,
    max_matches: int = _MAX_MATCHES,
    max_value_chars: int = _MAX_VALUE_CHARS,
) -> list[ValueMatch]:
    """Return up to ``max_matches`` cell-value groundings for ``question``.

    For each phrase x text-like column of the schema-RAG tables, run a bounded
    ``LIKE`` probe (CHESS-style) rather than a blind top-N distinct dump —
    district names buried past the 400th distinct value would otherwise be
    invisible. Failures on a single column are skipped.
    """
    phrases = extract_query_phrases(question)
    if not phrases or not table_names:
        return []

    # Cap phrase count so a long evidence line does not explode into O(N*M) probes.
    phrases = phrases[:12]

    insp = inspect(engine)
    available = set(insp.get_table_names())
    metadata = MetaData()
    candidates: list[ValueMatch] = []

    with engine.connect() as conn:
        for tname in table_names:
            if tname not in available:
                continue
            try:
                sa_table = Table(tname, metadata, autoload_with=engine)
            except SQLAlchemyError:
                continue
            for col_meta in insp.get_columns(tname):
                col_name = str(col_meta["name"])
                col_type = str(col_meta.get("type") or "")
                if not _is_textish(col_type, col_name):
                    continue
                sa_col = sa_table.c[col_name]
                for phrase in phrases:
                    for value in _lookup_phrase(
                        conn,
                        sa_table,
                        sa_col,
                        phrase,
                        limit=_MAX_HITS_PER_PHRASE_COL,
                        max_chars=max_value_chars,
                    ):
                        score = _best_score(value, [phrase])
                        if score <= 0:
                            continue
                        candidates.append(
                            ValueMatch(value=value, table=tname, column=col_name, score=score)
                        )

    if not candidates:
        return []

    # Prefer higher score, then longer value (more specific), stable by table.col.
    candidates.sort(key=lambda m: (-m.score, -len(m.value), m.table, m.column, m.value))
    # Once we have an exact hit, drop weak substring noise — exact grounding
    # is the whole point; a flood of near-misses confuses the generator.
    if any(m.score >= 1.0 for m in candidates):
        candidates = [m for m in candidates if m.score >= 0.9]

    # If "Riverside Unified" matched exactly, drop bare "Riverside" exacts —
    # they are almost always a city/county red herring next to the district.
    exact_values = {m.value.casefold() for m in candidates if m.score >= 1.0}
    if exact_values:
        dominated = {
            short
            for short in exact_values
            for long in exact_values
            if short != long and short in long and len(short) < len(long)
        }
        if dominated:
            candidates = [
                m for m in candidates if not (m.score >= 1.0 and m.value.casefold() in dominated)
            ]

    # De-dupe by (value, table, column) keeping the best score (already sorted).
    seen_keys: set[tuple[str, str, str]] = set()
    # Also de-dupe by value alone when the same literal lands in many columns —
    # keep the first (highest score) so the prompt stays short. Exact hits may
    # still list two columns (City vs District Name) because both are useful.
    seen_values: set[str] = set()
    picked: list[ValueMatch] = []
    for match in candidates:
        key = (match.value.casefold(), match.table, match.column)
        if key in seen_keys:
            continue
        if match.value.casefold() in seen_values and match.score < 1.0:
            continue
        seen_keys.add(key)
        seen_values.add(match.value.casefold())
        picked.append(match)
        if len(picked) >= max_matches:
            break
    return picked


def format_value_grounding(matches: list[ValueMatch]) -> str:
    """Render matches as a short prompt block. Empty string if none."""
    if not matches:
        return ""
    lines = [
        "Value grounding (real DB cell values that match tokens in the question). "
        "Copy literals exactly when filtering:",
    ]
    for m in matches:
        lines.append(f"- value {m.value!r} appears in {m.table}.{m.column}")
    return "\n".join(lines)


def _is_textish(col_type: str, col_name: str) -> bool:
    """Heuristic: keep string-ish columns, drop obvious numeric/id/date types."""
    if _NON_TEXT_TYPE_RE.search(col_type):
        # NVARCHAR / VARCHAR contain "char" not matched above; pure INTEGER etc. drop.
        return bool(re.search(r"char|text|clob|string", col_type, re.IGNORECASE))
    # Name-based drop for bare untyped sqlite ids that slipped through.
    return not bool(re.fullmatch(r"(?i).*(?:_id|id|_pk|pk)$", col_name))


def _lookup_phrase(
    conn: Any,
    sa_table: Table,
    sa_col: Any,
    phrase: str,
    *,
    limit: int,
    max_chars: int,
) -> list[str]:
    """Return up to ``limit`` distinct cell values containing ``phrase``.

    Prefer exact equality first, then a LIKE fallback for partials. Escape
    LIKE metacharacters so user tokens are literal.
    """
    needle = phrase.strip()
    if len(needle) < _MIN_TOKEN_LEN:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _consume(rows: Any) -> None:
        for (raw,) in rows:
            if raw is None or isinstance(raw, (bytes, bytearray, memoryview)):
                continue
            text = str(raw).strip()
            if not text:
                continue
            if len(text) > max_chars:
                text = text[: max_chars - 1] + "…"
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)

    try:
        _consume(
            conn.execute(
                select(sa_col)
                .where(sa_col.is_not(None))
                .where(cast(sa_col, String) == needle)
                .limit(limit)
            ).all()
        )
    except SQLAlchemyError:
        return []

    if len(out) >= limit:
        return out

    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with contextlib.suppress(SQLAlchemyError):
        _consume(
            conn.execute(
                select(sa_col)
                .where(sa_col.is_not(None))
                .where(cast(sa_col, String).like(pattern, escape="\\"))
                .limit(limit)
            ).all()
        )
    return out[:limit]


def _best_score(value: str, phrases: list[str]) -> float:
    """Score a cell value against extracted phrases. 0 = no match.

    Exact case-insensitive equality scores 1.0. Substring hits must cover
    most of the shorter side so a shared tail like "Unified" does not
    promote every '* Unified' district when the question named one.
    """
    v = value.casefold()
    best = 0.0
    for phrase in phrases:
        p = phrase.casefold()
        if v == p:
            return 1.0
        if " " in p:
            # Multi-word phrase: only accept if the full phrase sits inside
            # the cell (or the cell sits inside the phrase). A single shared
            # word is never enough.
            if p in v:
                score = 0.9 + 0.09 * (len(p) / max(len(v), 1))
            elif v in p and len(v) >= 6:
                score = 0.75
            else:
                continue
        elif p in v or v in p:
            shorter = min(len(v), len(p))
            longer = max(len(v), len(p))
            if shorter < 4:
                continue
            ratio = shorter / longer
            # Require the shorter side to cover most of the longer one —
            # "Riverside" vs "Riverside Unified" is ok (9/17≈0.53, borderline);
            # "Unified" vs "ABC Unified" (7/11≈0.64) still too generic as a
            # lone token, so demand ratio ≥ 0.7 OR whole-word equality-ish.
            if ratio < 0.7 and shorter < 8:
                continue
            if ratio < 0.45:
                continue
            score = 0.55 + 0.4 * ratio
        else:
            continue
        if score > best:
            best = score
    return best
