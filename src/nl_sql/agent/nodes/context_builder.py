"""Node: combine retrieve_schema + retrieve_examples into one ContextBundle.

Thin wrapper over `nl_sql.schema_index.retrieve_context`. Per arch v2 §3,
this node also owns dialect-adapter hints (Postgres vs SQLite). For v1 we
just pass dialect through state — the prompt assembler picks dialect-specific
phrasing once we observe model failure modes during eval.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from sqlalchemy.engine import Engine

from nl_sql.agent.nodes._support import render_schema_block
from nl_sql.agent.nodes.fewshot_synthesis import synthesize_fewshots
from nl_sql.agent.nodes.question_enrichment import enrich_question
from nl_sql.agent.state import PipelineState
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.llm.providers.base import LLMProvider
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
    cross_db_fewshot: bool = False,
    enable_value_retrieval: bool = False,
    fewshot_selection: str = "dense",
    fewshot_synthesis_provider: LLMProvider | None = None,
    enrichment_provider: LLMProvider | None = None,
) -> Callable[[PipelineState], PipelineState]:
    """Construct the context-builder node.

    Sample mixture wiring: when `registry` is provided AND
    `extended_sample_size > primary_sample_size`, the node opens the
    db's read-only engine for the current question and asks
    `retrieve_context` to attach an "extended samples" appendix to the
    bundle. `render_schema_block` then formats it as a supplementary
    block. No-op when either flag is missing — the production default.

    Value retrieval (CHESS-style): when `registry` is provided AND
    `enable_value_retrieval` is True, the same engine scan grounds
    question tokens against real cell values of the retrieved tables.

    `fewshot_selection`: ``"dense"`` (default), ``"dail"`` (schema-masked
    query embedding for few-shot retrieval) or ``"synthetic"`` (phase A3:
    one extra LLM call on `fewshot_synthesis_provider` writes fresh Q→SQL
    pairs against the target schema, replacing the retrieved shots; on any
    synthesis failure the retrieved shots stay, with a trace note).

    `enrichment_provider` (phase A4, E-SQL): when set, one extra LLM call
    rewrites the question into an explicit restatement (schema names,
    conditions, steps), stored as ``state["enriched_question"]``. On any
    failure the field stays empty and the trace carries a note — the
    pipeline never depends on enrichment succeeding.
    """

    mixture_enabled = registry is not None and extended_sample_size > primary_sample_size
    needs_engine = mixture_enabled or (registry is not None and enable_value_retrieval)

    def node(state: PipelineState) -> PipelineState:
        question = state.get("question", "")
        db_id = state.get("db_id", "")
        if not question or not db_id:
            return {
                "context": None,
                "trace": _append_trace(state, "context_builder", note="missing question or db_id"),
            }
        engine: Engine | None = None
        if needs_engine:
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
                cross_db_fewshot=cross_db_fewshot,
                enable_value_retrieval=enable_value_retrieval,
                fewshot_selection=fewshot_selection,
            )
        finally:
            if engine is not None:
                engine.dispose()
        synthesis_note = ""
        selection_mode = (fewshot_selection or "dense").strip().lower()
        if selection_mode == "synthetic" and fewshot_synthesis_provider is not None:
            try:
                synthetic = synthesize_fewshots(
                    fewshot_synthesis_provider,
                    question=question,
                    db_id=db_id,
                    dialect=state.get("dialect", "sqlite"),
                    schema_text=render_schema_block(bundle),
                )
            except Exception as exc:  # keep retrieved shots on any synthesis failure
                synthetic = []
                synthesis_note = f"fewshot_synthesis failed: {type(exc).__name__}: {exc}"
            if synthetic:
                bundle = replace(
                    bundle,
                    fewshots=synthetic,
                    notes=[
                        *bundle.notes,
                        f"fewshot_selection=synthetic ({len(synthetic)} pairs)",
                    ],
                )
            elif not synthesis_note:
                synthesis_note = "fewshot_synthesis returned no pairs; using retrieved shots"
        enriched = ""
        enrich_note = ""
        if enrichment_provider is not None:
            try:
                enriched = enrich_question(
                    enrichment_provider,
                    question=question,
                    schema_text=render_schema_block(bundle),
                )
            except Exception as exc:  # enrichment is auxiliary — never fail the question
                enrich_note = f"question_enrichment failed: {type(exc).__name__}: {exc}"
            if not enriched and not enrich_note:
                enrich_note = "question_enrichment returned empty text"
        trace_extra: dict[str, object] = {}
        if synthesis_note:
            trace_extra["fewshot_synthesis"] = synthesis_note
        if enrichment_provider is not None:
            trace_extra["question_enriched"] = bool(enriched)
        if enrich_note:
            trace_extra["question_enrichment"] = enrich_note
        return {
            "context": bundle,
            "enriched_question": enriched,
            "trace": _append_trace(
                state,
                "context_builder",
                tables=bundle.all_tables,
                fewshots=len(bundle.fewshots),
                truncated=bundle.truncated,
                extended_sample_tables=(
                    sorted(bundle.extended_samples) if bundle.extended_samples else []
                ),
                value_matches=len(bundle.value_matches),
                fewshot_selection=fewshot_selection,
                **trace_extra,
            ),
        }

    return node


def _append_trace(state: PipelineState, node: str, **details: object) -> list[dict[str, object]]:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, **details})
    return trace
