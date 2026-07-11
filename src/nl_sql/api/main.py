"""FastAPI surface for the NL→SQL Assistant.

Endpoints:
    GET  /healthz        — liveness probe + provider configuration snapshot.
    GET  /readyz         — readiness probe (Chroma + DB registry reachable).
    GET  /databases      — list registered DBs + table counts.
    POST /ask            — translate question to SQL, execute, return result.
    GET  /eval/latest    — metadata of the latest committed eval report.

Auth:
    Set ``NL_SQL_API_KEY`` (env, .env, or settings). When set, every request
    to /ask and /databases must include ``X-API-Key`` matching it. /healthz
    and /readyz are always open for orchestrator probes.

Rate limit:
    In-process token bucket per API key (60 req/min default). No external
    Redis — this is a single-replica portfolio demo, not a fleet service.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from nl_sql import __version__
from nl_sql.agent.graph import (
    PipelineConfig,
    PipelineRunResult,
    build_pipeline,
    run_pipeline,
)
from nl_sql.config import Settings, get_settings
from nl_sql.db.registry import DatabaseRegistry, get_default_registry
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers import build_provider
from nl_sql.llm.providers.base import EmbeddingProvider, LLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.schema_index.indexer import SchemaIndex

logger = logging.getLogger("nl_sql.api")

# ---------------------------------------------------------- response models


class HealthResponse(BaseModel):
    status: str
    version: str
    providers_configured: list[str]


class ReadyResponse(BaseModel):
    status: str
    chroma_ok: bool
    registry_ok: bool
    registered_dbs: int
    schema_chunks: int


class DatabaseInfo(BaseModel):
    db_id: str
    dialect: str
    description: str = ""
    table_count: int


class DatabasesResponse(BaseModel):
    databases: list[DatabaseInfo]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    db_id: str = Field(min_length=1)


class TraceStep(BaseModel):
    node: str
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    confidence: float | None = None


class AskResponse(BaseModel):
    trace_id: str
    db_id: str
    sql: str
    rationale: str
    confidence: float
    confidence_label: str
    rows: list[list[Any]] | None
    columns: list[str] | None
    row_count: int
    truncated: bool
    caption: str
    output_format: str | None
    error_kind: str | None
    error_message: str
    repair_attempted: bool
    latency_ms: float
    trace: list[TraceStep]


class EvalLatestResponse(BaseModel):
    configuration: str
    sql_model: str
    overall_ea: float | None
    n: int
    report_path: str


# ---------------------------------------------------------- helpers


def _confidence_label(value: float) -> str:
    if value >= 0.8:
        return "High"
    if value >= 0.5:
        return "Medium"
    if value > 0.0:
        return "Low"
    return "Unknown"


def _result_to_response(result: PipelineRunResult, *, latency_ms: float) -> AskResponse:
    rows: list[list[Any]] | None = None
    columns: list[str] | None = None
    row_count = 0
    truncated = False
    if result.outcome is not None and result.outcome.result is not None:
        rows = [list(r) for r in result.outcome.result.rows]
        columns = list(result.outcome.result.columns)
        row_count = result.outcome.result.row_count
        truncated = result.outcome.result.truncated

    trace_steps: list[TraceStep] = []
    for step in result.trace:
        trace_steps.append(
            TraceStep(
                node=str(step.get("node", "?")),
                model=step.get("model"),  # type: ignore[arg-type]
                tokens_in=step.get("input_tokens"),  # type: ignore[arg-type]
                tokens_out=step.get("output_tokens"),  # type: ignore[arg-type]
                confidence=step.get("confidence"),  # type: ignore[arg-type]
            )
        )

    fmt_name = None if result.output_format is None else type(result.output_format).__name__

    return AskResponse(
        trace_id=str(uuid.uuid4()),
        db_id=result.db_id,
        sql=result.sql,
        rationale=result.rationale,
        confidence=result.confidence,
        confidence_label=_confidence_label(result.confidence),
        rows=rows,
        columns=columns,
        row_count=row_count,
        truncated=truncated,
        caption=result.caption,
        output_format=fmt_name,
        error_kind=result.error_kind.value if result.error_kind else None,
        error_message=result.error_message,
        repair_attempted=result.repair_attempted,
        latency_ms=latency_ms,
        trace=trace_steps,
    )


# ---------------------------------------------------------- rate limit


class _TokenBucket:
    """Sliding-window token bucket per key.

    Default: 60 requests per 60 seconds. Single-process state — fine for the
    portfolio demo. Move to Redis if/when running multiple replicas.
    """

    def __init__(self, *, max_req: int = 60, window_s: int = 60) -> None:
        self.max_req = max_req
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.time()
        bucket = self._hits[key]
        cutoff = now - self.window_s
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_req:
            retry_after = int(self.window_s - (now - bucket[0]))
            return False, max(retry_after, 1)
        bucket.append(now)
        return True, 0


# ---------------------------------------------------------- bootstrap


def _build_pipeline_components(
    settings: Settings,
) -> tuple[DatabaseRegistry, SchemaIndex, LLMProvider, LLMProvider]:
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set — API can't bootstrap embeddings.")
    raw_sql = build_provider(settings.default_provider, settings=settings)
    sql_provider: LLMProvider = CachingLLMProvider(raw_sql, cache_dir=settings.llm_cache_dir)
    explain_provider: LLMProvider = sql_provider
    raw_embed: EmbeddingProvider = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    embedder: EmbeddingProvider = CachingEmbeddingProvider(
        raw_embed, cache_dir=settings.llm_cache_dir
    )
    schema_index = SchemaIndex(persist_dir="chroma_data", embedder=embedder)
    registry = get_default_registry()
    return registry, schema_index, sql_provider, explain_provider


class Singletons(NamedTuple):
    """The four runtime objects the API routes share.

    Exposed as a public type so tests can construct mock instances and feed
    them through ``app.dependency_overrides[get_singletons]``.
    """

    pipeline: Any
    registry: DatabaseRegistry
    schema_index: SchemaIndex
    sql_provider: LLMProvider


@lru_cache(maxsize=1)
def _make_singletons() -> Singletons:
    """Lazy: build the pipeline only when the first /ask hits — keeps /healthz
    fast and avoids touching Chroma when the API is used for status probes."""
    import os

    settings = get_settings()
    registry, schema_index, sql_provider, explain_provider = _build_pipeline_components(settings)
    # Eval-script env toggles bootstrap into PipelineConfig once at boot;
    # individual nodes never read os.environ at runtime (see graph.py docstrings).
    config = PipelineConfig(
        sql_provider=sql_provider,
        explain_provider=explain_provider,
        schema_index=schema_index,
        registry=registry,
        fewshot_top_k=3,
        sort_schema_block=True,
        cross_db_fewshot=True,
        verify_retry_on_empty=True,
        use_m_schema=os.environ.get("NLSQL_M_SCHEMA") == "1",
        use_dac_prompt=os.environ.get("NLSQL_DAC") == "1",
    )
    pipeline = build_pipeline(config)
    return Singletons(pipeline, registry, schema_index, sql_provider)


def get_singletons() -> Singletons:
    """FastAPI Depends-able factory; tests override via ``app.dependency_overrides``."""
    return _make_singletons()


def create_app() -> FastAPI:
    app = FastAPI(
        title="NL→SQL Assistant",
        version=__version__,
        description=(
            "Portfolio API: natural-language questions → SQL → executed rows. "
            "BIRD Mini-Dev 57% hybrid, Chinook 100%, $0 budget, AST safety guards."
        ),
    )
    settings = get_settings()
    rate_limiter = _TokenBucket(max_req=60, window_s=60)

    # Read from Settings (honours .env), not os.environ directly.
    api_key_env = settings.api_key

    async def require_api_key(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        # 1. Auth — only enforced when a key is configured. Constant-time compare
        #    so a timing side-channel can't leak the key byte by byte (the
        #    `and` short-circuits, so compare_digest only runs when a key is set).
        if api_key_env and (
            x_api_key is None or not secrets.compare_digest(x_api_key, api_key_env)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing or invalid X-API-Key header",
            )

        # 2. Rate limit — ALWAYS on, even with no key. A keyless public deploy is
        #    otherwise unthrottled (the README promises 60 req/min). Bucket by key
        #    when present, else by client IP.
        client_host = request.client.host if request.client else "unknown"
        bucket_key = x_api_key or client_host
        ok, retry_after = rate_limiter.check(bucket_key)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"rate limit exceeded; retry in {retry_after}s",
                headers={"Retry-After": str(retry_after)},
            )
        return x_api_key or "anonymous"

    # --------------------------------------------------------- health / ready

    @app.get("/healthz", response_model=HealthResponse, tags=["status"])
    def healthz() -> HealthResponse:
        configured: list[str] = []
        if settings.mistral_api_key:
            configured.append("mistral")
        if settings.github_token:
            configured.append("github_models")
        if settings.groq_api_key:
            configured.append("groq")
        configured.append("ollama")
        return HealthResponse(
            status="ok",
            version=__version__,
            providers_configured=sorted(configured),
        )

    @app.get("/readyz", response_model=ReadyResponse, tags=["status"])
    def readyz() -> ReadyResponse:
        chroma_ok = False
        registry_ok = False
        registered = 0
        schema_chunks = 0
        try:
            factory: Any = app.dependency_overrides.get(get_singletons, get_singletons)
            singletons: Singletons = factory()
            registered = len(singletons.registry.ids())
            registry_ok = registered > 0
            schema_chunks = singletons.schema_index.schema_collection.count()
            chroma_ok = schema_chunks > 0
        except Exception:
            pass
        all_ok = chroma_ok and registry_ok
        return ReadyResponse(
            status="ok" if all_ok else "not_ready",
            chroma_ok=chroma_ok,
            registry_ok=registry_ok,
            registered_dbs=registered,
            schema_chunks=schema_chunks,
        )

    # --------------------------------------------------------- product API

    @app.get("/databases", response_model=DatabasesResponse, tags=["catalog"])
    def databases(
        _auth: str = Depends(require_api_key),
        singletons: Singletons = Depends(get_singletons),  # noqa: B008
    ) -> DatabasesResponse:
        infos: list[DatabaseInfo] = []
        for db_id in singletons.registry.ids():
            spec = singletons.registry.get(db_id)
            try:
                records = singletons.schema_index.schema_collection.get(
                    where={"db_id": db_id}, include=["metadatas"]
                )
                table_count = len(records.get("metadatas") or [])
            except Exception:
                table_count = 0
            infos.append(
                DatabaseInfo(
                    db_id=db_id,
                    dialect=str(spec.dialect),
                    description=str(getattr(spec, "description", "") or ""),
                    table_count=table_count,
                )
            )
        return DatabasesResponse(databases=infos)

    @app.post("/ask", response_model=AskResponse, tags=["nl-sql"])
    def ask(
        req: AskRequest,
        _auth: str = Depends(require_api_key),
        singletons: Singletons = Depends(get_singletons),  # noqa: B008
    ) -> AskResponse:
        if req.db_id not in singletons.registry.ids():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown db_id: {req.db_id!r}; see /databases for the list",
            )
        spec = singletons.registry.get(req.db_id)
        t0 = time.perf_counter()
        try:
            result = run_pipeline(
                singletons.pipeline,
                question=req.question,
                db_id=req.db_id,
                dialect=spec.dialect,
                verify_retry_on_empty=True,
            )
        except Exception as exc:
            # Never leak exception text (paths, driver internals, provider
            # payloads) to the client. Log the detail server-side under a
            # trace_id the caller can quote in a bug report.
            trace_id = str(uuid.uuid4())
            logger.exception("pipeline crashed [trace_id=%s]", trace_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"internal pipeline error (trace_id={trace_id})",
            ) from exc
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return _result_to_response(result, latency_ms=latency_ms)

    @app.get("/eval/latest", response_model=EvalLatestResponse, tags=["transparency"])
    def eval_latest() -> EvalLatestResponse:
        """Returns metadata of the latest hybrid eval report committed to repo."""
        import json

        baseline = Path("eval/baselines/hybrid_n200_v0.json")
        if not baseline.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no committed baseline yet — run scripts/eval_baseline.py",
            )
        data = json.loads(baseline.read_text(encoding="utf-8"))
        overall = data.get("overall") or {}
        return EvalLatestResponse(
            configuration=str(data.get("configuration", "unknown")),
            sql_model=str(data.get("sql_model", "unknown")),
            overall_ea=overall.get("ea"),
            n=int(overall.get("n") or 0),
            report_path=str(baseline),
        )

    return app


app = create_app()
