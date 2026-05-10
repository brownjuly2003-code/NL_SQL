"""Streamlit UI for the NL→SQL assistant — Stage 10 of the v2 roadmap.

Lean by design (per docs/02_architecture_v2.md §8): chat input, DB switcher,
the four output formats (scalar / sentence / table / chart), and a "show
working" expander with the retrieved tables, rationale, latency, tokens,
and model. History lives in `st.session_state` (Streamlit's localStorage
equivalent for v1 demo).

Run with:
    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import chromadb
import pandas as pd
import plotly.express as px
import streamlit as st

from nl_sql.agent.graph import PipelineConfig, PipelineRunResult, build_pipeline, run_pipeline
from nl_sql.config import get_settings
from nl_sql.db.registry import DatabaseRegistry, get_default_registry
from nl_sql.llm.cache import CachingEmbeddingProvider, CachingLLMProvider
from nl_sql.llm.providers import build_provider
from nl_sql.llm.providers.base import EmbeddingProvider, LLMProvider
from nl_sql.llm.providers.mistral import MistralProvider
from nl_sql.render.formats import (
    BarChart,
    LineChart,
    OutputFormat,
    PieChart,
    Scalar,
    ScatterChart,
    Sentence,
    Table,
)
from nl_sql.schema_index.indexer import SchemaIndex

# --------------------------------------------------------- sample questions
# Hand-picked from the cached n=200 ablation (matched=True under
# C+sort+s=3, the production candidate). These are guaranteed cache hits,
# so a recruiter sees a sub-second answer on first click.

SAMPLE_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "chinook": [
        ("simple", "How many albums are in the store?"),
        ("simple", "Which 5 artists have the most albums?"),
        ("moderate", "What is the total revenue per genre?"),
    ],
    "bird_california_schools": [
        (
            "simple",
            "How many schools with an average score in Math greater than 400 in the SAT test are exclusively virtual?",
        ),
        (
            "simple",
            "What is the average number of test takers from Fresno schools that opened between 1/1/1980 and 12/31/1980?",
        ),
        (
            "moderate",
            "What is the ratio of merged Unified School District schools in Orange County to merged Elementary School District schools?",
        ),
    ],
    "bird_card_games": [
        ("simple", "How many cards have infinite power?"),
        ("simple", "What language is the set of 180 cards that belongs to the Ravnica block translated into?"),
        ("moderate", "Among the sets in the block 'Ice Age', how many of them have an Italian translation?"),
    ],
    "bird_codebase_community": [
        ("simple", "When did 'chl' cast its first vote in a post?"),
        ("simple", "What is the display name of the user who acquired the first Autobiographer badge?"),
        (
            "moderate",
            "Among the posts with views ranging from 100 to 150, what is the comment with the highest score?",
        ),
    ],
    "bird_debit_card_specializing": [
        ("simple", "What segment did the customer have at 2012/8/23 21:20:00?"),
        ("simple", "What is the percentage of 'premium' against the overall segment in Country = 'SVK'?"),
        ("moderate", "What was the average monthly consumption of customers in SME for the year 2013?"),
    ],
    "bird_european_football_2": [
        ("simple", "List down most tallest players' name."),
        ("simple", "Please name one player whose overall strength is the greatest."),
        ("moderate", "What was the overall rating for Aaron Mooy on 2016/2/4?"),
    ],
    "bird_financial": [
        ("simple", "For the female client who was born in 1976/1/29, which district did she opened her account?"),
        (
            "simple",
            "List out the no. of districts that have female average salary is more than 6000 but less than 10000?",
        ),
        ("moderate", "Provide the IDs and age of the client with high level credit card, which is eligible for loans."),
    ],
    "bird_formula_1": [
        ("simple", "What's the reference name of Marina Bay Street Circuit?"),
        ("simple", "Please state the reference name of the oldest German driver."),
        ("simple", "What's Bruno Senna's Q1 result in the qualifying race No. 354?"),
    ],
    "bird_student_club": [
        ("simple", "What's Angela Sanders's major?"),
        ("simple", "Mention the total expense used on 8/20/2019."),
        ("simple", "What is the total amount of money spent for food?"),
    ],
    "bird_superhero": [
        ("simple", "What is Copycat's race?"),
        ("moderate", "Which hero was the fastest?"),
        ("moderate", "Who is the dumbest superhero?"),
    ],
    "bird_thrombosis_prediction": [
        ("simple", "How many female patients were given an APS diagnosis?"),
        ("moderate", "State the ID and age of patient with positive degree of coagulation."),
        ("moderate", "Was the patient with the number 57266's uric acid within a normal range?"),
    ],
    "bird_toxicology": [
        ("simple", "How many connections does the atom 19 have?"),
        ("moderate", "Which non-carcinogenic molecules consisted more than 5 atoms?"),
        ("challenging", "List the elements of all the triple bonds."),
    ],
}


# --------------------------------------------------------- resource bootstrap


@st.cache_resource(show_spinner="Initialising providers + Chroma index…")
def _bootstrap() -> tuple[DatabaseRegistry, SchemaIndex, LLMProvider, LLMProvider]:
    """Build registry + Chroma + providers once per session.

    Cached so subsequent questions don't re-pay the Chroma persist cost
    (~hundreds of ms) or rebuild the LLM provider chain.
    """
    settings = get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError(
            "MISTRAL_API_KEY is not set in .env — required for codestral + mistral-embed."
        )

    registry = get_default_registry()

    persist_dir = Path("chroma_data")
    if not persist_dir.is_dir():
        raise RuntimeError(
            f"Chroma persist dir {persist_dir!r} not found. "
            "Run `uv run python scripts/build_index.py --db all` first."
        )
    chroma_client = chromadb.PersistentClient(path=str(persist_dir))

    raw_embedder = MistralProvider(
        api_key=settings.mistral_api_key,
        gen_model=settings.mistral_gen_model,
        embed_model=settings.mistral_embed_model,
        base_url=settings.mistral_base_url,
    )
    embedder: EmbeddingProvider = CachingEmbeddingProvider(
        raw_embedder,
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    schema_index = SchemaIndex(
        persist_dir=persist_dir, embedder=embedder, client=chroma_client
    )

    raw_sql = build_provider("mistral", settings=settings)
    sql_provider: LLMProvider = CachingLLMProvider(
        raw_sql,
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    explain_provider = sql_provider  # codestral works for caption in v1

    return registry, schema_index, sql_provider, explain_provider


# --------------------------------------------------------- pipeline assembly


def _make_pipeline(
    registry: DatabaseRegistry,
    schema_index: SchemaIndex,
    sql_provider: LLMProvider,
    explain_provider: LLMProvider,
    *,
    schema_top_k: int,
    fk_hops: int,
    table_budget: int,
    sort_schema_block: bool,
    extended_sample_size: int,
) -> Any:
    config = PipelineConfig(
        sql_provider=sql_provider,
        explain_provider=explain_provider,
        schema_index=schema_index,
        registry=registry,
        schema_top_k=schema_top_k,
        fewshot_top_k=0,  # config D not yet shipped
        fk_hops=fk_hops,
        table_budget=table_budget,
        sort_schema_block=sort_schema_block,
        primary_sample_size=3,
        extended_sample_size=extended_sample_size,
    )
    return build_pipeline(config)


# --------------------------------------------------------- output renderers


def _render_output(output: OutputFormat | None, *, caption: str) -> None:
    if isinstance(output, Scalar):
        col_label = output.column or "result"
        st.metric(col_label, str(output.value))
    elif isinstance(output, Sentence):
        st.markdown(f"**{output.text}**")
        if output.fields:
            st.json(output.fields, expanded=False)
    elif isinstance(output, Table):
        df = pd.DataFrame(output.rows, columns=output.columns)
        st.dataframe(df, use_container_width=True, hide_index=True)
    elif isinstance(output, BarChart | LineChart | PieChart | ScatterChart):
        df = pd.DataFrame(output.rows, columns=output.columns)
        _render_chart(output, df)
    elif output is None:
        st.warning("No output format produced.")
    if caption:
        st.caption(caption)


def _render_chart(
    spec: BarChart | LineChart | PieChart | ScatterChart,
    df: pd.DataFrame,
) -> None:
    if isinstance(spec, BarChart):
        fig = px.bar(df, x=spec.x_field, y=spec.y_fields)
    elif isinstance(spec, LineChart):
        fig = px.line(df, x=spec.x_field, y=spec.y_fields)
    elif isinstance(spec, PieChart):
        y_field = spec.y_fields[0] if spec.y_fields else df.columns[1]
        fig = px.pie(df, names=spec.x_field, values=y_field)
    else:  # ScatterChart
        y_field = spec.y_fields[0] if spec.y_fields else df.columns[1]
        fig = px.scatter(df, x=spec.x_field, y=y_field)
    st.plotly_chart(fig, use_container_width=True)


def _render_show_working(result: PipelineRunResult) -> None:
    with st.expander("Показать работу (schema, SQL, latency, errors)"):
        col_a, col_b = st.columns(2)
        latency_ms = 0.0
        for entry in result.trace:
            value = entry.get("elapsed_ms", 0)
            if isinstance(value, int | float):
                latency_ms += float(value)
        with col_a:
            st.markdown("**Pipeline trace**")
            for entry in result.trace:
                node = entry.get("node", "?")
                rest = {k: v for k, v in entry.items() if k != "node"}
                st.markdown(f"- `{node}` — {rest}")
        with col_b:
            st.markdown("**Metadata**")
            st.markdown(f"- DB: `{result.db_id}`")
            st.markdown(f"- Confidence: {result.confidence:.2f}")
            st.markdown(f"- Repair attempted: {result.repair_attempted}")
            if latency_ms:
                st.markdown(f"- Execution latency: {latency_ms:.0f} ms")
            if result.outcome and result.outcome.result:
                st.markdown(f"- Rows returned: {result.outcome.result.row_count}")
        if result.rationale:
            st.markdown("**Rationale**")
            st.write(result.rationale)
        if result.error_kind:
            st.error(f"Error: {result.error_kind} — {result.error_message}")


# ----------------------------------------------------------------- welcome


def _render_welcome(db_id: str) -> None:
    """Empty-state hero shown before any chat turn — recruiter-friendly."""
    col_intro, col_metric = st.columns([2, 1])
    with col_intro:
        st.markdown(
            "Ask a natural-language question about the selected database. "
            "The pipeline retrieves relevant tables (schema-RAG over Chroma), "
            "generates SQL with `codestral-latest`, validates it through "
            "sqlglot AST guards, executes against a read-only engine, and "
            "renders the result in the cleanest format for the shape of "
            "the answer."
        )
    with col_metric:
        st.metric(
            label="Execution Accuracy on BIRD Mini-Dev (n=200)",
            value="47.0%",
            help="C+sort_schema_block, codestral-latest, $0 budget. "
            "Reference: GPT-4 zero-shot on the same split = 47.8%.",
        )

    samples = SAMPLE_QUESTIONS.get(db_id)
    if not samples:
        st.info(f"No sample questions curated for `{db_id}` yet — type your own below.")
        return

    st.markdown("**Try a sample question:**")
    cols = st.columns(len(samples))
    for col, (difficulty, question) in zip(cols, samples, strict=False):
        with col:
            if st.button(
                f"{difficulty}\n\n{question}",
                key=f"sample_{db_id}_{hash(question)}",
                use_container_width=True,
            ):
                st.session_state.pending_question = question
                st.rerun()


# ---------------------------------------------------------------------- main


def main() -> None:
    st.set_page_config(
        page_title="NL→SQL Assistant",
        page_icon="📊",
        layout="wide",
    )
    st.title("NL→SQL Assistant")
    st.caption(
        "Portfolio demo · BIRD Mini-Dev + Chinook · codestral-latest "
        "with schema-RAG, sqlglot AST guards, and deterministic chart picker."
    )

    try:
        registry, schema_index, sql_provider, explain_provider = _bootstrap()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    # --- sidebar: DB + knobs
    with st.sidebar:
        st.header("Settings")
        db_ids = registry.ids()
        if not db_ids:
            st.error("No databases registered. Run scripts/download_data.py first.")
            st.stop()
        default_idx = (
            db_ids.index("bird_california_schools")
            if "bird_california_schools" in db_ids
            else 0
        )
        db_id = st.selectbox("Database", db_ids, index=default_idx)
        spec = registry.get(db_id)
        st.caption(f"Dialect: `{spec.dialect}`")
        if spec.description:
            st.caption(spec.description)

        st.divider()
        st.subheader("Retrieval knobs")
        schema_top_k = st.slider("schema_top_k", 1, 10, 5)
        fk_hops = st.slider("fk_hops", 0, 2, 1)
        table_budget = st.slider("table_budget", 4, 20, 12)
        sort_schema_block = st.checkbox("sort_schema_block (alphabetical)", value=True)
        extended_sample_size = st.slider(
            "extended_sample_size (0 = mixture off)", 0, 8, 0
        )

        st.divider()
        if st.button("Clear chat history"):
            st.session_state.messages = []
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # --- welcome / empty state with sample questions
    if not st.session_state.messages:
        _render_welcome(db_id)

    # --- chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                _replay_assistant_turn(msg)

    # --- new question (typed input OR queued sample button click)
    typed = st.chat_input("Спроси по данным выбранной БД…")
    queued = st.session_state.pop("pending_question", None)
    question = queued or typed
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    pipeline = _make_pipeline(
        registry,
        schema_index,
        sql_provider,
        explain_provider,
        schema_top_k=schema_top_k,
        fk_hops=fk_hops,
        table_budget=table_budget,
        sort_schema_block=sort_schema_block,
        extended_sample_size=extended_sample_size,
    )

    with st.chat_message("assistant"):
        with st.spinner("Generating SQL + executing…"):
            t0 = time.perf_counter()
            try:
                result = run_pipeline(
                    pipeline,
                    question=question,
                    db_id=db_id,
                    dialect=spec.dialect,
                    disable_repair=False,
                )
            except Exception as exc:
                st.error(f"Pipeline crashed: {type(exc).__name__}: {exc}")
                st.session_state.messages.append(
                    {"role": "assistant", "error": str(exc), "question": question}
                )
                return
            wall_ms = (time.perf_counter() - t0) * 1000

        _render_output(result.output_format, caption=result.caption)

        if result.sql:
            st.markdown("**SQL**")
            st.code(result.sql, language="sql")
        else:
            st.warning("Pipeline produced no SQL.")

        st.caption(f"Wall: {wall_ms:.0f} ms · Model: {sql_provider.model}")

        _render_show_working(result)

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
    """Re-render a stored assistant turn from session_state."""
    if msg.get("error"):
        st.error(f"Pipeline crashed: {msg['error']}")
        return
    result = cast(PipelineRunResult, msg["result"])
    _render_output(result.output_format, caption=result.caption)
    if result.sql:
        st.code(result.sql, language="sql")
    st.caption(f"Wall: {msg.get('wall_ms', 0):.0f} ms · Model: {msg.get('model', '?')}")
    _render_show_working(result)


if __name__ == "__main__":
    main()
