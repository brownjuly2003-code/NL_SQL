"""Mutable state shared across all pipeline nodes.

LangGraph's `StateGraph` merges per-node return dicts back into this state.
Keep field semantics tight — every reader/writer is a node, and adding a
field with unclear ownership multiplies coupling fast.

Optional fields default to ``None`` (not missing) so node code can `state.get`
and reason about presence vs. absence cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from nl_sql.db.connection import Dialect
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.runner import ExecutionOutcome
from nl_sql.render.formats import OutputFormat
from nl_sql.schema_index.retriever import ContextBundle


@dataclass(frozen=True, slots=True)
class GenerateSQLOutput:
    """Structured output of the `generate_sql` node.

    Per docs/02_architecture_v2.md §3, the LLM returns ``sql + rationale +
    tables_used + confidence``. ``raw_text`` keeps the original response
    for tracing/debugging — handy when JSON parsing degraded or the model
    hallucinated keys.
    """

    sql: str
    rationale: str = ""
    tables_used: tuple[str, ...] = ()
    confidence: float = 0.0
    raw_text: str = ""


class PipelineState(TypedDict, total=False):
    """Per-question state. ``total=False`` so partial dicts merge cleanly."""

    # --- input ----------------------------------------------------------
    question: str
    db_id: str
    dialect: Dialect

    # --- after context_builder -----------------------------------------
    context: ContextBundle | None

    # --- after plan_query (optional, only when enable_planner=True) ----
    plan: str
    """Structured plan (raw JSON text) produced by `plan_query` before
    SQL generation. Empty when the planner stage is disabled."""

    # --- after generate_sql --------------------------------------------
    generated: GenerateSQLOutput | None

    # --- after validate -------------------------------------------------
    # ExecutionOutcome carries both validation report and (later) execution
    # result, so a single field covers both phases.
    outcome: ExecutionOutcome | None

    # --- repair bookkeeping --------------------------------------------
    repair_attempted: bool
    last_error: str  # error context fed into the repair prompt
    verify_retry_on_empty: bool
    """When True, the empty-result branch in `_route_after_execute` flows
    to `repair_once` (subject to the repair_attempted guard) instead of
    short-circuiting to deterministic_format. Empty rows are often a
    silent miss (wrong filter value, case mismatch, NULL handling), so a
    second LLM pass with the empty-result signal can recover them. Set
    by `run_config_g`; off everywhere else."""
    critique_failed: bool

    # --- after deterministic_format ------------------------------------
    output_format: OutputFormat | None

    # --- after explain_trace -------------------------------------------
    caption: str

    # --- terminal status ------------------------------------------------
    error_kind: ExecutionErrorKind | None
    error_message: str

    # --- diagnostic / observability -------------------------------------
    trace: list[dict[str, Any]]
