"""Unit tests for DAIL-style schema-masked few-shot selection (A2 / 2a)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import chromadb
import pytest

from nl_sql.llm.providers.base import EmbedRequest, EmbedResponse
from nl_sql.schema_index.chunker import SchemaChunk
from nl_sql.schema_index.fewshot_selection import (
    MASK_TOKEN,
    collect_schema_tokens,
    fewshot_query_text,
    mask_schema_tokens,
    parse_column_names_from_chunk,
)
from nl_sql.schema_index.indexer import FewShotExample, SchemaIndex
from nl_sql.schema_index.retriever import retrieve_context


class FakeEmbedder:
    def embed(self, req: EmbedRequest) -> EmbedResponse:
        vectors: list[list[float]] = []
        for text in req.texts:
            digest = hashlib.sha1(text.encode("utf-8")).digest()
            vectors.append([b / 255.0 for b in digest[:8]])
        return EmbedResponse(vectors=vectors, model="fake")


def test_parse_column_names_from_chunk() -> None:
    text = (
        "Table: schools (rows=10)\n"
        "Columns:\n"
        "  - District Name: TEXT [NULL] | nulls=0 (0%), distinct=3 | samples: a\n"
        "  - CDSCode: TEXT [NOT NULL] | nulls=0 (0%), distinct=10\n"
        "Foreign keys:\n"
        "  - (CDSCode) -> frpm(CDSCode)\n"
    )
    cols = parse_column_names_from_chunk(text)
    assert "District Name" in cols
    assert "CDSCode" in cols
    # FK lines must not be parsed as columns.
    assert " (CDSCode) -> frpm(CDSCode)" not in cols


def test_mask_schema_tokens_replaces_table_and_column() -> None:
    q = "How many schools are in the District Name Riverside?"
    masked = mask_schema_tokens(q, ["schools", "District Name", "CDSCode"])
    assert MASK_TOKEN in masked
    assert "schools" not in masked.lower()
    assert "District Name" not in masked
    # Literal value stays.
    assert "Riverside" in masked


def test_mask_schema_tokens_underscore_space_variant() -> None:
    q = "Filter by District Name equals X"
    masked = mask_schema_tokens(q, ["District_Name"])
    assert "District Name" not in masked
    assert MASK_TOKEN in masked


def test_mask_skips_generic_short_identifiers() -> None:
    q = "What is the name and year of each record?"
    masked = mask_schema_tokens(q, ["name", "year", "id"])
    # Generics must not shred ordinary English.
    assert masked == q


def test_fewshot_query_text_modes() -> None:
    q = "List all Tracks on Album 1"
    tokens = ["Track", "Album", "Tracks"]
    assert fewshot_query_text(q, selection="dense", schema_tokens=tokens) == q
    dail = fewshot_query_text(q, selection="dail", schema_tokens=tokens)
    assert dail != q
    assert MASK_TOKEN in dail


def _chunk(db_id: str, table: str, text: str) -> SchemaChunk:
    return SchemaChunk(
        chunk_id=f"{db_id}::{table}",
        db_id=db_id,
        table_name=table,
        text=text,
        fk_targets=(),
        metadata={
            "db_id": db_id,
            "table_name": table,
            "row_count": 10,
            "column_count": 2,
            "primary_key": "id",
            "fk_targets": "",
            "business_hints": "",
        },
    )


@pytest.fixture
def dail_index(tmp_path: Path) -> SchemaIndex:
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    idx = SchemaIndex(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client)
    idx.index_schema(
        [
            _chunk(
                "california_schools",
                "schools",
                "Table: schools (rows=10)\nColumns:\n  - District Name: TEXT [NULL]\n  - CDSCode: TEXT [NOT NULL]",
            ),
        ]
    )
    idx.index_fewshots(
        [
            FewShotExample(
                example_id="fs1",
                db_id="other_db",
                question="How many schools are in the District Name X?",
                sql="SELECT COUNT(*) FROM schools",
            ),
            FewShotExample(
                example_id="fs2",
                db_id="other_db",
                question="What is the average score for each year?",
                sql="SELECT year, AVG(score) FROM scores GROUP BY year",
            ),
        ]
    )
    return idx


def test_collect_schema_tokens_from_index(dail_index: SchemaIndex) -> None:
    tokens = collect_schema_tokens(dail_index, "california_schools")
    assert "schools" in tokens
    assert "District Name" in tokens
    assert "CDSCode" in tokens


def test_retrieve_context_dail_notes_and_still_returns_fewshots(
    dail_index: SchemaIndex,
) -> None:
    question = "How many schools are in the District Name Riverside?"
    dense = retrieve_context(
        dail_index,
        question,
        db_id="california_schools",
        schema_top_k=1,
        fewshot_top_k=2,
        cross_db_fewshot=True,
        fewshot_selection="dense",
    )
    dail = retrieve_context(
        dail_index,
        question,
        db_id="california_schools",
        schema_top_k=1,
        fewshot_top_k=2,
        cross_db_fewshot=True,
        fewshot_selection="dail",
    )
    assert len(dail.fewshots) == 2
    assert any("fewshot_selection=dail" in n for n in dail.notes)
    # Fake embedder: masked query text ≠ raw → hit order/ids can differ.
    dense_ids = [h.example_id for h in dense.fewshots]
    dail_ids = [h.example_id for h in dail.fewshots]
    # Both modes must return the pool; at least the embedded query path ran
    # (dail note present). Ordering may or may not flip on this tiny pool.
    assert set(dense_ids) == set(dail_ids) == {"fs1", "fs2"}


def test_pipeline_config_default_is_dense() -> None:
    from nl_sql.agent.graph import PipelineConfig

    # Defaults must not change product path without an explicit CLI flag.
    # Constructing without providers fails — only inspect the field default.
    field = next(
        f for f in PipelineConfig.__dataclass_fields__.values() if f.name == "fewshot_selection"
    )
    assert field.default == "dense"
