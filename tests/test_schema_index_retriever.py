"""Unit tests for `nl_sql.schema_index.retriever.retrieve_context`.

We use a `PersistentClient(tmp_path)` for full isolation between tests
(see test_schema_index_indexer.py for rationale) and the same deterministic
fake embedder. Tests cover dense top-k, FK-graph traversal, table_budget
truncation, and absent-db notes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import chromadb
import pytest

from nl_sql.llm.providers.base import EmbedRequest, EmbedResponse
from nl_sql.schema_index.chunker import SchemaChunk
from nl_sql.schema_index.indexer import SchemaIndex
from nl_sql.schema_index.retriever import retrieve_context


class FakeEmbedder:
    def embed(self, req: EmbedRequest) -> EmbedResponse:
        vectors: list[list[float]] = []
        for text in req.texts:
            digest = hashlib.sha1(text.encode("utf-8")).digest()
            vectors.append([b / 255.0 for b in digest[:8]])
        return EmbedResponse(vectors=vectors, model="fake")


def _chunk(db_id: str, table: str, text: str, fk_targets: tuple[str, ...] = ()) -> SchemaChunk:
    return SchemaChunk(
        chunk_id=f"{db_id}::{table}",
        db_id=db_id,
        table_name=table,
        text=text,
        fk_targets=fk_targets,
        metadata={
            "db_id": db_id,
            "table_name": table,
            "row_count": 100,
            "column_count": 3,
            "primary_key": "id",
            "fk_targets": ",".join(fk_targets),
            "business_hints": "",
        },
    )


@pytest.fixture
def populated_index(tmp_path: Path) -> SchemaIndex:
    """Tiny graph: Album↔Artist, Album↔Track, Track↔Genre.

    Disconnected island Foo so we can test FK traversal does not bridge dbs.
    """
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    idx = SchemaIndex(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client)
    idx.index_schema(
        [
            _chunk("d", "Artist", "artists who record music", fk_targets=()),
            _chunk("d", "Album", "albums released by artists", fk_targets=("Artist",)),
            _chunk("d", "Track", "tracks on albums", fk_targets=("Album", "Genre")),
            _chunk("d", "Genre", "music genre", fk_targets=()),
            _chunk("d", "Foo", "unrelated", fk_targets=()),
        ]
    )
    return idx


def test_retrieve_context_returns_hits_and_neighbours(populated_index: SchemaIndex) -> None:
    bundle = retrieve_context(
        populated_index,
        "music tracks released by artists",
        db_id="d",
        schema_top_k=2,
        fk_hops=1,
        table_budget=8,
        fewshot_top_k=0,
    )
    assert bundle.db_id == "d"
    assert bundle.question == "music tracks released by artists"
    assert len(bundle.schema_hits) == 2
    # Neighbours should never duplicate seed tables
    seed = {h.table_name for h in bundle.schema_hits}
    extra = {h.table_name for h in bundle.fk_neighbours}
    assert seed.isdisjoint(extra)


def test_retrieve_context_truncates_to_table_budget(populated_index: SchemaIndex) -> None:
    # Question identical to the Track chunk text → fake-embedder lands seed
    # on Track deterministically. FK 2-hop: Track→{Album, Genre}, then
    # Album→Artist. 3 candidate neighbours, budget=2 leaves 1 slot, so 2
    # are dropped and the bundle reports truncated.
    bundle = retrieve_context(
        populated_index,
        "tracks on albums",
        db_id="d",
        schema_top_k=1,
        fk_hops=2,
        table_budget=2,
        fewshot_top_k=0,
    )
    assert len(bundle.schema_hits) == 1
    assert bundle.schema_hits[0].table_name == "Track"
    assert len(bundle.fk_neighbours) == 1
    assert bundle.truncated is True
    assert any("table_budget" in note for note in bundle.notes)


def test_retrieve_context_no_traversal_when_fk_hops_zero(populated_index: SchemaIndex) -> None:
    bundle = retrieve_context(
        populated_index,
        "music",
        db_id="d",
        schema_top_k=2,
        fk_hops=0,
        table_budget=10,
        fewshot_top_k=0,
    )
    assert bundle.fk_neighbours == []
    assert bundle.truncated is False


def test_retrieve_context_marks_unknown_db(tmp_path: Path) -> None:
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    idx = SchemaIndex(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client)
    bundle = retrieve_context(idx, "anything", db_id="missing", fewshot_top_k=0)
    assert bundle.schema_hits == []
    assert bundle.fk_neighbours == []
    assert any("missing" in note for note in bundle.notes)


def test_all_tables_preserves_order(populated_index: SchemaIndex) -> None:
    bundle = retrieve_context(
        populated_index,
        "music",
        db_id="d",
        schema_top_k=2,
        fk_hops=1,
        table_budget=8,
        fewshot_top_k=0,
    )
    listed = bundle.all_tables
    seed = [h.table_name for h in bundle.schema_hits]
    extra = [h.table_name for h in bundle.fk_neighbours]
    assert listed[: len(seed)] == seed
    assert listed[len(seed) :] == extra


def test_retrieve_context_skips_extended_samples_without_engine(
    populated_index: SchemaIndex,
) -> None:
    bundle = retrieve_context(
        populated_index,
        "music",
        db_id="d",
        schema_top_k=2,
        fk_hops=1,
        table_budget=8,
        fewshot_top_k=0,
        engine=None,
        extended_sample_size=5,
    )
    assert bundle.extended_samples is None


def test_retrieve_context_skips_extended_samples_when_size_not_greater(
    populated_index: SchemaIndex,
) -> None:
    import sqlite3

    from sqlalchemy import create_engine

    raw = sqlite3.connect(":memory:")
    try:
        eng = create_engine("sqlite://", creator=lambda: raw, future=True)
        bundle = retrieve_context(
            populated_index,
            "music",
            db_id="d",
            schema_top_k=2,
            fk_hops=1,
            table_budget=8,
            fewshot_top_k=0,
            engine=eng,
            primary_sample_size=5,
            extended_sample_size=3,
        )
        assert bundle.extended_samples is None
    finally:
        raw.close()
