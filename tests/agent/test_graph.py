from __future__ import annotations

import gc
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import chromadb
import pytest
from sqlalchemy.engine import Engine

from nl_sql.agent import PipelineConfig, PipelineState, build_pipeline
from nl_sql.db.connection import DatabaseSpec, sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.llm.providers.base import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
)
from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.introspector import introspect


class FakeEmbedder:
    def embed(self, req: EmbedRequest) -> EmbedResponse:
        import hashlib

        return EmbedResponse(
            vectors=[
                [b / 255.0 for b in hashlib.sha1(t.encode("utf-8")).digest()[:8]] for t in req.texts
            ],
            model="fake",
        )


class ScriptedLLM:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.prompts: list[str] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.call_count += 1
        self.prompts.append(req.prompt)
        if not self._responses:
            raise AssertionError("ScriptedLLM exhausted")
        return GenerateResponse(text=self._responses.pop(0), model=self.model)


@pytest.fixture
def customer_setup(tmp_path: Path) -> Iterator[tuple[DatabaseRegistry, SchemaIndex]]:
    db_path = tmp_path / "customers.sqlite"
    raw = sqlite3.connect(db_path)
    raw.execute(
        """
        CREATE TABLE Customer (
            CustomerId INTEGER PRIMARY KEY,
            Active INTEGER NOT NULL
        )
        """
    )
    raw.executemany(
        "INSERT INTO Customer (CustomerId, Active) VALUES (?, 1)",
        [(idx,) for idx in range(1, 5001)],
    )
    raw.commit()
    raw.close()

    spec = DatabaseSpec(id="crm", dialect="sqlite", url=sqlite_url_readonly(db_path))
    registry = DatabaseRegistry()
    registry.register(spec)

    intro_engine: Engine = spec.make_engine()
    try:
        client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
        index = SchemaIndex(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client)
        index.index_schema(to_chunks(introspect(intro_engine, sample_size=2), db_id="crm"))
        yield registry, index
    finally:
        intro_engine.dispose()
        gc.collect()


def test_grounded_critique_routes_to_repair(
    customer_setup: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = customer_setup
    too_many_rows_sql = json.dumps(
        {
            "sql": "SELECT CustomerId FROM Customer WHERE Active = 1",
            "tables_used": ["Customer"],
            "confidence": 0.6,
        }
    )
    sql_llm = ScriptedLLM([too_many_rows_sql, too_many_rows_sql])
    explain_llm = ScriptedLLM(["Query returned too many rows."])
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_llm,
            explain_provider=explain_llm,
            schema_index=index,
            registry=registry,
            schema_top_k=1,
            fewshot_top_k=0,
            fk_hops=0,
            enable_grounded_critique=True,
        )
    )

    state = cast(
        PipelineState,
        pipeline.invoke(
            {
                "question": "How many customers are active?",
                "db_id": "crm",
                "dialect": "sqlite",
                "repair_attempted": False,
                "verify_retry_on_empty": False,
                "trace": [],
            }
        ),
    )

    nodes_visited = [entry["node"] for entry in state["trace"]]
    assert "repair_once" in nodes_visited
    assert sql_llm.call_count == 2
    assert "The previous query returned 5000 rows" in state["last_error"]
    assert "question implies exactly 1 row" in state["last_error"]
