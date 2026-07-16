"""DAIL-style few-shot selection helpers (phase A2).

Default product path embeds the *raw* question against the ``fewshot_qsql``
collection (dense top-k). DAIL-SQL (arXiv:2308.15363) and the MCS-SQL
ablation instead embed a *schema-masked* question so retrieval prefers
intent/structure over shared table/column names.

This module implements the cheap **2a** variant only: mask schema tokens
in the query text before embedding. Skeleton re-ranking (2b) is deferred
until 2a shows ≥ +1.0 pp on n=200.

Default OFF — wired only when ``PipelineConfig.fewshot_selection == "dail"``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl_sql.schema_index.indexer import SchemaIndex

MASK_TOKEN = "<mask>"
_MIN_TOKEN_LEN = 2

# Column line in chunker-rendered table cards:
#   "  - District Name: TEXT [NULL] | nulls=0 ..."
_COLUMN_LINE = re.compile(r"^\s+-\s+([^:]+):\s+\S+", re.MULTILINE)

# Ultra-generic identifiers that are also ordinary English; masking them
# shreds the question into noise. Table names are never filtered this way.
_GENERIC_IDENTIFIERS = frozenset(
    {
        "id",
        "name",
        "type",
        "date",
        "time",
        "year",
        "month",
        "day",
        "code",
        "key",
        "value",
        "text",
        "data",
        "info",
        "number",
        "count",
        "total",
        "status",
        "level",
        "order",
        "group",
        "user",
        "index",
        "rank",
        "score",
        "rate",
        "flag",
        "mode",
        "kind",
        "class",
        "size",
        "start",
        "end",
        "first",
        "last",
        "min",
        "max",
        "avg",
        "sum",
        "desc",
        "description",
        "comment",
        "note",
        "notes",
        "title",
        "label",
        "amount",
        "price",
        "cost",
        "qty",
        "quantity",
        "age",
        "sex",
        "gender",
        "city",
        "state",
        "country",
        "address",
        "phone",
        "email",
        "url",
        "path",
        "file",
    }
)


def parse_column_names_from_chunk(text: str) -> set[str]:
    """Extract column identifiers from a chunker-rendered table card."""
    names: set[str] = set()
    for match in _COLUMN_LINE.finditer(text or ""):
        raw = match.group(1).strip()
        if raw:
            names.add(raw)
    return names


def collect_schema_tokens(index: SchemaIndex, db_id: str) -> frozenset[str]:
    """Table + column names for ``db_id`` from the indexed schema cards.

    Used only as a query-time mask source — does not rebuild embeddings.
    """
    if not db_id:
        return frozenset()
    records = index.schema_collection.get(
        where={"db_id": db_id},
        include=["documents", "metadatas"],
    )
    tokens: set[str] = set()
    for meta in records.get("metadatas") or []:
        if not meta:
            continue
        table = str(meta.get("table_name") or "").strip()
        if table:
            tokens.add(table)
    for doc in records.get("documents") or []:
        tokens.update(parse_column_names_from_chunk(str(doc or "")))
    return frozenset(t.strip() for t in tokens if _keep_token(t))


def _keep_token(token: str) -> bool:
    t = token.strip()
    if len(t) < _MIN_TOKEN_LEN:
        return False
    # Pure digits / single symbols are never useful schema anchors.
    if t.isdigit():
        return False
    folded = t.casefold()
    if folded in _GENERIC_IDENTIFIERS:
        return False
    # Multi-word / underscored names always keep (e.g. "District Name").
    if " " in t or "_" in t:
        return True
    return True


def _expand_variants(token: str) -> list[str]:
    """Surface space/underscore variants so NL phrasing still masks."""
    base = token.strip()
    if not base:
        return []
    variants = {base, base.replace("_", " "), base.replace(" ", "_")}
    # Prefer longest first so "District Name" wins over "District".
    return sorted(variants, key=len, reverse=True)


def mask_schema_tokens(
    question: str,
    tokens: Iterable[str],
    *,
    mask: str = MASK_TOKEN,
) -> str:
    """Replace whole-token schema identifiers in ``question`` with ``mask``.

    Matching is case-insensitive. Longer tokens are applied first so multi-word
    column names are not partially eaten by a shorter component. Tokens that
    never appear leave the question unchanged (cheap no-op path).
    """
    if not question or not tokens:
        return question

    # Dedup expanded variants, longest first.
    seen: set[str] = set()
    ordered: list[str] = []
    for tok in tokens:
        for variant in _expand_variants(str(tok)):
            key = variant.casefold()
            if key in seen or not _keep_token(variant):
                continue
            # Re-check generic on the variant itself.
            if (
                variant.casefold() in _GENERIC_IDENTIFIERS
                and " " not in variant
                and "_" not in variant
            ):
                continue
            seen.add(key)
            ordered.append(variant)
    ordered.sort(key=len, reverse=True)

    result = question
    for tok in ordered:
        escaped = re.escape(tok)
        # Word-ish boundaries: not alphanumeric on either side. Works for
        # "Album", "District Name", and "frpm" without eating "frpm_table".
        pattern = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
        result = pattern.sub(mask, result)
    # Collapse accidental double masks from overlapping replacements.
    return re.sub(rf"(?:{re.escape(mask)}\s*){{2,}}", f"{mask} ", result)


def fewshot_query_text(
    question: str,
    *,
    selection: str,
    schema_tokens: Iterable[str],
) -> str:
    """Return the text that should be embedded for few-shot retrieval."""
    mode = (selection or "dense").strip().lower()
    if mode == "dail":
        return mask_schema_tokens(question, schema_tokens)
    return question
