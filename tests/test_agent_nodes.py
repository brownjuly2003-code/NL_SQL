"""Per-node behaviour tests for the LangGraph pipeline.

We mock out only what crosses the LLM/DB boundary — everything else (schema
index, registry, validate_sql, execute_validated, pick_format) runs for real
against in-memory SQLite. Keeps the tests close to integration without
needing a live API key.
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
from nl_sql.db.connection import DatabaseSpec, sqlite_url_readonly
from nl_sql.db.registry import DatabaseRegistry
from nl_sql.execution.errors import ExecutionErrorKind
from nl_sql.llm.providers.base import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
)
from nl_sql.render.formats import Scalar, Sentence, Table
from nl_sql.schema_index.chunker import to_chunks
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.introspector import introspect


class FakeEmbedder:
    def embed(self, req: EmbedRequest) -> EmbedResponse:
        # Length-8 "embedding" — every text gets a vector based on its hash;
        # adequate for plumbing tests, irrelevant to semantic recall.
        import hashlib

        vectors = [
            [b / 255.0 for b in hashlib.sha1(t.encode("utf-8")).digest()[:8]] for t in req.texts
        ]
        return EmbedResponse(vectors=vectors, model="fake")


class ScriptedLLM:
    """Returns canned responses in order, raising if exhausted.

    Useful when a test wants to assert the second LLM call (the repair) sees
    a different prompt. We stash every call in `prompts` for inspection.
    """

    name = "scripted"
    model = "scripted-1"

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        self.prompts.append(req.prompt)
        if not self._responses:
            raise AssertionError("ScriptedLLM exhausted")
        text = self._responses.pop(0)
        return GenerateResponse(text=text, model=self.model)


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def chinook_db(tmp_path: Path) -> Iterator[tuple[DatabaseSpec, Engine]]:
    db_path = tmp_path / "chinook_mini.sqlite"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE Artist (
            ArtistId INTEGER PRIMARY KEY,
            Name TEXT NOT NULL
        );
        CREATE TABLE Album (
            AlbumId INTEGER PRIMARY KEY,
            Title TEXT NOT NULL,
            ArtistId INTEGER NOT NULL,
            FOREIGN KEY (ArtistId) REFERENCES Artist(ArtistId)
        );
        INSERT INTO Artist VALUES (1, 'AC/DC'), (2, 'Aerosmith'), (3, 'Accept');
        INSERT INTO Album VALUES (10, 'Back in Black', 1), (11, 'Highway to Hell', 1), (12, 'Pump', 2);
        """
    )
    raw.commit()
    raw.close()

    spec = DatabaseSpec(
        id="chinook_mini",
        dialect="sqlite",
        url=sqlite_url_readonly(db_path),
    )
    eng = spec.make_engine()
    try:
        yield spec, eng
    finally:
        # The execute_node closure caches its own engine — force GC so that
        # SQLite raw connections close before pytest's tmp_path cleanup runs;
        # otherwise filterwarnings=error trips on ResourceWarning.
        eng.dispose()
        gc.collect()


@pytest.fixture
def populated_index(tmp_path: Path, chinook_db: tuple[DatabaseSpec, Engine]) -> SchemaIndex:
    spec, eng = chinook_db
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    idx = SchemaIndex(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client)
    tables = introspect(eng, sample_size=2)
    idx.index_schema(to_chunks(tables, db_id=spec.id))
    return idx


@pytest.fixture
def registry_one_db(chinook_db: tuple[DatabaseSpec, Engine]) -> DatabaseRegistry:
    spec, _ = chinook_db
    reg = DatabaseRegistry()
    reg.register(spec)
    return reg


# ----------------------------------------------------------- context_builder


def test_context_builder_populates_bundle(populated_index: SchemaIndex) -> None:
    node = make_context_builder_node(
        populated_index, schema_top_k=2, fewshot_top_k=0, fk_hops=1, table_budget=8
    )
    state: PipelineState = {"question": "albums released by AC/DC", "db_id": "chinook_mini"}
    out = node(state)
    assert out["context"] is not None
    bundle = out["context"]
    assert bundle.db_id == "chinook_mini"
    assert any(h.table_name in {"Album", "Artist"} for h in bundle.schema_hits)
    assert any(t["node"] == "context_builder" for t in out["trace"])


def test_context_builder_skips_when_inputs_missing(populated_index: SchemaIndex) -> None:
    node = make_context_builder_node(populated_index, fewshot_top_k=0)
    out = node({"question": "", "db_id": ""})
    assert out["context"] is None


def test_context_builder_attaches_extended_samples_when_registry_set(
    populated_index: SchemaIndex,
    registry_one_db: DatabaseRegistry,
) -> None:
    """Sample mixture path: extended_sample_size > primary_sample_size +
    registry provided → bundle.extended_samples is populated for retrieved
    tables, and the trace records which tables got the appendix."""
    node = make_context_builder_node(
        populated_index,
        schema_top_k=2,
        fewshot_top_k=0,
        fk_hops=1,
        table_budget=8,
        registry=registry_one_db,
        primary_sample_size=2,
        extended_sample_size=5,
    )
    out = node({"question": "list AC/DC albums", "db_id": "chinook_mini"})
    bundle = out["context"]
    assert bundle is not None
    assert bundle.extended_samples is not None
    # Both retrieved tables should have at least one column with tail samples
    # (Artist has 3 rows; ArtistId is the PK with 3 distinct values).
    assert any(cols for cols in bundle.extended_samples.values())
    trace_entry = next(t for t in out["trace"] if t["node"] == "context_builder")
    assert "extended_sample_tables" in trace_entry


def test_context_builder_no_extended_samples_when_disabled(
    populated_index: SchemaIndex,
    registry_one_db: DatabaseRegistry,
) -> None:
    """Default path (extended_sample_size=0) → bundle.extended_samples is
    None, no DB introspection happens."""
    node = make_context_builder_node(
        populated_index,
        schema_top_k=2,
        fewshot_top_k=0,
        fk_hops=1,
        registry=registry_one_db,
    )
    out = node({"question": "albums", "db_id": "chinook_mini"})
    bundle = out["context"]
    assert bundle is not None
    assert bundle.extended_samples is None


# -------------------------------------------------------------- generate_sql


def test_generate_sql_parses_provider_response(populated_index: SchemaIndex) -> None:
    cb = make_context_builder_node(populated_index, schema_top_k=2, fewshot_top_k=0, fk_hops=0)
    state: PipelineState = {"question": "list AC/DC albums", "db_id": "chinook_mini"}
    state = {**state, **cb(state)}

    payload = json.dumps(
        {
            "sql": "SELECT Title FROM Album WHERE ArtistId = 1",
            "rationale": "filter Album by Artist 1",
            "tables_used": ["Album"],
            "confidence": 0.85,
        }
    )
    llm = ScriptedLLM([payload])
    gen = make_generate_sql_node(llm)
    out = gen(state)

    generated = out["generated"]
    assert isinstance(generated, GenerateSQLOutput)
    assert generated.sql == "SELECT Title FROM Album WHERE ArtistId = 1"
    assert generated.tables_used == ("Album",)
    assert generated.confidence == 0.85
    # Ensure the rendered prompt actually carried the schema body.
    assert "Album" in llm.prompts[0]


# ------------------------------------------------------------------ validate


def test_validate_passes_clean_select() -> None:
    node = make_validate_node()
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="SELECT 1"),
        "dialect": "sqlite",
    }
    out = node(state)
    assert out["outcome"].error_kind is None
    assert out["outcome"].validation.ok


def test_validate_flags_dml_for_repair() -> None:
    node = make_validate_node()
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="DELETE FROM Album"),
        "dialect": "sqlite",
    }
    out = node(state)
    assert out["error_kind"] == ExecutionErrorKind.INVALID_SQL
    assert out["last_error"]


def test_validate_handles_no_sql_case() -> None:
    node = make_validate_node()
    out = node({"generated": GenerateSQLOutput(sql=""), "dialect": "sqlite"})
    assert out["error_kind"] == ExecutionErrorKind.INVALID_SQL
    assert "no SQL" in out["last_error"]


# --------------------------------------------------------------- repair_once


def test_repair_once_uses_error_context_in_prompt() -> None:
    llm = ScriptedLLM([json.dumps({"sql": "SELECT 2", "confidence": 0.5})])
    node = make_repair_once_node(llm)
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="SELECT * FORM Album"),  # typo
        "last_error": "syntax error near 'FORM'",
        "dialect": "sqlite",
        "question": "list albums",
    }
    out = node(state)
    assert out["repair_attempted"] is True
    assert out["generated"].sql == "SELECT 2"
    assert "FORM Album" in llm.prompts[0]
    assert "syntax error near 'FORM'" in llm.prompts[0]


# -------------------------------------------------------------------- execute


def test_execute_runs_validated_select(registry_one_db: DatabaseRegistry) -> None:
    node = make_execute_node(registry=registry_one_db)
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="SELECT COUNT(*) FROM Album"),
        "db_id": "chinook_mini",
        "dialect": "sqlite",
    }
    out = node(state)
    assert out["outcome"].ok
    assert out["outcome"].result is not None
    assert out["outcome"].result.rows == [(3,)]


def test_execute_reports_runtime_error(registry_one_db: DatabaseRegistry) -> None:
    node = make_execute_node(registry=registry_one_db)
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="SELECT * FROM no_such_table"),
        "db_id": "chinook_mini",
        "dialect": "sqlite",
    }
    out = node(state)
    assert out["error_kind"] == ExecutionErrorKind.EXECUTION_FAILED
    assert "no_such_table" in out["last_error"]


# --------------------------------------------------------------------- format


def test_format_node_picks_scalar_for_single_value(
    registry_one_db: DatabaseRegistry,
) -> None:
    exec_node = make_execute_node(registry=registry_one_db)
    fmt_node = make_format_node()
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="SELECT COUNT(*) FROM Album"),
        "db_id": "chinook_mini",
        "dialect": "sqlite",
    }
    state = {**state, **exec_node(state)}
    out = fmt_node(state)
    assert isinstance(out["output_format"], Scalar)


def test_format_node_falls_back_to_sentence_on_no_result() -> None:
    fmt_node = make_format_node()
    out = fmt_node({"outcome": None, "error_message": "boom"})
    assert isinstance(out["output_format"], Sentence)
    assert "boom" in out["output_format"].text


def test_format_node_table_for_three_col_result(
    registry_one_db: DatabaseRegistry,
) -> None:
    # 3 cols → picker has no chart heuristic, falls through to Table.
    exec_node = make_execute_node(registry=registry_one_db)
    fmt_node = make_format_node()
    state: PipelineState = {
        "generated": GenerateSQLOutput(
            sql="SELECT AlbumId, Title, ArtistId FROM Album ORDER BY AlbumId",
        ),
        "db_id": "chinook_mini",
        "dialect": "sqlite",
    }
    state = {**state, **exec_node(state)}
    out = fmt_node(state)
    assert isinstance(out["output_format"], Table)


# ---------------------------------------------------------------- explain_trace


def test_explain_trace_uses_provider_caption(registry_one_db: DatabaseRegistry) -> None:
    exec_node = make_execute_node(registry=registry_one_db)
    explain_llm = ScriptedLLM(["The store has 3 albums."])
    explain_node = make_explain_trace_node(explain_llm)
    state: PipelineState = {
        "generated": GenerateSQLOutput(sql="SELECT COUNT(*) FROM Album"),
        "db_id": "chinook_mini",
        "dialect": "sqlite",
        "question": "How many albums?",
    }
    state = {**state, **exec_node(state)}
    out = explain_node(state)
    assert out["caption"] == "The store has 3 albums."
    assert "How many albums?" in explain_llm.prompts[0]


def test_explain_trace_falls_back_to_error_message_when_no_result() -> None:
    explain_node = make_explain_trace_node(ScriptedLLM([]))
    out = explain_node({"outcome": None, "error_message": "bad"})
    assert "bad" in out["caption"]
