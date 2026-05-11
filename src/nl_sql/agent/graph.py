"""LangGraph StateGraph wiring + a thin run-result wrapper.

Topology (per docs/02_architecture_v2.md §3):

    START
      │
      ▼
    context_builder
      │
      ▼
    generate_sql ◄────────────┐
      │                       │
      ▼                       │
    validate ──fail──► repair_once  (fired exactly once,
      │                              guarded by repair_attempted)
      ▼ ok
    execute ──fail──► repair_once
      │
      ▼ ok
    deterministic_format
      │
      ▼
    explain_trace
      │
      ▼
    END

Failure fall-through: when a fail happens AND repair was already attempted,
we route directly to deterministic_format with the error attached, so the
user always sees a structured caption + trace instead of a 500.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from nl_sql.agent.nodes import (
    make_context_builder_node,
    make_execute_node,
    make_explain_trace_node,
    make_format_node,
    make_generate_sql_node,
    make_repair_once_node,
    make_validate_node,
)
from nl_sql.agent.state import GenerateSQLOutput, PipelineState
from nl_sql.db.connection import Dialect
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.runner import ExecutionOutcome
from nl_sql.llm.providers.base import LLMProvider
from nl_sql.render.formats import OutputFormat
from nl_sql.schema_index.indexer import SchemaIndex


@dataclass(slots=True)
class PipelineConfig:
    """All runtime dependencies. Tests inject fakes via this object."""

    sql_provider: LLMProvider
    explain_provider: LLMProvider
    schema_index: SchemaIndex
    registry: DatabaseRegistry
    schema_top_k: int = 5
    fewshot_top_k: int = 3
    fk_hops: int = 1
    table_budget: int = 12
    statement_timeout_ms: int = 30_000
    row_cap: int = 10_000
    sort_schema_block: bool = True
    """Render schema_block in alphabetical-by-table-name order instead of
    retrieval-distance + FK BFS order. Empirically the single biggest
    retrieval-side EA lever on BIRD Mini-Dev under codestral
    (+3pp moderate, +5.5pp challenging at n=100; +5pp moderate at n=200).
    Default ON since 2026-05-11 per docs/SESSION_HANDOFF.md item #2.
    Set to False explicitly to recover the unsorted retrieval-distance
    baseline for ablation."""
    primary_sample_size: int = 3
    """Sample density already baked into the chunks stored in Chroma.
    Must match the `--sample-size` used by `scripts/build_index.py` when
    the current `chroma_data/` was built. Used together with
    `extended_sample_size` to compute the tail for the mixture appendix.
    """
    extended_sample_size: int = 0
    """Per-difficulty sample mixture (off by default). When > 0 and
    > `primary_sample_size`, the context_builder fetches sample values
    rows `primary..extended` per column for retrieved tables and
    `render_schema_block` appends them as an "additional sample values"
    section. Empirically: s=3 cards favour moderate-tier accuracy, s=5
    cards favour challenging-tier; the mixture exposes both densities
    to the model in a single prompt. Requires registry access — see
    docs/SESSION_HANDOFF.md item #1."""
    sql_temperature: float = 0.0
    """Sampling temperature for the generate_sql / repair_once LLM calls.
    Default 0.0 = greedy / deterministic. Higher values inject diversity
    needed by config F (self-consistency execution-based voting), where
    each candidate runs at a different temperature so the cache stores
    them as distinct entries."""
    cross_db_fewshot: bool = False
    """When True, few-shot retrieval skips the `db_id` filter and pulls
    Q→SQL hits from any database in the `fewshot_qsql` collection. Needed
    for BIRD, whose train and dev splits are partitioned by db_id (zero
    overlap) — same-db retrieval would return zero hits. Set ON by
    `run_config_d`; off everywhere else."""
    verify_retry_on_empty: bool = False
    """When True, route an EMPTY_RESULT outcome to `repair_once` instead
    of short-circuiting to deterministic_format. Empty rows often mean
    the model got the filter value wrong (case mismatch, LIKE pattern
    missing, NULL handling); a second pass with the empty-result hint
    can recover them. Subject to the standard `repair_attempted` guard —
    one extra LLM call per question, capped. Set ON by `run_config_g`."""


@dataclass(slots=True)
class PipelineRunResult:
    """Flat snapshot of the terminal state — what the caller needs."""

    question: str
    db_id: str
    sql: str
    rationale: str
    confidence: float
    outcome: ExecutionOutcome | None
    output_format: OutputFormat | None
    caption: str
    error_kind: ExecutionErrorKind | None
    error_message: str
    repair_attempted: bool
    trace: list[dict[str, object]]

    @property
    def ok(self) -> bool:
        return self.outcome is not None and self.outcome.ok and self.error_kind is None


def build_pipeline(config: PipelineConfig) -> CompiledStateGraph[Any, Any, Any, Any]:
    graph: StateGraph[PipelineState, None, PipelineState, PipelineState] = StateGraph(PipelineState)

    nodes: dict[str, Any] = {
        "context_builder": make_context_builder_node(
            config.schema_index,
            schema_top_k=config.schema_top_k,
            fewshot_top_k=config.fewshot_top_k,
            fk_hops=config.fk_hops,
            table_budget=config.table_budget,
            registry=config.registry,
            primary_sample_size=config.primary_sample_size,
            extended_sample_size=config.extended_sample_size,
            cross_db_fewshot=config.cross_db_fewshot,
        ),
        "generate_sql": make_generate_sql_node(
            config.sql_provider,
            sort_schema_block=config.sort_schema_block,
            temperature=config.sql_temperature,
        ),
        "validate": make_validate_node(),
        "repair_once": make_repair_once_node(
            config.sql_provider,
            sort_schema_block=config.sort_schema_block,
        ),
        "execute": make_execute_node(
            registry=config.registry,
            statement_timeout_ms=config.statement_timeout_ms,
            row_cap=config.row_cap,
        ),
        "deterministic_format": make_format_node(),
        "explain_trace": make_explain_trace_node(config.explain_provider),
    }
    for name, action in nodes.items():
        graph.add_node(name, action)

    graph.add_edge(START, "context_builder")
    graph.add_edge("context_builder", "generate_sql")
    graph.add_edge("generate_sql", "validate")
    graph.add_conditional_edges("validate", _route_after_validate)
    graph.add_edge("repair_once", "validate")
    graph.add_conditional_edges("execute", _route_after_execute)
    graph.add_edge("deterministic_format", "explain_trace")
    graph.add_edge("explain_trace", END)

    return graph.compile()


_AfterValidate = Literal["repair_once", "execute", "deterministic_format"]
_AfterExecute = Literal["repair_once", "deterministic_format"]


def _route_after_validate(state: PipelineState) -> _AfterValidate:
    outcome = state.get("outcome")
    if outcome is not None and outcome.error_kind is None:
        return "execute"
    if not state.get("repair_attempted"):
        return "repair_once"
    return "deterministic_format"


def _route_after_execute(state: PipelineState) -> _AfterExecute:
    outcome = state.get("outcome")
    if outcome is None:
        return "deterministic_format"
    if outcome.ok:
        return "deterministic_format"
    # EMPTY_RESULT is normally a valid outcome (zero rows is a legitimate
    # answer) → render handles the empty-set messaging. Config G flips this
    # to retry the empty case once, on the assumption that the model
    # confused a filter value (case mismatch, LIKE pattern, NULL handling).
    if outcome.error_kind == ExecutionErrorKind.EMPTY_RESULT:
        if state.get("verify_retry_on_empty") and not state.get("repair_attempted"):
            return "repair_once"
        return "deterministic_format"
    if not state.get("repair_attempted"):
        return "repair_once"
    return "deterministic_format"


def run_pipeline(
    pipeline: CompiledStateGraph[Any, Any, Any, Any],
    *,
    question: str,
    db_id: str,
    dialect: Dialect = "sqlite",
    disable_repair: bool = False,
    verify_retry_on_empty: bool = False,
) -> PipelineRunResult:
    """One-shot helper: invoke the compiled graph and flatten the result.

    `disable_repair` (default False): when True, sets repair_attempted in
    initial state, which causes both `_route_after_validate` and
    `_route_after_execute` to skip the repair branch on the first failure
    and fall through to deterministic_format. Used by eval configurations
    A-D where the methodology specifies "no repair" as a measured baseline.

    `verify_retry_on_empty` (default False): when True, an EMPTY_RESULT
    outcome routes to repair_once (subject to the repair_attempted guard)
    so the model can take a second swing at the filter values. Used by
    config G; the corresponding `last_error` payload comes from the
    execute node and includes the empty-result hint.
    """
    initial: PipelineState = {
        "question": question,
        "db_id": db_id,
        "dialect": dialect,
        "repair_attempted": disable_repair,
        "verify_retry_on_empty": verify_retry_on_empty,
        "trace": [],
    }
    final = cast(PipelineState, pipeline.invoke(initial))
    generated = final.get("generated") or GenerateSQLOutput(sql="")
    return PipelineRunResult(
        question=final.get("question", question),
        db_id=final.get("db_id", db_id),
        sql=generated.sql,
        rationale=generated.rationale,
        confidence=generated.confidence,
        outcome=final.get("outcome"),
        output_format=final.get("output_format"),
        caption=final.get("caption", ""),
        error_kind=final.get("error_kind"),
        error_message=final.get("error_message", ""),
        repair_attempted=bool(final.get("repair_attempted")),
        trace=list(final.get("trace") or []),
    )


__all__ = [
    "PipelineConfig",
    "PipelineRunResult",
    "build_pipeline",
    "run_pipeline",
]
