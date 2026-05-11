"""Unit tests for `nl_sql.schema_index.indexer.SchemaIndex`.

We use an in-memory chromadb client (`EphemeralClient`) and a deterministic
fake embedder so tests are hermetic — no Mistral calls, no temp files,
no Windows file-handle cleanup races.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import chromadb
import pytest

from nl_sql.llm.providers.base import EmbedRequest, EmbedResponse
from nl_sql.schema_index.chunker import SchemaChunk
from nl_sql.schema_index.indexer import FewShotExample, SchemaIndex


class FakeEmbedder:
    """Deterministic embedder: SHA1 of text, first 8 bytes scaled to [0, 1].

    Produces vectors that cluster identical / near-identical strings together
    while still being deterministic across runs. Sufficient for query
    plumbing tests; semantic recall tests live in `scripts/`.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.last_texts: list[str] = []

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        self.calls += 1
        self.last_texts = list(req.texts)
        vectors: list[list[float]] = []
        for text in req.texts:
            digest = hashlib.sha1(text.encode("utf-8")).digest()
            vectors.append([b / 255.0 for b in digest[:8]])
        return EmbedResponse(vectors=vectors, model="fake")


@pytest.fixture
def index(tmp_path: Path) -> SchemaIndex:
    """One-of-a-kind persistent client per test in `tmp_path`.

    `EphemeralClient` shares its underlying System across instances in the same
    process (default tenant+database), so two ephemeral clients in different
    tests would leak data between each other. PersistentClient keyed on a
    unique tmp_path is fully isolated.
    """
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return SchemaIndex(persist_dir=tmp_path / "chroma", embedder=FakeEmbedder(), client=client)


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


def test_index_schema_upserts_chunks(index: SchemaIndex) -> None:
    chunks = [
        _chunk("chinook", "Album", "Table: Album", fk_targets=("Artist",)),
        _chunk("chinook", "Artist", "Table: Artist"),
    ]
    n = index.index_schema(chunks)
    assert n == 2
    assert index.schema_collection.count() == 2


def test_index_schema_is_idempotent(index: SchemaIndex) -> None:
    chunks = [_chunk("chinook", "Album", "Table: Album")]
    index.index_schema(chunks)
    index.index_schema(chunks)  # re-indexing same id must not duplicate
    assert index.schema_collection.count() == 1


def test_index_schema_batches(tmp_path: Path) -> None:
    # Batch boundary: 5 chunks, batch=2 → expect 3 embed calls.
    embedder = FakeEmbedder()
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    idx = SchemaIndex(
        persist_dir=tmp_path / "chroma",
        embedder=embedder,
        client=client,
        embed_batch=2,
    )
    chunks = [_chunk("d", f"t{i}", f"Table t{i}") for i in range(5)]
    idx.index_schema(chunks)
    assert embedder.calls == 3
    assert idx.schema_collection.count() == 5


def test_query_schema_filters_by_db_id(index: SchemaIndex) -> None:
    index.index_schema(
        [
            _chunk("chinook", "Album", "Albums released by artists"),
            _chunk("chinook", "Artist", "Artists in the music store"),
            _chunk("bird_x", "Song", "Songs in BIRD database"),
        ]
    )
    hits = index.query_schema("artist albums", db_id="chinook", top_k=5)
    assert {h.table_name for h in hits} <= {"Album", "Artist"}
    assert all(h.db_id == "chinook" for h in hits)


def test_query_schema_returns_distance(index: SchemaIndex) -> None:
    index.index_schema([_chunk("d", "t", "hello world")])
    hits = index.query_schema("hello world", db_id="d", top_k=1)
    assert len(hits) == 1
    assert hits[0].distance >= 0.0


def test_index_fewshots_does_not_embed_sql(index: SchemaIndex) -> None:
    embedder = index._embedder  # type: ignore[attr-defined]
    examples = [
        FewShotExample(
            example_id="ex1",
            db_id="chinook",
            question="how many albums per artist",
            sql="SELECT artist, COUNT(*) FROM album GROUP BY artist",
            intent="aggregation",
        )
    ]
    n = index.index_fewshots(examples)
    assert n == 1
    assert embedder.last_texts == ["how many albums per artist"]  # type: ignore[attr-defined]
    assert index.fewshot_collection.count() == 1


def test_query_fewshots_returns_sql_in_metadata(index: SchemaIndex) -> None:
    index.index_fewshots(
        [
            FewShotExample(
                example_id="e1",
                db_id="chinook",
                question="albums per artist",
                sql="SELECT 1",
                intent="agg",
            )
        ]
    )
    hits = index.query_fewshots("albums per artist", db_id="chinook", top_k=1)
    assert len(hits) == 1
    assert hits[0].sql == "SELECT 1"
    assert hits[0].metadata.get("intent") == "agg"


def test_fk_graph_is_symmetric(index: SchemaIndex) -> None:
    index.index_schema(
        [
            _chunk("d", "Album", "Album", fk_targets=("Artist",)),
            _chunk("d", "Artist", "Artist", fk_targets=()),
            _chunk("d", "Track", "Track", fk_targets=("Album",)),
        ]
    )
    graph = index.fk_graph("d")
    assert "Artist" in graph["Album"]
    assert "Album" in graph["Artist"]  # back-edge synthesised
    assert "Album" in graph["Track"]
    assert "Track" in graph["Album"]  # back-edge from Track


def test_fk_graph_scopes_to_db_id(index: SchemaIndex) -> None:
    index.index_schema(
        [
            _chunk("a", "Foo", "", fk_targets=("Bar",)),
            _chunk("b", "Foo", "", fk_targets=("Baz",)),
        ]
    )
    g_a = index.fk_graph("a")
    assert g_a["Foo"] == {"Bar"}
    assert "Baz" not in g_a.get("Foo", set())


def test_empty_index_returns_no_hits(index: SchemaIndex) -> None:
    assert index.query_schema("anything", db_id="x", top_k=5) == []
    assert index.query_fewshots("anything", db_id="x", top_k=5) == []
    assert index.fk_graph("x") == {}


def test_query_fewshots_cross_db_pulls_from_any_database(index: SchemaIndex) -> None:
    """BIRD train and dev partition by db_id. Cross-db retrieval must skip
    the where filter so a dev question can still find the most similar
    train Q→SQL pair (different db_id).
    """
    index.index_fewshots(
        [
            FewShotExample(
                example_id="train_1",
                db_id="video_games",
                question="how many publishers shipped 5 games or fewer",
                sql="SELECT 1",
                intent="agg",
            ),
            FewShotExample(
                example_id="train_2",
                db_id="retail",
                question="weather in tokyo",
                sql="SELECT 2",
                intent="other",
            ),
        ]
    )
    same_db = index.query_fewshots(
        "how many publishers shipped few games",
        db_id="california_schools",
        top_k=2,
    )
    assert same_db == []  # no fewshot exists for california_schools

    cross = index.query_fewshots(
        "how many publishers shipped few games",
        db_id="california_schools",
        top_k=2,
        cross_db=True,
    )
    assert len(cross) >= 1
    assert {h.example_id for h in cross} <= {"train_1", "train_2"}
