"""Schema Recall@k — secondary metric per docs/03_eval_methodology.md §1.2.

For each example we know which tables the gold SQL touches (`gold_tables`).
After retrieval we know which tables the context_builder shortlisted
(`retrieved_tables`). Recall@k is the share of examples where every gold
table is present in the top-k retrieval set.

Why "all-or-nothing" rather than per-table fraction: a SQL referencing 3
tables is broken if any one is missing — the LLM cannot recover.
"""

from __future__ import annotations

from collections.abc import Sequence


def schema_recall_at_k(
    gold_tables: Sequence[str],
    retrieved_tables: Sequence[str],
    *,
    case_insensitive: bool = True,
) -> bool:
    """True iff every `gold_table` appears in `retrieved_tables`.

    SQLite identifiers are case-insensitive; BIRD gold + introspector both
    preserve original case but the comparison should be case-insensitive
    by default. Pass `case_insensitive=False` to enforce exact match.
    """
    if not gold_tables:
        return True
    if case_insensitive:
        retrieved = {t.lower() for t in retrieved_tables}
        return all(g.lower() in retrieved for g in gold_tables)
    retrieved_set = set(retrieved_tables)
    return all(g in retrieved_set for g in gold_tables)
