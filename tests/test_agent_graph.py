"""End-to-end graph tests with fakes for both LLMs.

Three flows exercised:
1. Happy path — generate_sql returns valid SQL, executes, formats, captions.
2. Repair path — first generate is invalid (DML), validate fails, repair_once
   fires exactly once, validate passes, execute succeeds, format/caption run.
3. Repair-failed path — both attempts fail, graph terminates via the
   deterministic_format → explain_trace fall-through with an error caption.
"""

from __future__ import annotations

import gc
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import chromadb
import pytest
from sqlalchemy.engine import Engine

from nl_sql.agent import PipelineConfig, build_pipeline, run_pipeline
from nl_sql.db.connection import DatabaseSpec, sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.llm.providers.base import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
)
from nl_sql.render.formats import Scalar
from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.introspector import introspect


class FakeEmbedder:
    def embed(self, req: EmbedRequest) -> EmbedResponse:
        import hashlib

        return EmbedResponse(
            vectors=[
                [b / 255.0 for b in hashlib.sha1(t.encode("utf-8")).digest()[:8]]
                for t in req.texts
            ],
            model="fake",
        )


class ScriptedLLM:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.call_count += 1
        if not self._responses:
            return GenerateResponse(text="(no more scripted responses)", model=self.model)
        return GenerateResponse(text=self._responses.pop(0), model=self.model)


@pytest.fixture
def chinook_setup(tmp_path: Path) -> Iterator[tuple[DatabaseRegistry, SchemaIndex]]:
    db_path = tmp_path / "chinook.sqlite"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE Artist (ArtistId INTEGER PRIMARY KEY, Name TEXT NOT NULL);
        CREATE TABLE Album (
            AlbumId INTEGER PRIMARY KEY,
            Title TEXT NOT NULL,
            ArtistId INTEGER NOT NULL,
            FOREIGN KEY (ArtistId) REFERENCES Artist(ArtistId)
        );
        INSERT INTO Artist VALUES (1, 'AC/DC'), (2, 'Aerosmith');
        INSERT INTO Album VALUES (10, 'Back in Black', 1), (11, 'Highway to Hell', 1), (12, 'Pump', 2);
        """
    )
    raw.commit()
    raw.close()

    spec = DatabaseSpec(id="chinook", dialect="sqlite", url=sqlite_url_readonly(db_path))
    registry = DatabaseRegistry()
    registry.register(spec)

    intro_engine: Engine = spec.make_engine()
    try:
        client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
        index = SchemaIndex(
            persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client
        )
        index.index_schema(to_chunks(introspect(intro_engine, sample_size=2), db_id="chinook"))
        yield registry, index
    finally:
        intro_engine.dispose()
        gc.collect()


def test_graph_happy_path(chinook_setup: tuple[DatabaseRegistry, SchemaIndex]) -> None:
    registry, index = chinook_setup
    sql_llm = ScriptedLLM(
        [
            json.dumps(
                {
                    "sql": "SELECT COUNT(*) FROM Album",
                    "rationale": "count rows",
                    "tables_used": ["Album"],
                    "confidence": 0.9,
                }
            )
        ]
    )
    explain_llm = ScriptedLLM(["The store has 3 albums."])
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_llm,
            explain_provider=explain_llm,
            schema_index=index,
            registry=registry,
            schema_top_k=2,
            fewshot_top_k=0,
            fk_hops=0,
        )
    )
    result = run_pipeline(pipeline, question="how many albums?", db_id="chinook")

    assert result.ok
    assert result.sql == "SELECT COUNT(*) FROM Album"
    assert result.repair_attempted is False
    assert isinstance(result.output_format, Scalar)
    assert result.output_format.value == 3
    assert result.caption == "The store has 3 albums."
    assert sql_llm.call_count == 1
    nodes_visited = [t["node"] for t in result.trace]
    assert nodes_visited == [
        "context_builder",
        "generate_sql",
        "validate",
        "execute",
        "deterministic_format",
        "explain_trace",
    ]


def test_graph_repair_recovers_from_initial_failure(
    chinook_setup: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = chinook_setup
    bad_sql = json.dumps({"sql": "DELETE FROM Album", "confidence": 0.1})
    good_sql = json.dumps(
        {"sql": "SELECT COUNT(*) FROM Album", "tables_used": ["Album"], "confidence": 0.85}
    )
    sql_llm = ScriptedLLM([bad_sql, good_sql])
    explain_llm = ScriptedLLM(["3 albums."])
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_llm,
            explain_provider=explain_llm,
            schema_index=index,
            registry=registry,
            schema_top_k=2,
            fewshot_top_k=0,
            fk_hops=0,
        )
    )
    result = run_pipeline(pipeline, question="album count?", db_id="chinook")

    assert result.ok
    assert result.sql == "SELECT COUNT(*) FROM Album"
    assert result.repair_attempted is True
    assert sql_llm.call_count == 2
    nodes_visited = [t["node"] for t in result.trace]
    assert "repair_once" in nodes_visited
    assert nodes_visited.count("validate") == 2
    assert nodes_visited.count("execute") == 1


def test_graph_terminates_when_repair_also_fails(
    chinook_setup: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = chinook_setup
    bad_sql_a = json.dumps({"sql": "DELETE FROM Album", "confidence": 0.1})
    bad_sql_b = json.dumps({"sql": "UPDATE Album SET Title='x'", "confidence": 0.1})
    sql_llm = ScriptedLLM([bad_sql_a, bad_sql_b])
    explain_llm = ScriptedLLM(["fallback caption"])
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_llm,
            explain_provider=explain_llm,
            schema_index=index,
            registry=registry,
            schema_top_k=2,
            fewshot_top_k=0,
            fk_hops=0,
        )
    )
    result = run_pipeline(pipeline, question="bad question", db_id="chinook")

    assert not result.ok
    assert result.error_kind == ExecutionErrorKind.INVALID_SQL
    assert result.repair_attempted is True
    assert sql_llm.call_count == 2  # exactly one repair, no third attempt
    # explain still runs — the caption comes from the LLM, no live data
    # was available, and the caption fallback path uses the error message.
    assert result.caption  # never empty


def test_graph_passes_empty_result_through_format(
    chinook_setup: tuple[DatabaseRegistry, SchemaIndex],
) -> None:
    registry, index = chinook_setup
    empty_sql = json.dumps(
        {"sql": "SELECT * FROM Album WHERE 1=0", "tables_used": ["Album"], "confidence": 0.7}
    )
    sql_llm = ScriptedLLM([empty_sql])
    explain_llm = ScriptedLLM(["Query returned no rows."])
    pipeline = build_pipeline(
        PipelineConfig(
            sql_provider=sql_llm,
            explain_provider=explain_llm,
            schema_index=index,
            registry=registry,
            schema_top_k=2,
            fewshot_top_k=0,
            fk_hops=0,
        )
    )
    result = run_pipeline(pipeline, question="impossible filter", db_id="chinook")

    assert result.error_kind == ExecutionErrorKind.EMPTY_RESULT
    assert result.repair_attempted is False  # empty is NOT a retry trigger
    assert sql_llm.call_count == 1
