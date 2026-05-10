"""Ablation runner — orchestrates per-configuration eval over BIRD examples.

Per docs/03_eval_methodology.md §4 there are five configurations A-E.
Stage 6 first milestone = config A only. B-E surface as `Configuration`
enum members but `run_config_*` helpers raise NotImplementedError, so the
report writer can already render placeholder rows for them.

Config A — `full_schema` baseline:
    Dump every table chunk for the target db into the prompt. No dense
    retrieval, no FK graph traversal, no fewshots, no repair. The first
    real number we publish lives here, so the implementation is
    deliberately the simplest end-to-end path that exercises the
    generate → validate → execute → compare loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from nl_sql.agent import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.agent.nodes._support import (
    parse_generate_sql_output,
    render_fewshot_block,
    render_schema_block,
)
from nl_sql.agent.prompts import load_prompt
from nl_sql.db.connection import Dialect, execute_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.eval.dataset import BirdExample, extract_gold_tables
from nl_sql.eval.metrics.execution_accuracy import (
    ResultComparison,
    compare_results,
    execution_accuracy,
)
from nl_sql.eval.metrics.schema_recall import schema_recall_at_k
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.execution.runner import ExecutionOutcome, execute_validated
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider
from nl_sql.schema_index.chunker import SchemaChunk, to_chunks
from nl_sql.schema_index.indexer import SchemaIndex, SchemaQueryHit
from nl_sql.schema_index.introspector import introspect
from nl_sql.schema_index.retriever import ContextBundle


class Configuration(StrEnum):
    """The 5 configurations from docs/03_eval_methodology.md §4.1."""

    A_FULL_SCHEMA = "A_full_schema"
    B_BM25 = "B_bm25_cards"
    C_DENSE = "C_dense_cards"
    D_FEWSHOT = "D_dense_fewshot"
    E_FINAL = "E_dense_fewshot_repair"


@dataclass(frozen=True, slots=True)
class EvalRecord:
    """Per-example outcome. `match` is the EA bit."""

    question_id: int
    db_id: str
    difficulty: str
    dialect: str
    question: str
    gold_sql: str
    pred_sql: str
    match: bool
    schema_recall: bool
    error_kind: str | None
    error_message: str
    repair_attempted: bool
    first_pass_match: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int
    gold_tables: tuple[str, ...]
    retrieved_tables: tuple[str, ...]
    pred_row_count: int
    gold_row_count: int
    comparison_reason: str


@dataclass(slots=True)
class EvalSummary:
    """Aggregates per a slice (overall, per-difficulty, etc)."""

    n: int
    ea: float
    validity_rate: float
    schema_recall_at_k: float
    repair_success_rate: float
    first_pass_ea: float
    empty_result_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    tokens_p50: float
    tokens_p95: float


@dataclass(slots=True)
class EvalRun:
    """Result of running one configuration against a list of examples."""

    configuration: Configuration
    sql_model: str
    overall: EvalSummary
    per_difficulty: dict[str, EvalSummary] = field(default_factory=dict)
    records: list[EvalRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point — only Configuration.A is implemented in milestone 1.
# ---------------------------------------------------------------------------


def run_config_a(
    examples: Sequence[BirdExample],
    *,
    sql_provider: LLMProvider,
    registry: DatabaseRegistry,
    statement_timeout_ms: int = 60_000,
    row_cap: int = 10_000,
    sample_size: int = 3,
    max_tokens: int = 1024,
    progress: Callable[[int, int, EvalRecord], None] | None = None,
) -> EvalRun:
    """Run configuration A (full_schema baseline) against `examples`.

    `progress` (optional): called after every example as
    `progress(idx, total, record)` — used by `scripts/eval_baseline.py` to
    print live status without polluting the runner with stdout.
    """
    schema_cache: dict[str, list[SchemaChunk]] = {}
    records: list[EvalRecord] = []

    for idx, example in enumerate(examples, start=1):
        record = _run_one_config_a(
            example,
            sql_provider=sql_provider,
            registry=registry,
            schema_cache=schema_cache,
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
            sample_size=sample_size,
            max_tokens=max_tokens,
        )
        records.append(record)
        if progress is not None:
            progress(idx, len(examples), record)

    return _summarise(
        configuration=Configuration.A_FULL_SCHEMA,
        sql_model=getattr(sql_provider, "model", "unknown"),
        records=records,
    )


def run_config_b(*_: Any, **__: Any) -> EvalRun:
    raise NotImplementedError("Configuration B (BM25) ships in stage 6.b")


def run_config_c(
    examples: Sequence[BirdExample],
    *,
    sql_provider: LLMProvider,
    explain_provider: LLMProvider,
    schema_index: SchemaIndex,
    registry: DatabaseRegistry,
    schema_top_k: int = 5,
    fk_hops: int = 1,
    table_budget: int = 12,
    statement_timeout_ms: int = 60_000,
    row_cap: int = 10_000,
    max_tokens: int = 1024,
    progress: Callable[[int, int, EvalRecord], None] | None = None,
) -> EvalRun:
    """Run configuration C (dense schema cards + FK 1-hop, no fewshot, no repair).

    Reuses the production LangGraph pipeline so the eval signal directly
    measures the same code path the API will serve. `disable_repair=True`
    flips the route_after_validate/execute conditional edges to fall through
    to deterministic_format on first failure, so we measure first-pass EA.
    """
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_provider,
            explain_provider=explain_provider,
            schema_index=schema_index,
            registry=registry,
            schema_top_k=schema_top_k,
            fewshot_top_k=0,
            fk_hops=fk_hops,
            table_budget=table_budget,
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
        )
    )
    records: list[EvalRecord] = []
    for idx, example in enumerate(examples, start=1):
        record = _run_one_via_pipeline(
            example,
            pipeline=pipeline,
            registry=registry,
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
            disable_repair=True,
        )
        records.append(record)
        if progress is not None:
            progress(idx, len(examples), record)
    return _summarise(
        configuration=Configuration.C_DENSE,
        sql_model=getattr(sql_provider, "model", "unknown"),
        records=records,
    )


def run_config_d(*_: Any, **__: Any) -> EvalRun:
    raise NotImplementedError("Configuration D (+ fewshot) ships in stage 6.d")


def run_config_e(*_: Any, **__: Any) -> EvalRun:
    raise NotImplementedError("Configuration E (+ repair) ships in stage 6.e")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_one_config_a(
    example: BirdExample,
    *,
    sql_provider: LLMProvider,
    registry: DatabaseRegistry,
    schema_cache: dict[str, list[SchemaChunk]],
    statement_timeout_ms: int,
    row_cap: int,
    sample_size: int,
    max_tokens: int,
) -> EvalRecord:
    started = time.perf_counter()
    spec = registry.get(example.registry_db_id)
    engine = spec.make_engine()
    try:
        chunks = _full_schema_chunks(
            engine, db_id=example.registry_db_id, cache=schema_cache, sample_size=sample_size
        )
        bundle = _bundle_from_chunks(chunks, question=example.question, db_id=example.registry_db_id)
        prompt = load_prompt(
            "generate_sql",
            dialect=example.dialect,
            schema_block=render_schema_block(bundle),
            fewshot_block=render_fewshot_block(bundle),
            question=_compose_question(example),
        )
        response = sql_provider.generate(
            GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=0.0)
        )
        parsed = parse_generate_sql_output(response.text)
        pred_sql = parsed.sql
        outcome = execute_validated(
            engine,
            pred_sql,
            dialect=_to_dialect(example.dialect),
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
        )
        gold_rows, gold_columns = _execute_gold(
            engine,
            example.sql,
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
        )
        comparison = _compare_outcome(outcome, gold_rows, gold_sql=example.sql)
        gold_tables = tuple(extract_gold_tables(example.sql))
        retrieved = tuple(c.table_name for c in chunks)
        recall = schema_recall_at_k(gold_tables, retrieved)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return EvalRecord(
            question_id=example.question_id,
            db_id=example.db_id,
            difficulty=example.difficulty,
            dialect=example.dialect,
            question=example.question,
            gold_sql=example.sql,
            pred_sql=pred_sql,
            match=comparison.match,
            schema_recall=recall,
            error_kind=outcome.error_kind.value if outcome.error_kind else None,
            error_message=outcome.error_message,
            repair_attempted=False,
            first_pass_match=comparison.match,  # config A has no repair
            latency_ms=elapsed_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            gold_tables=gold_tables,
            retrieved_tables=retrieved,
            pred_row_count=comparison.pred_rows,
            gold_row_count=comparison.gold_rows,
            comparison_reason=comparison.reason,
        )
    finally:
        engine.dispose()
        # Suppress unused; gold_columns kept for future per-column F1 metric.
        del gold_columns


def _run_one_via_pipeline(
    example: BirdExample,
    *,
    pipeline: Any,
    registry: DatabaseRegistry,
    statement_timeout_ms: int,
    row_cap: int,
    disable_repair: bool,
) -> EvalRecord:
    """Drive one example through the compiled LangGraph pipeline.

    Used by configurations C/D/E (and any future config that wants the
    production code path with knobs flipped). EA is computed against the
    same gold engine via `_execute_gold` to keep parity with config A.
    """
    started = time.perf_counter()
    spec = registry.get(example.registry_db_id)
    gold_engine = spec.make_engine()
    try:
        try:
            result = run_pipeline(
                pipeline,
                question=_compose_question(example),
                db_id=example.registry_db_id,
                dialect=_to_dialect(example.dialect),
                disable_repair=disable_repair,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return EvalRecord(
                question_id=example.question_id,
                db_id=example.db_id,
                difficulty=example.difficulty,
                dialect=example.dialect,
                question=example.question,
                gold_sql=example.sql,
                pred_sql="",
                match=False,
                schema_recall=False,
                error_kind="pipeline_exception",
                error_message=str(exc),
                repair_attempted=False,
                first_pass_match=False,
                latency_ms=elapsed_ms,
                input_tokens=0,
                output_tokens=0,
                gold_tables=tuple(extract_gold_tables(example.sql)),
                retrieved_tables=(),
                pred_row_count=0,
                gold_row_count=0,
                comparison_reason=f"pipeline raised: {exc!r}",
            )
        gold_rows, _ = _execute_gold(
            gold_engine,
            example.sql,
            statement_timeout_ms=statement_timeout_ms,
            row_cap=row_cap,
        )
        # The pipeline's outcome is what `match` should reflect — but the
        # comparison runs against the gold rows we just fetched. Build a
        # synthetic outcome view for `_compare_outcome`, or pull rows out.
        if result.outcome is not None and result.outcome.result is not None:
            comparison = compare_results(
                gold_rows,
                result.outcome.result.rows,
                gold_sql=example.sql,
            )
        else:
            comparison = ResultComparison(
                match=False,
                reason=(
                    f"pred failed: {result.error_kind.value if result.error_kind else 'unknown'}"
                ),
                gold_rows=len(gold_rows),
                pred_rows=0,
            )
        gold_tables = tuple(extract_gold_tables(example.sql))
        retrieved = _retrieved_from_trace(result.trace)
        recall = schema_recall_at_k(gold_tables, retrieved)
        in_tok, out_tok = _tokens_from_trace(result.trace)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return EvalRecord(
            question_id=example.question_id,
            db_id=example.db_id,
            difficulty=example.difficulty,
            dialect=example.dialect,
            question=example.question,
            gold_sql=example.sql,
            pred_sql=result.sql,
            match=comparison.match,
            schema_recall=recall,
            error_kind=result.error_kind.value if result.error_kind else None,
            error_message=result.error_message,
            # `disable_repair=True` seeds repair_attempted in initial state to
            # short-circuit routing — that's not a "repair happened" signal,
            # so suppress it in the record. When repair is enabled, trust the
            # pipeline's flag.
            repair_attempted=False if disable_repair else result.repair_attempted,
            first_pass_match=comparison.match,
            latency_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            gold_tables=gold_tables,
            retrieved_tables=tuple(retrieved),
            pred_row_count=comparison.pred_rows,
            gold_row_count=comparison.gold_rows,
            comparison_reason=comparison.reason,
        )
    finally:
        gold_engine.dispose()


def _retrieved_from_trace(trace: list[dict[str, object]]) -> tuple[str, ...]:
    """Pull `tables` from the context_builder trace step (set by node)."""
    for step in trace:
        if step.get("node") == "context_builder":
            tables = step.get("tables")
            if isinstance(tables, list):
                return tuple(str(t) for t in tables)
            break
    return ()


def _tokens_from_trace(trace: list[dict[str, object]]) -> tuple[int, int]:
    """Sum input + output tokens across all generate-style trace steps."""
    in_tok = 0
    out_tok = 0
    for step in trace:
        i = step.get("input_tokens")
        o = step.get("output_tokens")
        in_tok += int(i) if isinstance(i, (int, float)) else 0
        out_tok += int(o) if isinstance(o, (int, float)) else 0
    return in_tok, out_tok


def _full_schema_chunks(
    engine: Engine,
    *,
    db_id: str,
    cache: dict[str, list[SchemaChunk]],
    sample_size: int,
) -> list[SchemaChunk]:
    if db_id in cache:
        return cache[db_id]
    tables = introspect(engine, sample_size=sample_size)
    chunks = to_chunks(tables, db_id=db_id)
    cache[db_id] = chunks
    return chunks


def _bundle_from_chunks(
    chunks: list[SchemaChunk],
    *,
    question: str,
    db_id: str,
) -> ContextBundle:
    """Synthesize a ContextBundle that puts every table into `schema_hits`.

    distance=inf marks each as graph-derived rather than dense-retrieved —
    `render_schema_block` doesn't care about distance, but downstream tracing
    can still tell config A bundles apart from config C/D bundles.
    """
    hits = [
        SchemaQueryHit(
            chunk_id=c.chunk_id,
            table_name=c.table_name,
            db_id=c.db_id,
            text=c.text,
            distance=float("inf"),
            metadata=dict(c.metadata),
        )
        for c in chunks
    ]
    return ContextBundle(
        db_id=db_id,
        question=question,
        schema_hits=hits,
        fk_neighbours=[],
        fewshots=[],
        truncated=False,
        notes=["config-A: full schema, no retrieval"],
    )


def _compose_question(example: BirdExample) -> str:
    """Embed BIRD `evidence` (external knowledge) inline with the question.

    BIRD's leaderboard runs the evaluation_ex baseline *with* evidence —
    the gold SQL often relies on definitions that only appear in evidence.
    Dropping it would underestimate model capability across the board.
    """
    if not example.evidence:
        return example.question
    return f"{example.question}\n\nHint: {example.evidence}"


def _execute_gold(
    engine: Engine,
    sql: str,
    *,
    statement_timeout_ms: int,
    row_cap: int,
) -> tuple[list[tuple[Any, ...]], list[str]]:
    """Run gold SQL with the same row cap / timeout as predictions.

    Bypasses the validator (gold is trusted, BIRD ships it). Errors propagate
    as empty result + sentinel — the EA comparison will then fail naturally.
    """
    try:
        with execute_readonly(
            engine, sql, statement_timeout_ms=statement_timeout_ms, row_cap=row_cap
        ) as result:
            return list(result.rows), list(result.columns)
    except SQLAlchemyError:
        # Last-resort: try the raw connection to surface gold-SQL bugs in
        # logs without crashing the runner. BIRD ships ~1% gold SQLs that
        # fail under sqlite default settings; we count them as gold-failure
        # rather than pred-failure.
        try:
            with engine.connect() as conn:
                cursor = conn.execute(text(sql))
                cols = list(cursor.keys())
                rows = [tuple(r) for r in cursor.fetchmany(row_cap)]
                cursor.close()
                return rows, cols
        except SQLAlchemyError:
            return [], []


def _compare_outcome(
    outcome: ExecutionOutcome,
    gold_rows: list[tuple[Any, ...]],
    *,
    gold_sql: str,
) -> ResultComparison:
    if outcome.result is None:
        return ResultComparison(
            match=False,
            reason=f"pred failed: {outcome.error_kind.value if outcome.error_kind else 'unknown'}",
            gold_rows=len(gold_rows),
            pred_rows=0,
        )
    return compare_results(gold_rows, outcome.result.rows, gold_sql=gold_sql)


def _to_dialect(dialect: str) -> Dialect:
    if dialect in ("sqlite", "postgresql"):
        return dialect  # type: ignore[return-value]
    return "sqlite"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _summarise(
    *,
    configuration: Configuration,
    sql_model: str,
    records: list[EvalRecord],
) -> EvalRun:
    overall = _summary_for(records)
    per_difficulty = {
        diff: _summary_for([r for r in records if r.difficulty == diff])
        for diff in ("simple", "moderate", "challenging")
    }
    return EvalRun(
        configuration=configuration,
        sql_model=sql_model,
        overall=overall,
        per_difficulty=per_difficulty,
        records=records,
    )


def _summary_for(records: Iterable[EvalRecord]) -> EvalSummary:
    rs = list(records)
    if not rs:
        return EvalSummary(
            n=0,
            ea=0.0,
            validity_rate=0.0,
            schema_recall_at_k=0.0,
            repair_success_rate=0.0,
            first_pass_ea=0.0,
            empty_result_rate=0.0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            tokens_p50=0.0,
            tokens_p95=0.0,
        )
    matches = [r.match for r in rs]
    valid = [r.error_kind != ExecutionErrorKind.INVALID_SQL.value for r in rs]
    repair_success = [
        r.match for r in rs if r.repair_attempted
    ]
    empty = [r.error_kind == ExecutionErrorKind.EMPTY_RESULT.value for r in rs]
    latencies = sorted(r.latency_ms for r in rs)
    tokens = sorted((r.input_tokens + r.output_tokens) for r in rs)
    return EvalSummary(
        n=len(rs),
        ea=execution_accuracy(matches),
        validity_rate=sum(valid) / len(rs),
        schema_recall_at_k=sum(1 for r in rs if r.schema_recall) / len(rs),
        repair_success_rate=(sum(repair_success) / len(repair_success)) if repair_success else 0.0,
        first_pass_ea=sum(1 for r in rs if r.first_pass_match) / len(rs),
        empty_result_rate=sum(empty) / len(rs),
        latency_p50_ms=_percentile(latencies, 0.5),
        latency_p95_ms=_percentile(latencies, 0.95),
        tokens_p50=_percentile(tokens, 0.5),
        tokens_p95=_percentile(tokens, 0.95),
    )


def _percentile(sorted_values: Sequence[float | int], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    frac = pos - low
    return float(sorted_values[low]) * (1 - frac) + float(sorted_values[high]) * frac
