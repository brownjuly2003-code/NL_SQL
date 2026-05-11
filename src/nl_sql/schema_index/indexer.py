"""Persist schema chunks + few-shot Q/SQL pairs into Chroma.

Two collections per arch v2 §4:
- ``schema_chunks``: one record per (db, table). ``text`` is the rendered
  table card from `chunker.to_chunks`; embedded vector comes from the
  injected `EmbeddingProvider` (Mistral in production).
- ``fewshot_qsql``: question text is the embedded body; SQL + db_id + intent
  ride along as metadata (NEVER embedded — keeps the retrieval space focused
  on intent, not on syntactic SQL similarity).

FK graph is **not** a Chroma collection. It's reconstructed in memory from
the schema chunks' ``fk_targets`` metadata at retrieve time (see
`SchemaIndex.fk_graph`). Per docs/02_architecture_v2.md §4, this is a
deliberate cut: dense retrieval on FK edges is bookkeeping, not semantics.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from nl_sql.llm.providers.base import EmbedRequest
from nl_sql.schema_index.chunker import SchemaChunk

if TYPE_CHECKING:
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection

SCHEMA_COLLECTION = "schema_chunks"
FEWSHOT_COLLECTION = "fewshot_qsql"


@dataclass(frozen=True, slots=True)
class FewShotExample:
    """One Q→SQL training pair. Sourced from BIRD train split, never dev/test
    (see `03_eval_methodology.md` §5 — leakage prevention).
    """

    example_id: str
    db_id: str
    question: str
    sql: str
    intent: str = ""  # short hint, e.g. "aggregation by year"


@runtime_checkable
class _Embedder(Protocol):
    """Minimal slice of `EmbeddingProvider` we need here, named locally so the
    indexer doesn't pull in the OpenAI client transitively at type-check time.
    """

    def embed(self, req: EmbedRequest) -> Any: ...  # returns object with .vectors


class SchemaIndex:
    """Owns a Chroma persistent client + a thread of two collections.

    Single-writer: the indexer assumes one process at a time. Concurrent
    `index_schema` calls on the same db_id will not corrupt data (Chroma
    upserts are per-id), but vector dimensionality is enforced by the first
    insert into a collection — embedder swaps require wiping the collection.
    """

    def __init__(
        self,
        persist_dir: Path | str,
        embedder: _Embedder,
        *,
        client: ClientAPI | None = None,
        embed_batch: int = 16,
    ) -> None:
        self._persist_dir = Path(persist_dir)
        self._embedder = embedder
        self._embed_batch = embed_batch
        self._client = client or self._build_default_client(self._persist_dir)
        self._schema = self._client.get_or_create_collection(name=SCHEMA_COLLECTION)
        self._fewshot = self._client.get_or_create_collection(name=FEWSHOT_COLLECTION)

    @staticmethod
    def _build_default_client(persist_dir: Path) -> ClientAPI:
        import chromadb

        persist_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(persist_dir))

    @property
    def schema_collection(self) -> Collection:
        return self._schema

    @property
    def fewshot_collection(self) -> Collection:
        return self._fewshot

    def index_schema(self, chunks: list[SchemaChunk]) -> int:
        """Embed and upsert one schema chunk per table. Returns chunk count."""
        if not chunks:
            return 0
        for batch in _batched(chunks, self._embed_batch):
            texts = [c.text for c in batch]
            vectors = self._embedder.embed(EmbedRequest(texts=texts)).vectors
            self._schema.upsert(
                ids=[c.chunk_id for c in batch],
                documents=texts,
                embeddings=vectors,
                metadatas=[dict(c.metadata) for c in batch],
            )
        return len(chunks)

    def index_fewshots(self, examples: list[FewShotExample]) -> int:
        """Embed each Q (NOT the SQL) and upsert with SQL/intent in metadata."""
        if not examples:
            return 0
        for batch in _batched(examples, self._embed_batch):
            texts = [ex.question for ex in batch]
            vectors = self._embedder.embed(EmbedRequest(texts=texts)).vectors
            self._fewshot.upsert(
                ids=[ex.example_id for ex in batch],
                documents=texts,
                embeddings=vectors,
                metadatas=[
                    {
                        "db_id": ex.db_id,
                        "sql": ex.sql,
                        "intent": ex.intent,
                    }
                    for ex in batch
                ],
            )
        return len(examples)

    def query_schema(
        self,
        question: str,
        *,
        db_id: str,
        top_k: int = 5,
    ) -> list[SchemaQueryHit]:
        """Dense top-k over `schema_chunks` filtered to a single db_id."""
        qvec = self._embed_one(question)
        result = self._schema.query(
            query_embeddings=cast(Any, [qvec]),
            n_results=top_k,
            where={"db_id": db_id},
        )
        return cast(
            list[SchemaQueryHit],
            _hits_from_query(cast(Mapping[str, Any], result), hit_cls=SchemaQueryHit),
        )

    def query_fewshots(
        self,
        question: str,
        *,
        db_id: str,
        top_k: int = 3,
        cross_db: bool = False,
    ) -> list[FewShotHit]:
        """Dense top-k over `fewshot_qsql`.

        Default (`cross_db=False`) restricts retrieval to the same `db_id`.
        That works when fewshot pool and test pool share schemas. BIRD's
        train and dev splits, however, partition by db_id (zero overlap) —
        same-db retrieval would return zero hits. `cross_db=True` drops the
        filter so the LLM sees Q→SQL patterns from any train db, which is
        the standard cross-domain fewshot setup in NL-SQL literature.
        """
        qvec = self._embed_one(question)
        query_kwargs: dict[str, Any] = {
            "query_embeddings": cast(Any, [qvec]),
            "n_results": top_k,
        }
        if not cross_db:
            query_kwargs["where"] = {"db_id": db_id}
        result = self._fewshot.query(**query_kwargs)
        return cast(
            list[FewShotHit],
            _hits_from_query(cast(Mapping[str, Any], result), hit_cls=FewShotHit),
        )

    def fk_graph(self, db_id: str) -> dict[str, set[str]]:
        """Reconstruct ``table → {referred_tables}`` adjacency from the
        schema chunks' metadata. Symmetric: edges are doubled so retriever
        can traverse in either direction.
        """
        records = self._schema.get(where={"db_id": db_id}, include=["metadatas"])
        graph: dict[str, set[str]] = {}
        for meta in records.get("metadatas") or []:
            if not meta:
                continue
            table = str(meta.get("table_name") or "")
            targets_raw = str(meta.get("fk_targets") or "")
            targets = {t for t in targets_raw.split(",") if t}
            if not table:
                continue
            graph.setdefault(table, set()).update(targets)
            for t in targets:
                graph.setdefault(t, set()).add(table)
        return graph

    def _embed_one(self, text: str) -> list[float]:
        return list(self._embedder.embed(EmbedRequest(texts=[text])).vectors[0])


@dataclass(frozen=True, slots=True)
class SchemaQueryHit:
    chunk_id: str
    table_name: str
    db_id: str
    text: str
    distance: float
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FewShotHit:
    example_id: str
    db_id: str
    question: str
    sql: str
    distance: float
    metadata: dict[str, Any]


def _hits_from_query(
    result: Mapping[str, Any],
    *,
    hit_cls: type[SchemaQueryHit] | type[FewShotHit],
) -> list[Any]:
    """Translate a Chroma `.query()` payload into our flat hit dataclass.

    Chroma returns each list nested by query (we always pass one query):
        {"ids": [[id1, id2]], "documents": [[doc1, doc2]], ...}
    so we always index `[0]` to flatten.
    """
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    hits: list[Any] = []
    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) and metas[i] else {}
        doc = docs[i] if i < len(docs) else ""
        dist = float(dists[i]) if i < len(dists) and dists[i] is not None else 0.0
        if hit_cls is SchemaQueryHit:
            hits.append(
                SchemaQueryHit(
                    chunk_id=str(_id),
                    table_name=str(meta.get("table_name") or ""),
                    db_id=str(meta.get("db_id") or ""),
                    text=str(doc),
                    distance=dist,
                    metadata=dict(meta),
                )
            )
        else:
            hits.append(
                FewShotHit(
                    example_id=str(_id),
                    db_id=str(meta.get("db_id") or ""),
                    question=str(doc),
                    sql=str(meta.get("sql") or ""),
                    distance=dist,
                    metadata=dict(meta),
                )
            )
    return hits


def _batched(items: Iterable[Any], n: int) -> Iterator[list[Any]]:
    bucket: list[Any] = []
    for item in items:
        bucket.append(item)
        if len(bucket) >= n:
            yield bucket
            bucket = []
    if bucket:
        yield bucket
