"""Streamlit UI for the NL→SQL assistant.

Modern light surface: warm stone palette on white, one terracotta accent,
soft shadows and rounded corners (Manrope for text, JetBrains Mono for code).
Controls live in a top bar — database, mode and the EN/RU language
toggle; the sidebar keeps only the schema explorer, advanced retrieval
knobs and clear-chat. Bilingual chrome (data questions stay in their
natural language; the pipeline accepts both EN and RU).

Run with:
    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import time
from typing import Any, cast

import streamlit as st

from bootstrap import bootstrap, make_pipeline
from components.output import render_output
from components.schema_explorer import render_schema_explorer
from components.show_working import render_show_working
from components.welcome import render_welcome
from i18n import t
from nl_sql.agent.graph import PipelineRunResult, run_pipeline
from samples import source_link_for
from theme import inject_chrome


def _render_lang_toggle(col_en: Any, col_ru: Any) -> None:
    """EN | RU joined pill in the top bar; the active segment inverts."""
    lang = st.session_state.get("lang", "en")
    with col_en:
        if st.button(
            t("lang_en"),
            key="lang_en_btn",
            use_container_width=True,
            type="primary" if lang == "en" else "secondary",
        ):
            st.session_state.lang = "en"
            st.rerun()
    with col_ru:
        if st.button(
            t("lang_ru"),
            key="lang_ru_btn",
            use_container_width=True,
            type="primary" if lang == "ru" else "secondary",
        ):
            st.session_state.lang = "ru"
            st.rerun()


def main() -> None:
    if "lang" not in st.session_state:
        st.session_state.lang = "en"

    st.set_page_config(page_title=t("page_title"), layout="wide")
    inject_chrome()

    try:
        registry, schema_index, sql_provider, explain_provider = bootstrap()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()
    st.session_state["_schema_index"] = schema_index

    db_ids = registry.ids()
    if not db_ids:
        st.error("No databases registered. Run scripts/download_data.py first.")
        st.stop()
    default_idx = (
        db_ids.index("bird_california_schools") if "bird_california_schools" in db_ids else 0
    )

    # --- top bar (sticky): wordmark · database · mode · language
    with st.container(key="nl_topbar"):
        c_brand, c_db, c_mode, c_en, c_ru = st.columns(
            [2.4, 3, 3, 0.9, 0.9], vertical_alignment="center"
        )
        with c_brand:
            st.markdown(
                "<div class='nl-wordmark'>NL<span class='arrow'>→</span>SQL</div>",
                unsafe_allow_html=True,
            )
        with c_db:
            db_id = st.selectbox(
                t("db_label"), db_ids, index=default_idx, label_visibility="collapsed"
            )
        with c_mode:
            mode_opts = (t("mode_accurate"), t("mode_fast"), t("mode_debug"))
            mode_help = (
                f"{t('mode_accurate')} — {t('mode_accurate_caption')}\n\n"
                f"{t('mode_fast')} — {t('mode_fast_caption')}\n\n"
                f"{t('mode_debug')} — {t('mode_debug_caption')}"
            )
            mode = st.selectbox(
                t("mode_header"),
                mode_opts,
                index=0,
                label_visibility="collapsed",
                help=mode_help,
            )
        _render_lang_toggle(c_en, c_ru)

    spec = registry.get(db_id)
    if mode == t("mode_fast"):
        fewshot_top_k = 0
        verify_retry_on_empty = False
    else:
        fewshot_top_k = 3
        verify_retry_on_empty = True

    # --- context line under the top bar
    ctx_parts = [f"{t('db_dialect')}: <code>{spec.dialect}</code>"]
    link = source_link_for(db_id)
    if link is not None:
        label, url = link
        ctx_parts.append(f"{t('db_source')}: <a href='{url}' target='_blank'>{label}</a>")
    if spec.description:
        ctx_parts.append(spec.description)
    st.markdown(
        f"<div class='nl-context'>{' · '.join(ctx_parts)}</div>",
        unsafe_allow_html=True,
    )

    # --- sidebar: schema explorer + advanced knobs + clear chat
    with st.sidebar:
        st.markdown(
            "<div class='nl-side-h'>NL<span class='arrow'>→</span>SQL</div>",
            unsafe_allow_html=True,
        )
        render_schema_explorer(db_id)

        with st.expander(t("advanced_header"), expanded=False):
            schema_top_k = st.slider(t("schema_top_k"), 1, 10, 5)
            fk_hops = st.slider(t("fk_hops"), 0, 2, 1)
            table_budget = st.slider(t("table_budget"), 4, 20, 12)
            sort_schema_block = st.checkbox(t("sort_schema"), value=True)
            extended_sample_size = st.slider(t("sample_size"), 0, 8, 0)

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
        if st.button(t("clear_chat"), key="clear_chat_btn", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        render_welcome(db_id)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                _replay_assistant_turn(msg)

    typed = st.chat_input(t("ask_placeholder"))
    queued = st.session_state.pop("pending_question", None)
    question = queued or typed
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    pipeline = make_pipeline(
        registry,
        schema_index,
        sql_provider,
        explain_provider,
        schema_top_k=schema_top_k,
        fk_hops=fk_hops,
        table_budget=table_budget,
        sort_schema_block=sort_schema_block,
        extended_sample_size=extended_sample_size,
        fewshot_top_k=fewshot_top_k,
        verify_retry_on_empty=verify_retry_on_empty,
    )

    with st.chat_message("assistant"):
        with st.spinner(t("spinner_generating")):
            t0 = time.perf_counter()
            try:
                result = run_pipeline(
                    pipeline,
                    question=question,
                    db_id=db_id,
                    dialect=spec.dialect,
                    disable_repair=False,
                    verify_retry_on_empty=verify_retry_on_empty,
                )
            except Exception as exc:
                st.error(t("pipeline_crashed", kind=type(exc).__name__, msg=str(exc)))
                st.session_state.messages.append(
                    {"role": "assistant", "error": str(exc), "question": question}
                )
                return
            wall_ms = (time.perf_counter() - t0) * 1000

        render_output(result.output_format, caption=result.caption)

        if result.sql:
            st.markdown(f"**{t('sql_label')}**")
            st.code(result.sql, language="sql")
        else:
            st.warning(t("no_sql"))

        st.caption(t("wall_model", wall=wall_ms, model=sql_provider.model))

        render_show_working(result)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "question": question,
                "result": result,
                "wall_ms": wall_ms,
                "model": sql_provider.model,
            }
        )


def _replay_assistant_turn(msg: dict[str, Any]) -> None:
    if msg.get("error"):
        st.error(t("pipeline_crashed", kind="prior", msg=msg["error"]))
        return
    result = cast(PipelineRunResult, msg["result"])
    render_output(result.output_format, caption=result.caption)
    if result.sql:
        st.code(result.sql, language="sql")
    st.caption(t("wall_model", wall=msg.get("wall_ms", 0), model=msg.get("model", "?")))
    render_show_working(result)


if __name__ == "__main__":
    main()
