"""Build a `ContextBundle` for the LangGraph context_builder node.

Pipeline (per docs/02_architecture_v2.md §3 + §4):
1. Dense retrieve top-k schema chunks for `db_id` (Mistral embeddings).
2. FK-graph traversal up to `fk_hops` to add neighbour tables, capped by
   `table_budget`.
3. Dense retrieve top-k few-shot Q→SQL pairs for the same db_id.

Returns flat structures the prompt assembler can render directly. No prompt
text is built here — that lives in `agent/prompts/` once stage 4 lands.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy.engine import Engine

from nl_sql.schema_index.indexer import FewShotHit, SchemaIndex, SchemaQueryHit
from nl_sql.schema_index.introspector import fetch_extended_samples


@dataclass(frozen=True, slots=True)
class ContextBundle:
    db_id: str
    question: str
    schema_hits: list[SchemaQueryHit]
    fk_neighbours: list[SchemaQueryHit]
    fewshots: list[FewShotHit]
    truncated: bool = False
    notes: list[str] = field(default_factory=list)
    extended_samples: dict[str, dict[str, tuple[Any, ...]]] | None = None
    """Per-difficulty sample mixture. Maps `table_name → col_name → tail
    sample values` (i.e. samples 4..N when chunks were built at
    sample_size=3). Set by `retrieve_context` when called with both
    `engine` and `extended_sample_size > primary_sample_size`. Rendered
    as an "additional sample values" appendix by `render_schema_block`.
    """

    @property
    def all_tables(self) -> list[str]:
        seen: list[str] = []
        for hit in (*self.schema_hits, *self.fk_neighbours):
            if hit.table_name and hit.table_name not in seen:
                seen.append(hit.table_name)
        return seen


def retrieve_context(
    index: SchemaIndex,
    question: str,
    *,
    db_id: str,
    schema_top_k: int = 5,
    fewshot_top_k: int = 3,
    fk_hops: int = 1,
    table_budget: int = 12,
    engine: Engine | None = None,
    primary_sample_size: int = 3,
    extended_sample_size: int = 0,
) -> ContextBundle:
    """One call → schema cards + FK neighbours + fewshots, db_id-scoped.

    `fk_hops` of 1 (default) adds direct neighbours of every retrieved table;
    2 adds neighbours-of-neighbours, etc. `table_budget` caps the total table
    count (top-k hits + neighbours together) so the downstream prompt stays
    within the context window.

    Sample mixture (optional): when `engine` is provided and
    `extended_sample_size > primary_sample_size`, the bundle's
    `extended_samples` field is populated with the tail (rows
    primary..extended) of each retrieved table's column samples. Wired
    by `make_context_builder_node` via the registry's read-only engine.
    """
    schema_hits = (
        index.query_schema(question, db_id=db_id, top_k=schema_top_k) if schema_top_k > 0 else []
    )
    fewshots = (
        index.query_fewshots(question, db_id=db_id, top_k=fewshot_top_k)
        if fewshot_top_k > 0
        else []
    )

    notes: list[str] = []
    if not schema_hits:
        notes.append(f"no schema chunks indexed for db_id={db_id!r}")

    seed_tables = [h.table_name for h in schema_hits if h.table_name]
    fk_extra: list[SchemaQueryHit] = []
    truncated = False

    if seed_tables and fk_hops > 0:
        graph = index.fk_graph(db_id)
        seen = set(seed_tables)
        frontier: deque[tuple[str, int]] = deque((t, 0) for t in seed_tables)
        neighbour_order: list[str] = []
        while frontier:
            table, depth = frontier.popleft()
            if depth >= fk_hops:
                continue
            for nb in sorted(graph.get(table, ())):
                if nb in seen:
                    continue
                seen.add(nb)
                neighbour_order.append(nb)
                frontier.append((nb, depth + 1))

        # Total budget = seed tables already in schema_hits, plus neighbours.
        slots_left = max(0, table_budget - len(seed_tables))
        chosen_neighbours = neighbour_order[:slots_left]
        if len(neighbour_order) > slots_left:
            truncated = True
            notes.append(
                f"FK traversal yielded {len(neighbour_order)} neighbours, "
                f"capped to {slots_left} by table_budget={table_budget}"
            )

        if chosen_neighbours:
            fk_extra = _materialise_neighbours(index, db_id=db_id, names=chosen_neighbours)

    extended_samples: dict[str, dict[str, tuple[Any, ...]]] | None = None
    if engine is not None and extended_sample_size > primary_sample_size:
        all_tables = list(seed_tables)
        for hit in fk_extra:
            if hit.table_name and hit.table_name not in all_tables:
                all_tables.append(hit.table_name)
        if all_tables:
            extended_samples = fetch_extended_samples(
                engine,
                all_tables,
                primary_size=primary_sample_size,
                extended_size=extended_sample_size,
            )

    return ContextBundle(
        db_id=db_id,
        question=question,
        schema_hits=schema_hits,
        fk_neighbours=fk_extra,
        fewshots=fewshots,
        truncated=truncated,
        notes=notes,
        extended_samples=extended_samples,
    )


def _materialise_neighbours(
    index: SchemaIndex,
    *,
    db_id: str,
    names: list[str],
) -> list[SchemaQueryHit]:
    """Pull schema chunks for FK-graph neighbours by exact table_name match.

    Distance is set to ``inf`` to mark these as graph-derived (not dense
    retrieval). Order matches `names` (caller already prioritised).
    """
    if not names:
        return []
    where_clause = cast(
        Any,
        {"$and": [{"db_id": db_id}, {"table_name": {"$in": names}}]},
    )
    records = index.schema_collection.get(
        where=where_clause,
        include=["documents", "metadatas"],
    )
    ids = records.get("ids") or []
    docs = records.get("documents") or []
    metas = records.get("metadatas") or []

    by_name: dict[str, SchemaQueryHit] = {}
    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) and metas[i] else {}
        doc = docs[i] if i < len(docs) else ""
        table_name = str(meta.get("table_name") or "")
        if not table_name:
            continue
        by_name[table_name] = SchemaQueryHit(
            chunk_id=str(_id),
            table_name=table_name,
            db_id=str(meta.get("db_id") or ""),
            text=str(doc),
            distance=float("inf"),
            metadata=dict(meta),
        )
    return [by_name[n] for n in names if n in by_name]
