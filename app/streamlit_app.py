"""Streamlit UI for the NL→SQL assistant.

Editorial monochrome surface: ink-on-paper background, typography-led
hierarchy, two custom faces (Stetica sans for chrome, TT Norms Pro Serif
for display). Bilingual: EN/RU toggle in the sidebar (chrome only — data
questions stay in their natural language; the pipeline accepts both).

Run with:
    uv run streamlit run app/streamlit_app.py
"""

# Bilingual UI mixes Cyrillic and Latin in `I18N["ru"]` — silence the
# ambiguous-glyph lint at module scope.
# ruff: noqa: RUF001

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
from nl_sql.render.labels import classify_scalar_label
from nl_sql.schema_index.indexer import SchemaIndex

# --------------------------------------------------------- i18n
# Chrome-level strings only. Sample questions stay in their natural
# language — the pipeline handles EN + RU both, the toggle only flips
# the surrounding UI copy.

I18N: dict[str, dict[str, str]] = {
    "en": {
        "page_title": "NL → SQL",
        "tagline": "Natural language in. SQL out. Answer rendered in whichever shape fits the question.",
        "lang_label": "Language",
        "lang_en": "EN",
        "lang_ru": "RU",
        "metric_kicker": "Chinook business workload",
        "metric_value": "60 / 60 correct",
        "metric_percent": "100%",
        "metric_caption": "30 dev + 30 held-out, balanced split, all ten query categories at 100% on the free-tier codestral pipeline.",
        "research_kicker": "BIRD Mini-Dev research benchmark",
        "research_value": "84.5% / 200",
        "research_caption": "Hybrid pipeline: codestral + Sonnet on challenging tier + cross-provider voting + grounded-critique directed retry + Sonnet 4.6 bridge + M-Schema compact serialization + CHASE-SQL divide-and-conquer + Perplexity Pro multi-model voting (Grok 4.1 + GPT-5.2) + reasoning-mode variants (grok-4.1-reasoning + gpt-5.2-thinking + kimi-k2-thinking) on residue. +36.7pp over the GPT-4 zero-shot reference (47.8%), $0 external cost. On Arcwise-Plat corrected gold (Jin et al., CIDR 2026): 67.34% — honest noise-floor after BIRD annotation fixes; +6 cases where our pred catches BIRD's wrong gold.",
        "settings_header": "Settings",
        "db_label": "Database",
        "db_dialect": "Dialect",
        "db_source": "Source",
        "schema_explorer_collapsed": "Schema · {n} tables",
        "schema_explorer_empty": "Schema index empty for this database. Run scripts/build_index.py.",
        "schema_explorer_caption": "The same chunks the retriever sees — table cards with columns, types, null and distinct stats, sample values, and foreign keys.",
        "mode_header": "Mode",
        "mode_accurate": "Accurate",
        "mode_fast": "Fast",
        "mode_debug": "Debug",
        "mode_accurate_caption": "fewshot + verify-retry — best EA",
        "mode_fast_caption": "no fewshot — fastest, slight EA loss",
        "mode_debug_caption": "Accurate + raw trace in show-working",
        "advanced_header": "Advanced retrieval",
        "schema_top_k": "schema_top_k",
        "fk_hops": "fk_hops",
        "table_budget": "table_budget",
        "sort_schema": "sort schema block (alphabetical)",
        "sample_size": "extended sample size",
        "clear_chat": "Clear chat",
        "ask_placeholder": "Ask a question about this database (EN or RU)…",
        "ask_intro_label": "Try one of these to start",
        "diff_simple": "simple",
        "diff_moderate": "moderate",
        "diff_challenging": "challenging",
        "no_samples": "No sample questions curated for this database yet — type your own below.",
        "spinner_generating": "Generating SQL and executing…",
        "pipeline_crashed": "Pipeline crashed: {kind}: {msg}",
        "sql_label": "SQL",
        "no_sql": "Pipeline produced no SQL.",
        "wall_model": "{wall:.0f} ms · {model}",
        "show_working": "Show working — pipeline trace, SQL, metadata",
        "trace_header": "Pipeline trace",
        "meta_header": "Metadata",
        "shape_header": "Result shape",
        "confidence_label": "Confidence",
        "repair_attempted": "Repair attempted",
        "db_field": "Database",
        "rows_returned": "Rows returned",
        "columns_field": "Columns",
        "no_rows": "No result rows.",
        "rationale_header": "Rationale",
        "error_kind": "Error",
        "no_output_warning": "No output format produced.",
        "conf_high": "High",
        "conf_med": "Medium",
        "conf_low": "Low",
        "conf_unknown": "Unknown",
        "scalar_label_count": "Count",
        "scalar_label_sum": "Sum",
        "scalar_label_average": "Average",
        "scalar_label_minimum": "Minimum",
        "scalar_label_maximum": "Maximum",
        "scalar_label_ratio": "Ratio",
        "scalar_label_result": "Result",
    },
    "ru": {
        "page_title": "NL → SQL",
        "tagline": "На входе — естественный язык. На выходе — SQL и ответ в форме, которая подходит вопросу.",
        "lang_label": "Язык",
        "lang_en": "EN",
        "lang_ru": "RU",
        "metric_kicker": "Бизнес-нагрузка Chinook",
        "metric_value": "60 из 60",
        "metric_percent": "100%",
        "metric_caption": "30 dev + 30 held-out, сбалансированный сплит, все десять категорий запросов на 100% через бесплатный codestral.",
        "research_kicker": "Исследовательский бенчмарк BIRD Mini-Dev",
        "research_value": "84.5% / 200",
        "research_caption": "Гибрид: codestral + Sonnet на challenging-тире + кросс-провайдер voting + grounded-critique directed retry + Sonnet 4.6 bridge + компактная M-Schema + CHASE-SQL divide-and-conquer + Perplexity Pro multi-model voting (Grok 4.1 + GPT-5.2) + reasoning-режим (grok-4.1-reasoning + gpt-5.2-thinking + kimi-k2-thinking) на residue. +36.7 п.п. над zero-shot GPT-4 (47.8%), внешние расходы — ноль. На исправленном gold Arcwise-Plat (Jin et al., CIDR 2026) — 67.34%, честный noise-floor после правки аннотаций BIRD; +6 случаев, где наш pred правильнее эталона BIRD.",
        "settings_header": "Настройки",
        "db_label": "База данных",
        "db_dialect": "Диалект",
        "db_source": "Источник",
        "schema_explorer_collapsed": "Схема · {n} таблиц",
        "schema_explorer_empty": "Индекс схемы пуст для этой БД. Запусти scripts/build_index.py.",
        "schema_explorer_caption": "Те же чанки, которые видит ретривер — карточки таблиц с колонками, типами, null/distinct, sample-значениями и foreign keys.",
        "mode_header": "Режим",
        "mode_accurate": "Точно",
        "mode_fast": "Быстро",
        "mode_debug": "Отладка",
        "mode_accurate_caption": "fewshot + verify-retry — максимальный EA",
        "mode_fast_caption": "без fewshot — быстрее, EA чуть ниже",
        "mode_debug_caption": "Точно + сырой trace в show-working",
        "advanced_header": "Тонкая настройка ретривала",
        "schema_top_k": "schema_top_k",
        "fk_hops": "fk_hops",
        "table_budget": "table_budget",
        "sort_schema": "сортировать блок схемы (по алфавиту)",
        "sample_size": "размер расширенного семпла",
        "clear_chat": "Очистить чат",
        "ask_placeholder": "Спроси что-нибудь об этой базе (EN или RU)…",
        "ask_intro_label": "Можно начать с одного из этих вопросов",
        "diff_simple": "просто",
        "diff_moderate": "средне",
        "diff_challenging": "сложно",
        "no_samples": "Для этой БД пока нет подготовленных вопросов — задай свой ниже.",
        "spinner_generating": "Генерирую SQL и выполняю…",
        "pipeline_crashed": "Пайплайн упал: {kind}: {msg}",
        "sql_label": "SQL",
        "no_sql": "Пайплайн не выдал SQL.",
        "wall_model": "{wall:.0f} мс · {model}",
        "show_working": "Показать работу — trace, SQL, метаданные",
        "trace_header": "Trace пайплайна",
        "meta_header": "Метаданные",
        "shape_header": "Форма результата",
        "confidence_label": "Уверенность",
        "repair_attempted": "Был ли repair",
        "db_field": "База",
        "rows_returned": "Строк в ответе",
        "columns_field": "Колонки",
        "no_rows": "Строки не вернулись.",
        "rationale_header": "Обоснование",
        "error_kind": "Ошибка",
        "no_output_warning": "Формат вывода не был построен.",
        "conf_high": "Высокая",
        "conf_med": "Средняя",
        "conf_low": "Низкая",
        "conf_unknown": "Неизвестно",
        "scalar_label_count": "Количество",
        "scalar_label_sum": "Сумма",
        "scalar_label_average": "Среднее",
        "scalar_label_minimum": "Минимум",
        "scalar_label_maximum": "Максимум",
        "scalar_label_ratio": "Отношение",
        "scalar_label_result": "Результат",
    },
}


def _t(key: str, **kwargs: Any) -> str:
    lang = st.session_state.get("lang", "en")
    template = I18N.get(lang, I18N["en"]).get(key) or I18N["en"].get(key) or key
    return template.format(**kwargs) if kwargs else template


# --------------------------------------------------------- sample questions

SOURCE_LINKS: dict[str, tuple[str, str]] = {
    "chinook": (
        "Chinook SQLite (lerocha/chinook-database)",
        "https://github.com/lerocha/chinook-database",
    ),
    "_bird_default": (
        "BIRD Mini-Dev (bird-bench.github.io)",
        "https://bird-bench.github.io/",
    ),
}


def _source_link_for(db_id: str) -> tuple[str, str] | None:
    if db_id in SOURCE_LINKS:
        return SOURCE_LINKS[db_id]
    if db_id.startswith("bird_"):
        return SOURCE_LINKS["_bird_default"]
    return None


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
        (
            "simple",
            "What language is the set of 180 cards that belongs to the Ravnica block translated into?",
        ),
        (
            "moderate",
            "Among the sets in the block 'Ice Age', how many of them have an Italian translation?",
        ),
    ],
    "bird_codebase_community": [
        ("simple", "When did 'chl' cast its first vote in a post?"),
        (
            "simple",
            "What is the display name of the user who acquired the first Autobiographer badge?",
        ),
        (
            "moderate",
            "Among the posts with views ranging from 100 to 150, what is the comment with the highest score?",
        ),
    ],
    "bird_debit_card_specializing": [
        ("simple", "What segment did the customer have at 2012/8/23 21:20:00?"),
        (
            "simple",
            "What is the percentage of 'premium' against the overall segment in Country = 'SVK'?",
        ),
        (
            "moderate",
            "What was the average monthly consumption of customers in SME for the year 2013?",
        ),
    ],
    "bird_european_football_2": [
        ("simple", "List down most tallest players' name."),
        ("simple", "Please name one player whose overall strength is the greatest."),
        ("moderate", "What was the overall rating for Aaron Mooy on 2016/2/4?"),
    ],
    "bird_financial": [
        (
            "simple",
            "For the female client who was born in 1976/1/29, which district did she opened her account?",
        ),
        (
            "simple",
            "List out the no. of districts that have female average salary is more than 6000 but less than 10000?",
        ),
        (
            "moderate",
            "Provide the IDs and age of the client with high level credit card, which is eligible for loans.",
        ),
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


# --------------------------------------------------------- typography + chrome


_FONT_CSS = """
<style>
@font-face {
  font-family: 'Stetica';
  src: url('/app/static/fonts/stetica-regular.otf') format('opentype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Stetica';
  src: url('/app/static/fonts/stetica-medium.otf') format('opentype');
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Stetica';
  src: url('/app/static/fonts/stetica-bold.otf') format('opentype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'NLEdSerif';
  src: url('/app/static/fonts/serif-regular.otf') format('opentype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'NLEdSerif';
  src: url('/app/static/fonts/serif-bold.otf') format('opentype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

:root {
  --ink:        #111111;
  --ink-soft:   #4A4A4A;
  --ink-mute:   #7A7A75;
  --paper:      #FAFAF7;
  --paper-warm: #F1EFE9;
  --rule:       #1A1A1A;
  --hairline:   #DCD8CE;
}

html, body, [class*="css"], .stApp, .stMarkdown, .stChatMessage {
  font-family: 'Stetica', system-ui, sans-serif !important;
  color: var(--ink);
  background: var(--paper);
}

.block-container {
  padding-top: 2.4rem;
  padding-bottom: 4rem;
  max-width: 1080px;
}

/* Hide Streamlit chrome we don't want */
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
header { background: var(--paper) !important; }

/* Display headline — serif */
.nl-display {
  font-family: 'NLEdSerif', Georgia, serif;
  font-weight: 400;
  font-size: clamp(2.6rem, 5vw, 3.6rem);
  letter-spacing: -0.02em;
  line-height: 0.95;
  color: var(--ink);
  margin: 0 0 0.4rem 0;
}
.nl-display .arrow {
  font-weight: 700;
  display: inline-block;
  transform: translateY(-0.04em);
  margin: 0 0.25rem;
}

.nl-tagline {
  font-family: 'Stetica', system-ui, sans-serif;
  font-weight: 400;
  font-size: 1.02rem;
  line-height: 1.5;
  color: var(--ink-soft);
  max-width: 56ch;
  margin: 0 0 2rem 0;
}

/* Kicker — small uppercase letter-spaced label */
.nl-kicker {
  font-family: 'Stetica', sans-serif;
  font-size: 0.68rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 0.5rem;
}

/* Metric block — pure typography, no card chrome */
.nl-metric {
  border-top: 1px solid var(--rule);
  padding-top: 0.8rem;
  margin-top: 1.4rem;
}
.nl-metric-row {
  display: flex;
  align-items: baseline;
  gap: 0.9rem;
  margin-bottom: 0.5rem;
}
.nl-metric-value {
  font-family: 'NLEdSerif', Georgia, serif;
  font-weight: 700;
  font-size: 2.2rem;
  letter-spacing: -0.01em;
  color: var(--ink);
  line-height: 1;
}
.nl-metric-aside {
  font-family: 'Stetica', sans-serif;
  font-size: 0.86rem;
  color: var(--ink-mute);
  letter-spacing: 0.04em;
}
.nl-metric-cap {
  font-family: 'Stetica', sans-serif;
  font-size: 0.86rem;
  color: var(--ink-soft);
  line-height: 1.55;
  max-width: 62ch;
}

/* Section rule */
.nl-section-label {
  font-family: 'Stetica', sans-serif;
  font-size: 0.68rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 2.4rem 0 0.7rem 0;
  border-top: 1px solid var(--hairline);
  padding-top: 0.7rem;
}

/* Sidebar polish */
[data-testid="stSidebar"] {
  background: var(--paper-warm) !important;
  border-right: 1px solid var(--hairline);
}
[data-testid="stSidebar"] .nl-side-h {
  font-family: 'NLEdSerif', Georgia, serif;
  font-weight: 700;
  font-size: 1.1rem;
  letter-spacing: -0.005em;
  margin: 0.4rem 0 0.6rem 0;
}
[data-testid="stSidebar"] .nl-side-sub {
  font-family: 'Stetica', sans-serif;
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 1.2rem 0 0.4rem 0;
}

/* Language toggle */
.nl-lang-row { display: flex; gap: 0; }
.nl-lang-row button {
  background: transparent !important;
  color: var(--ink) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 0 !important;
  font-family: 'Stetica', sans-serif !important;
  font-weight: 500 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase;
  padding: 0.35rem 0.9rem !important;
  font-size: 0.74rem !important;
  min-height: 0 !important;
}

/* Buttons (sample questions) */
.stButton > button {
  background: transparent !important;
  color: var(--ink) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 0 !important;
  font-family: 'Stetica', sans-serif !important;
  font-weight: 400 !important;
  font-size: 0.92rem !important;
  text-align: left !important;
  padding: 0.85rem 1rem !important;
  line-height: 1.45 !important;
  transition: background 0.12s;
  white-space: normal !important;
  height: auto !important;
}
.stButton > button:hover {
  background: var(--ink) !important;
  color: var(--paper) !important;
}
.stButton > button p {
  color: inherit !important;
}

/* Chat input */
.stChatInput { border-top: 1px solid var(--rule) !important; }
.stChatInput textarea {
  font-family: 'Stetica', sans-serif !important;
  font-size: 1rem !important;
  color: var(--ink) !important;
  background: var(--paper) !important;
}

/* Code blocks — keep mono but on warm paper */
pre, code {
  background: var(--paper-warm) !important;
  color: var(--ink) !important;
  border: 1px solid var(--hairline) !important;
  border-radius: 0 !important;
  font-family: 'JetBrains Mono', 'IBM Plex Mono', ui-monospace, monospace !important;
}

/* Scalar metric block — flatten */
[data-testid="stMetric"] {
  background: transparent !important;
  border: none !important;
}
[data-testid="stMetricLabel"] {
  font-family: 'Stetica', sans-serif !important;
  font-size: 0.68rem !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: var(--ink-mute) !important;
}
[data-testid="stMetricValue"] {
  font-family: 'NLEdSerif', Georgia, serif !important;
  font-weight: 700 !important;
  font-size: 2.4rem !important;
  color: var(--ink) !important;
}

/* Tables */
[data-testid="stDataFrame"] { border: 1px solid var(--rule); }

/* Expanders */
.streamlit-expanderHeader {
  font-family: 'Stetica', sans-serif !important;
  font-size: 0.78rem !important;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink) !important;
}

/* Sample card — wraps a button + difficulty kicker */
.nl-sample {
  display: block;
}
.nl-sample-kicker {
  font-family: 'Stetica', sans-serif;
  font-size: 0.62rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 0 0 0.4rem 0.05rem;
}

/* Chat message bubbles — strip default round chrome */
[data-testid="stChatMessage"] {
  background: transparent !important;
  border: 0 !important;
  padding: 0.4rem 0 1.4rem 0 !important;
}
[data-testid="stChatMessage"]:not(:first-child) {
  border-top: 1px solid var(--hairline) !important;
  padding-top: 1.4rem !important;
}

/* Remove the avatar/icon circle Streamlit injects — covers every variant */
[data-testid="stChatMessage"] > div:first-child,
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"],
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] [class*="Avatar"],
[data-testid="stChatMessage"] svg {
  display: none !important;
}

/* The chat message body lives in second child after the avatar; pull it left */
[data-testid="stChatMessage"] > div:nth-child(2) {
  margin-left: 0 !important;
  padding-left: 0 !important;
  width: 100% !important;
}
</style>
"""


def _inject_chrome() -> None:
    st.markdown(_FONT_CSS, unsafe_allow_html=True)


# --------------------------------------------------------- resource bootstrap


@st.cache_resource(show_spinner="Initialising providers + Chroma index…")
def _bootstrap() -> tuple[DatabaseRegistry, SchemaIndex, LLMProvider, LLMProvider]:
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
    schema_index = SchemaIndex(persist_dir=persist_dir, embedder=embedder, client=chroma_client)

    raw_sql = build_provider("mistral", settings=settings)
    sql_provider: LLMProvider = CachingLLMProvider(
        raw_sql,
        cache_dir=settings.llm_cache_dir,
        size_limit_gb=settings.llm_cache_size_limit_gb,
    )
    explain_provider = sql_provider

    return registry, schema_index, sql_provider, explain_provider


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
    fewshot_top_k: int = 3,
    cross_db_fewshot: bool = True,
    verify_retry_on_empty: bool = True,
) -> Any:
    config = PipelineConfig(
        sql_provider=sql_provider,
        explain_provider=explain_provider,
        schema_index=schema_index,
        registry=registry,
        schema_top_k=schema_top_k,
        fewshot_top_k=fewshot_top_k,
        fk_hops=fk_hops,
        table_budget=table_budget,
        sort_schema_block=sort_schema_block,
        primary_sample_size=3,
        extended_sample_size=extended_sample_size,
        cross_db_fewshot=cross_db_fewshot,
        verify_retry_on_empty=verify_retry_on_empty,
    )
    return build_pipeline(config)


# --------------------------------------------------------- output renderers


def _render_output(output: OutputFormat | None, *, caption: str) -> None:
    if isinstance(output, Scalar):
        st.metric(_scalar_metric_label(output.column), str(output.value))
    elif isinstance(output, Sentence):
        st.markdown(
            f"<div style=\"font-family:'NLEdSerif',Georgia,serif; "
            f"font-size:1.25rem; line-height:1.45; color:var(--ink); "
            f'margin:0.4rem 0 0.6rem;">{output.text}</div>',
            unsafe_allow_html=True,
        )
        if output.fields:
            st.json(output.fields, expanded=False)
    elif isinstance(output, Table):
        df = pd.DataFrame(output.rows, columns=output.columns)
        st.dataframe(df, use_container_width=True, hide_index=True)
    elif isinstance(output, BarChart | LineChart | PieChart | ScatterChart):
        df = pd.DataFrame(output.rows, columns=output.columns)
        _render_chart(output, df)
    elif output is None:
        st.warning(_t("no_output_warning"))
    if caption:
        st.caption(caption)


_CHART_PALETTE = ["#111111", "#4A4A4A", "#7A7A75", "#A8A29E", "#1A1A1A"]


def _style_fig(fig: Any) -> Any:
    fig.update_layout(
        font_family="Stetica, system-ui, sans-serif",
        font_color="#111111",
        paper_bgcolor="#FAFAF7",
        plot_bgcolor="#FAFAF7",
        colorway=_CHART_PALETTE,
        margin=dict(l=10, r=10, t=20, b=10),
    )
    fig.update_xaxes(gridcolor="#DCD8CE", zerolinecolor="#1A1A1A", tickcolor="#1A1A1A")
    fig.update_yaxes(gridcolor="#DCD8CE", zerolinecolor="#1A1A1A", tickcolor="#1A1A1A")
    return fig


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
    else:
        y_field = spec.y_fields[0] if spec.y_fields else df.columns[1]
        fig = px.scatter(df, x=spec.x_field, y=y_field)
    st.plotly_chart(_style_fig(fig), use_container_width=True)


def _scalar_metric_label(column: str) -> str:
    """Translate a raw SQL column label into a localized business label
    (audit P2 #5). Engine columns like ``COUNT(DISTINCT s.CDSCode)`` become
    "Count" / "Количество"; identifier-like columns (``total_revenue``) are
    kept as-is."""
    kind = classify_scalar_label(column)
    if kind == "identifier":
        return column
    return _t(f"scalar_label_{kind}")


def _confidence_label(value: float) -> str:
    if value >= 0.8:
        return _t("conf_high")
    if value >= 0.5:
        return _t("conf_med")
    if value > 0.0:
        return _t("conf_low")
    return _t("conf_unknown")


def _render_show_working(result: PipelineRunResult) -> None:
    with st.expander(_t("show_working")):
        trace_rows: list[dict[str, Any]] = []
        for entry in result.trace:
            trace_rows.append(
                {
                    "node": str(entry.get("node", "?")),
                    "model": str(entry.get("model", "—")),
                    "tokens_in": entry.get("input_tokens", "—"),
                    "tokens_out": entry.get("output_tokens", "—"),
                    "confidence": entry.get("confidence", "—"),
                }
            )
        if trace_rows:
            st.markdown(f"**{_t('trace_header')}**")
            st.dataframe(
                pd.DataFrame(trace_rows),
                use_container_width=True,
                hide_index=True,
            )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**{_t('meta_header')}**")
            conf_label = _confidence_label(result.confidence)
            st.markdown(f"- {_t('confidence_label')}: **{conf_label}** ({result.confidence:.2f})")
            st.markdown(f"- {_t('repair_attempted')}: {result.repair_attempted}")
            st.markdown(f"- {_t('db_field')}: `{result.db_id}`")
        with col_b:
            st.markdown(f"**{_t('shape_header')}**")
            if result.outcome and result.outcome.result:
                st.markdown(f"- {_t('rows_returned')}: {result.outcome.result.row_count}")
                cols = ", ".join(result.outcome.result.columns) or "—"
                st.markdown(f"- {_t('columns_field')}: {cols}")
            else:
                st.markdown(f"- {_t('no_rows')}")
        if result.rationale:
            st.markdown(f"**{_t('rationale_header')}**")
            st.write(result.rationale)
        if result.error_kind:
            st.error(f"{_t('error_kind')}: {result.error_kind} — {result.error_message}")


# ------------------------------------------------------------ schema explorer


@st.cache_data(show_spinner=False)
def _fetch_schema_chunks(_index_id: int, db_id: str) -> list[tuple[str, str]]:
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


def _render_schema_explorer(db_id: str) -> None:
    schema_index = st.session_state.get("_schema_index")
    if schema_index is None:
        return
    chunks = _fetch_schema_chunks(id(schema_index), db_id)
    if not chunks:
        st.caption(_t("schema_explorer_empty"))
        return
    with st.expander(_t("schema_explorer_collapsed", n=len(chunks)), expanded=False):
        st.caption(_t("schema_explorer_caption"))
        for table_name, text in chunks:
            with st.expander(table_name, expanded=False):
                st.code(text, language="text")


# ----------------------------------------------------------------- hero


def _render_welcome(db_id: str) -> None:
    st.markdown(
        "<div class='nl-display'>NL<span class='arrow'>→</span>SQL</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='nl-tagline'>{_t('tagline')}</div>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"""
            <div class='nl-metric'>
              <div class='nl-kicker'>{_t("metric_kicker")}</div>
              <div class='nl-metric-row'>
                <span class='nl-metric-value'>{_t("metric_value")}</span>
                <span class='nl-metric-aside'>{_t("metric_percent")}</span>
              </div>
              <div class='nl-metric-cap'>{_t("metric_caption")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f"""
            <div class='nl-metric'>
              <div class='nl-kicker'>{_t("research_kicker")}</div>
              <div class='nl-metric-row'>
                <span class='nl-metric-value'>{_t("research_value")}</span>
              </div>
              <div class='nl-metric-cap'>{_t("research_caption")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    samples = SAMPLE_QUESTIONS.get(db_id)
    if not samples:
        st.markdown(
            f"<div class='nl-section-label'>{_t('ask_intro_label')}</div>",
            unsafe_allow_html=True,
        )
        st.info(_t("no_samples"))
        return

    st.markdown(
        f"<div class='nl-section-label'>{_t('ask_intro_label')}</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(len(samples))
    diff_map = {
        "simple": _t("diff_simple"),
        "moderate": _t("diff_moderate"),
        "challenging": _t("diff_challenging"),
    }
    for col, (difficulty, question) in zip(cols, samples, strict=False):
        with col:
            st.markdown(
                f"<div class='nl-sample-kicker'>{diff_map.get(difficulty, difficulty)}</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                question,
                key=f"sample_{db_id}_{hash(question)}",
                use_container_width=True,
            ):
                st.session_state.pending_question = question
                st.rerun()


# ---------------------------------------------------------------------- main


def _render_lang_toggle() -> None:
    """Two flat segments: EN / RU. Active one inverts."""
    lang = st.session_state.get("lang", "en")
    st.markdown(f"<div class='nl-side-sub'>{_t('lang_label')}</div>", unsafe_allow_html=True)
    cols = st.columns(2)
    with cols[0]:
        if st.button(
            _t("lang_en"),
            key="lang_en_btn",
            use_container_width=True,
            type="primary" if lang == "en" else "secondary",
        ):
            st.session_state.lang = "en"
            st.rerun()
    with cols[1]:
        if st.button(
            _t("lang_ru"),
            key="lang_ru_btn",
            use_container_width=True,
            type="primary" if lang == "ru" else "secondary",
        ):
            st.session_state.lang = "ru"
            st.rerun()


def main() -> None:
    if "lang" not in st.session_state:
        st.session_state.lang = "en"

    st.set_page_config(
        page_title=_t("page_title"),
        layout="wide",
    )

    _inject_chrome()

    try:
        registry, schema_index, sql_provider, explain_provider = _bootstrap()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()
    st.session_state["_schema_index"] = schema_index

    # --- sidebar
    with st.sidebar:
        st.markdown("<div class='nl-side-h'>NL→SQL</div>", unsafe_allow_html=True)
        _render_lang_toggle()

        st.markdown(
            f"<div class='nl-side-sub'>{_t('db_label')}</div>",
            unsafe_allow_html=True,
        )
        db_ids = registry.ids()
        if not db_ids:
            st.error("No databases registered. Run scripts/download_data.py first.")
            st.stop()
        default_idx = (
            db_ids.index("bird_california_schools") if "bird_california_schools" in db_ids else 0
        )
        db_id = st.selectbox(
            _t("db_label"), db_ids, index=default_idx, label_visibility="collapsed"
        )
        spec = registry.get(db_id)
        st.caption(f"{_t('db_dialect')}: `{spec.dialect}`")
        if spec.description:
            st.caption(spec.description)

        link = _source_link_for(db_id)
        if link is not None:
            label, url = link
            st.caption(f"{_t('db_source')}: [{label}]({url})")

        _render_schema_explorer(db_id)

        st.markdown(
            f"<div class='nl-side-sub'>{_t('mode_header')}</div>",
            unsafe_allow_html=True,
        )
        mode = st.radio(
            _t("mode_header"),
            options=(_t("mode_accurate"), _t("mode_fast"), _t("mode_debug")),
            index=0,
            captions=(
                _t("mode_accurate_caption"),
                _t("mode_fast_caption"),
                _t("mode_debug_caption"),
            ),
            label_visibility="collapsed",
        )
        if mode == _t("mode_fast"):
            fewshot_top_k = 0
            verify_retry_on_empty = False
        else:
            fewshot_top_k = 3
            verify_retry_on_empty = True

        with st.expander(_t("advanced_header"), expanded=False):
            schema_top_k = st.slider(_t("schema_top_k"), 1, 10, 5)
            fk_hops = st.slider(_t("fk_hops"), 0, 2, 1)
            table_budget = st.slider(_t("table_budget"), 4, 20, 12)
            sort_schema_block = st.checkbox(_t("sort_schema"), value=True)
            extended_sample_size = st.slider(_t("sample_size"), 0, 8, 0)

        st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)
        if st.button(_t("clear_chat"), use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        _render_welcome(db_id)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                _replay_assistant_turn(msg)

    typed = st.chat_input(_t("ask_placeholder"))
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
        fewshot_top_k=fewshot_top_k,
        verify_retry_on_empty=verify_retry_on_empty,
    )

    with st.chat_message("assistant"):
        with st.spinner(_t("spinner_generating")):
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
                st.error(_t("pipeline_crashed", kind=type(exc).__name__, msg=str(exc)))
                st.session_state.messages.append(
                    {"role": "assistant", "error": str(exc), "question": question}
                )
                return
            wall_ms = (time.perf_counter() - t0) * 1000

        _render_output(result.output_format, caption=result.caption)

        if result.sql:
            st.markdown(f"**{_t('sql_label')}**")
            st.code(result.sql, language="sql")
        else:
            st.warning(_t("no_sql"))

        st.caption(_t("wall_model", wall=wall_ms, model=sql_provider.model))

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
    if msg.get("error"):
        st.error(_t("pipeline_crashed", kind="prior", msg=msg["error"]))
        return
    result = cast(PipelineRunResult, msg["result"])
    _render_output(result.output_format, caption=result.caption)
    if result.sql:
        st.code(result.sql, language="sql")
    st.caption(_t("wall_model", wall=msg.get("wall_ms", 0), model=msg.get("model", "?")))
    _render_show_working(result)


if __name__ == "__main__":
    main()
