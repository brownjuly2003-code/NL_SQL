"""Sidebar schema explorer: per-table chunk cards rendered from the index."""

from __future__ import annotations

import streamlit as st

from i18n import t


@st.cache_data(show_spinner=False)
def fetch_schema_chunks(_index_id: int, db_id: str) -> list[tuple[str, str]]:
    schema_index = st.session_state.get("_schema_index")
    if schema_index is None:
        return []
    records = schema_index.schema_collection.get(
        where={"db_id": db_id},
        include=["documents", "metadatas"],
    )
    docs = records.get("documents") or []
    metas = records.get("metadatas") or []
    pairs: list[tuple[str, str]] = []
    for doc, meta in zip(docs, metas, strict=False):
        table_name = str((meta or {}).get("table_name") or "")
        if table_name:
            pairs.append((table_name, str(doc)))
    pairs.sort(key=lambda p: p[0].lower())
    return pairs


def render_schema_explorer(db_id: str) -> None:
    schema_index = st.session_state.get("_schema_index")
    if schema_index is None:
        return
    chunks = fetch_schema_chunks(id(schema_index), db_id)
    if not chunks:
        st.caption(t("schema_explorer_empty"))
        return
    with st.expander(t("schema_explorer_collapsed", n=len(chunks)), expanded=False):
        st.caption(t("schema_explorer_caption"))
        for table_name, text in chunks:
            with st.expander(table_name, expanded=False):
                st.code(text, language="text")
