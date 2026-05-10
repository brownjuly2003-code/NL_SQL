"""Node: combine retrieve_schema + retrieve_examples into one ContextBundle.

Thin wrapper over `nl_sql.schema_index.retrieve_context`. Per arch v2 §3,
this node also owns dialect-adapter hints (Postgres vs SQLite). For v1 we
just pass dialect through state — the prompt assembler picks dialect-specific
phrasing once we observe model failure modes during eval.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.engine import Engine

from nl_sql.agent.state import PipelineState
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.retriever import retrieve_context


def make_context_builder_node(
    index: SchemaIndex,
    *,
    schema_top_k: int = 5,
    fewshot_top_k: int = 3,
    fk_hops: int = 1,
    table_budget: int = 12,
    registry: DatabaseRegistry | None = None,
    primary_sample_size: int = 3,
    extended_sample_size: int = 0,
) -> Callable[[PipelineState], PipelineState]:
    """Construct the context-builder node.

    Sample mixture wiring: when `registry` is provided AND
    `extended_sample_size > primary_sample_size`, the node opens the
    db's read-only engine for the current question and asks
    `retrieve_context` to attach an "extended samples" appendix to the
    bundle. `render_schema_block` then formats it as a supplementary
    block. No-op when either flag is missing — the production default.
    """

    mixture_enabled = registry is not None and extended_sample_size > primary_sample_size

    def node(state: PipelineState) -> PipelineState:
        question = state.get("question", "")
        db_id = state.get("db_id", "")
        if not question or not db_id:
            return {
                "context": None,
                "trace": _append_trace(state, "context_builder", note="missing question or db_id"),
            }
        engine: Engine | None = None
        if mixture_enabled:
            assert registry is not None
            engine = registry.get(db_id).make_engine()
        try:
            bundle = retrieve_context(
                index,
                question,
                db_id=db_id,
                schema_top_k=schema_top_k,
                fewshot_top_k=fewshot_top_k,
                fk_hops=fk_hops,
                table_budget=table_budget,
                engine=engine,
                primary_sample_size=primary_sample_size,
                extended_sample_size=extended_sample_size,
            )
        finally:
            if engine is not None:
                engine.dispose()
        return {
            "context": bundle,
            "trace": _append_trace(
                state,
                "context_builder",
                tables=bundle.all_tables,
                fewshots=len(bundle.fewshots),
                truncated=bundle.truncated,
                extended_sample_tables=(
                    sorted(bundle.extended_samples) if bundle.extended_samples else []
                ),
            ),
        }

    return node


def _append_trace(state: PipelineState, node: str, **details: object) -> list[dict[str, object]]:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, **details})
    return trace
