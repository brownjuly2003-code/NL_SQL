"""Resource bootstrap + pipeline factory for the Streamlit UI."""

from __future__ import annotations

from typing import Any

import chromadb
import streamlit as st

from nl_sql.agent.graph import PipelineConfig, build_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import DatabaseRegistry, get_default_registry
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers import build_provider
from nl_sql.llm.providers.base import EmbeddingProvider, LLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.paths import under_root
from nl_sql.schema_index.indexer import SchemaIndex


@st.cache_resource(show_spinner="Initialising providers + Chroma index…")
def bootstrap() -> tuple[DatabaseRegistry, SchemaIndex, LLMProvider, LLMProvider]:
    settings = get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in .env — required for embeddings.")

    registry = get_default_registry()

    persist_dir = under_root("chroma_data")
    if not persist_dir.is_dir():
        raise RuntimeError(
            f"Chroma persist dir {persist_dir!r} not found. "
            "Run `uv run python scripts/build_index.py --db all` first."
        )
    chroma_client = chromadb.PersistentClient(path=str(persist_dir))

    raw_embedder = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    embedder: EmbeddingProvider = CachingEmbeddingProvider(
        raw_embedder,
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    schema_index = SchemaIndex(persist_dir=persist_dir, embedder=embedder, client=chroma_client)

    raw_sql = build_provider(settings.default_provider, settings=settings)
    sql_provider: LLMProvider = CachingLLMProvider(
        raw_sql,
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    explain_provider = sql_provider

    return registry, schema_index, sql_provider, explain_provider


def make_pipeline(
    registry: DatabaseRegistry,
    schema_index: SchemaIndex,
    sql_provider: LLMProvider,
    explain_provider: LLMProvider,
    *,
    schema_top_k: int,
    fk_hops: int,
    table_budget: int,
    sort_schema_block: bool,
    extended_sample_size: int,
    fewshot_top_k: int = 3,
    cross_db_fewshot: bool = True,
    verify_retry_on_empty: bool = True,
) -> Any:
    config = PipelineConfig(
        sql_provider=sql_provider,
        explain_provider=explain_provider,
        schema_index=schema_index,
        registry=registry,
        schema_top_k=schema_top_k,
        fewshot_top_k=fewshot_top_k,
        fk_hops=fk_hops,
        table_budget=table_budget,
        sort_schema_block=sort_schema_block,
        primary_sample_size=3,
        extended_sample_size=extended_sample_size,
        cross_db_fewshot=cross_db_fewshot,
        verify_retry_on_empty=verify_retry_on_empty,
    )
    return build_pipeline(config)
