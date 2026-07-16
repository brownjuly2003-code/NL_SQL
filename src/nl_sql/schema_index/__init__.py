"""Schema indexer: introspect, chunk, embed, retrieve.

Stage 3 of the v2 pipeline (per docs/02_architecture_v2.md §4):
- two Chroma collections (`schema_chunks`, `fewshot_qsql`),
- one chunk per table with sample values, null %, FK list,
- FK graph kept in memory as a dict-of-sets, **not** as a Chroma collection.

Public surface:
- `introspect(engine)` → `list[TableInfo]`  (introspector)
- `to_chunks(tables, db_id)` → `list[SchemaChunk]`  (chunker)
- `SchemaIndex` (indexer) — wraps a Chroma persistent client + embed provider
- `retrieve_context(...)` → `ContextBundle`  (retriever)
"""

from __future__ import annotations

from nl_sql.schema_index.chunker import SchemaChunk, to_chunks
from nl_sql.schema_index.fewshot_selection import (
    MASK_TOKEN,
    collect_schema_tokens,
    fewshot_query_text,
    mask_schema_tokens,
    parse_column_names_from_chunk,
)
from nl_sql.schema_index.indexer import (
    FEWSHOT_COLLECTION,
    SCHEMA_COLLECTION,
    FewShotExample,
    FewShotHit,
    SchemaIndex,
    SchemaQueryHit,
)
from nl_sql.schema_index.introspector import (
    ColumnInfo,
    ForeignKeyInfo,
    TableInfo,
    introspect,
)
from nl_sql.schema_index.retriever import ContextBundle, retrieve_context
from nl_sql.schema_index.value_retrieval import (
    ValueMatch,
    extract_query_phrases,
    format_value_grounding,
    retrieve_value_matches,
)

__all__ = [
    "FEWSHOT_COLLECTION",
    "MASK_TOKEN",
    "SCHEMA_COLLECTION",
    "ColumnInfo",
    "ContextBundle",
    "FewShotExample",
    "FewShotHit",
    "ForeignKeyInfo",
    "SchemaChunk",
    "SchemaIndex",
    "SchemaQueryHit",
    "TableInfo",
    "ValueMatch",
    "collect_schema_tokens",
    "extract_query_phrases",
    "fewshot_query_text",
    "format_value_grounding",
    "introspect",
    "mask_schema_tokens",
    "parse_column_names_from_chunk",
    "retrieve_context",
    "retrieve_value_matches",
    "to_chunks",
]
