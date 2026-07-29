# NL→SQL Assistant

[![Demo paused](https://img.shields.io/badge/demo-paused-lightgrey?logo=huggingface)](https://liovina-nl-sql.hf.space) [![CI](https://github.com/brownjuly2003-code/NL_SQL/actions/workflows/ci.yml/badge.svg)](https://github.com/brownjuly2003-code/NL_SQL/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white) ![BIRD Mini-Dev](https://img.shields.io/badge/BIRD_Mini--Dev-61.5%25_reproducible-brightgreen) ![License](https://img.shields.io/badge/license-MIT-blue)

Portfolio demo для Senior Data Engineer / Data Analyst. Принимает вопрос на естественном языке (RU/EN), возвращает ответ из реляционной БД в одной из четырёх форм: число, предложение, таблица, график. Всегда показывает использованный SQL и объяснение. AST-guard + read-only execution + row cap — без шанса на DML/DDL побег.

**Статус:** closure candidate; Stages 1–10 закрыты и scope заморожен.
Production FastAPI surface, retrieval-augmented LangGraph pipeline, редизайн
Streamlit UI с EN/RU-переключателем. Тесты, ruff и mypy --strict гоняются в CI.
Финальные критерии: [docs/PROJECT_CLOSURE.md](docs/PROJECT_CLOSURE.md).
Публичный HF Space сейчас `PAUSED` / `Flagged as abusive` (`Cloudflared`), поэтому
live-доступ не заявляется.

**Headline metric — два воспроизводимых уровня (BIRD Mini-Dev SQLite, n=200, $0 free-tier)**

Одно число вводило бы в заблуждение, поэтому метрика разложена по слоям. В продукт (Streamlit UI и `/ask`) входит только уровень 1.

| Уровень | EA | Что это | В продукте? | Воспроизводится? |
|---|---:|---|:--:|:--:|
| **1. Reproducible single-run** | **61.5%** | Чистый пайплайн на free-tier codestral, один прогон, без голосования и подсказок (123/200). | ✅ да | ✅ одной командой |
| **2. + per-question schema-link hints** | **62.5%** | Тот же прогон с флагом `--bird-rescue-hints` (125/200): 11 hint-блоков под annotation-quirks конкретных BIRD-вопросов. Кодирует ответы к тесту — **в продукте выключен** (`enable_bird_rescue_hints`, off). | ❌ eval | ✅ одной командой |

Уровень 1 — first-pass 59.5%, per-tier simple 76.1% / moderate 58.6% / challenging 41.2% ([`eval/baselines/reproducible_n200.json`](eval/baselines/reproducible_n200.json), отдаётся `GET /eval/latest`).

```powershell
# Уровень 1 (одна команда, детерминированный split, seed=0):
uv run python scripts/eval_baseline.py --config E --n 200            # → 61.5%
# Уровень 2 (hint-assisted, eval-only) — тот же прогон с флагом:
uv run python scripts/eval_baseline.py --config E --n 200 --bird-rescue-hints   # → 62.5%
```

В архиве проекта лежат также eval-only композиции: накопительные merge'и примерно двух десятков прогонов разных провайдеров поверх тех же per-question подсказок. Они **не являются конфигурацией пайплайна**, не воспроизводятся ни одной командой (часть шла через Perplexity-мост, которого больше нет) и в метрику продукта не входят — поэтому здесь не приводятся. Полный разбор с числами и артефактами — в [методологии](docs/03_eval_methodology.md), раздел 13.

**Единственный живой рычаг качества — сила генератора.** Тот же пайплайн на бесплатном `mimo-v2.5-free` даёт **68.5%**, на `claude-opus-4-8` (effort=max) — **79.5%**; при этом шесть подряд литературных приёмов (CHESS, DAIL, CHASE, E-SQL и др.), реализованных и измеренных по одному на прогон, дали от −0.5 до −9.5 п.п. Разбор — [анатомия потолка](docs/ceiling_anatomy.md): коридор разметки ±16.6 п.п., метрика «чинит/ломает» на бесспорной земле, стена из 32 вопросов и почему её не берёт никто.

- **Chinook demo workload (n=60): 100% EA — 60/60.** 30 dev + 30 held-out, сбалансированный split. Все 10 категорий (count/list/filter/aggregation/group-by/having/join-2/join-3/top-n/date-filter) через free-tier codestral — реальный analyst workload.
- **60.3% EA на Arcwise-corrected gold** (120/199) — тот же продуктовый прогон, судимый по исправленной разметке Jin et al. (CIDR/VLDB 2026). Расхождение с 61.5% меньше собственного шума бенчмарка: вердикт по 33 вопросам из 199 зависит только от того, какой разметке верить. Разбор — [анатомия потолка](docs/ceiling_anatomy.md); архивные прогоны на исправленном gold — [docs/corrected_gold_evaluation.md](docs/corrected_gold_evaluation.md).
- **Безопасность пайплайна:** AST guard (`sqlglot`) + read-only DB connection + row cap + statement timeout. DML/DDL/multi-statement/ATTACH/PRAGMA/`SELECT … INTO` отбрасываются до execution.

Полная по-версионная lift-трасса, saturation-evidence и audit-методология — в [docs/03_eval_methodology.md](docs/03_eval_methodology.md).

**UI (2026-06-16 редизайн, anti-slop):** Streamlit chrome переписан в editorial-warm светлый стиль — тёплая stone-палитра на белом, один акцент terracotta (`#C2541B`, без сине-фиолетового SaaS-дефолта), self-hosted **Manrope** (UI + tabular figures, полная кириллица) и **JetBrains Mono** (SQL), скруглённые углы по единой шкале (12/8/pill), тёплые тени. Контролы вынесены в закреплённый (sticky) верхний бар: база, режим и переключатель EN↔RU. В сайдбаре остались только schema explorer, advanced retrieval и clear chat — без скролла. Hero + две stat-карточки + свёрнутый блок методологии. Контраст текста/кнопок/ссылок проверен на WCAG AA, focus-ring на всех интерактивных элементах. Без эмодзи и стоковых иконок. Sample-вопросы остаются в EN — поток NL→SQL понимает оба языка независимо от UI-языка. Скриншоты ниже сняты с ранее работавшего Space; текущий Space paused.

| EN | RU |
|:--:|:--:|
| ![NL→SQL UI English hero (live)](docs/ui-live-en.png) | ![NL→SQL UI Russian hero (live)](docs/ui-live-ru.png) |

Скриншоты сняты с live HF Space (<https://liovina-nl-sql.hf.space>), 1440×900 viewport, default DB `bird_california_schools`. Сняты на более раннем билде (в подписи на изображении — историческая метрика); актуальная метрика — см. таблицу трёх уровней выше.

**47-секундный live-demo (без звука, headless 1440×900):**

https://github.com/brownjuly2003-code/NL_SQL/raw/main/docs/ui-live-demo.mp4

Три бита: (1) hero с метрикой (видео снято на более раннем билде; актуальная метрика — см. таблицу выше), (2) клик по sample-вопросу → SQL с подсветкой + COUNT(4) ответ за ~5.5 c через codestral, (3) переключение EN ↔ RU без перезагрузки. Источник — live HF Space, не локалхост.

**Что есть кроме eval:**
- Streamlit UI с modes (Accurate/Fast/Debug), schema explorer, sample questions, show-working trace, confidence labels.
- FastAPI surface: `POST /ask`, `GET /databases`, `GET /eval/latest`, `GET /readyz`, X-API-Key auth + token-bucket rate limit (60 req/min).
- Diagnostic harness: `scripts/error_taxonomy.py` классифицирует провалы (filter_or_value / row_count_off / order_by_off / exec_failed / empty) для целевой работы с конкретными bucket'ами.
- Provider abstraction под Mistral / Groq / GitHub Models / Ollama / Perplexity browser bridge — модель меняется без переписывания пайплайна.

**Deployment status:** public Space <https://liovina-nl-sql.hf.space> существует,
но сейчас paused/flagged и не является live demo. Когда Space работал, default DB
была `bird_california_schools`, а selector содержал 9 shipped DBs.

## Quick start

Two tiers: **(A) clone-first** (fastest first run) and **(B) full local rebuild** (all 12 DBs).

### Full-source local demo (recommended instead of the paused HF Space)

This path runs the original checkout directly: **all 12 registered SQLite DBs**,
both Chroma collections, and the normal product pipeline
(`mistral` / `codestral-latest` by default). It does not use the filtered HF
publish set, alter source files, or put the API key in a command argument.
At runtime it uses a temporary byte-for-byte Chroma copy, so Chroma housekeeping
does not dirty the tracked source index.

Complete the dependency and `.env` steps in (A), the full data steps in (B),
then run:

```powershell
# Read-only local preflight: verifies the key is configured, all 12 DBs exist,
# and the Chroma schema index covers all 12. It makes no API request.
uv run python scripts/run_local_demo.py --check

# Serve the complete source checkout on loopback only.
uv run python scripts/run_local_demo.py
# Open http://127.0.0.1:8501
```

Keep your own `MISTRAL_API_KEY` in the gitignored `.env` or the current process
environment. The launcher never prints it. Provider calls use your account and
quota; local SQLite queries remain read-only.

### A. Clone-first (fastest)

Requires **Python 3.13**.

A tracked clone already includes **9 SQLite DBs** (chinook + 8 BIRD slices under GitHub's size limit) plus a **prebuilt Chroma** index in `chroma_data/`. No download or reindex is needed for the first run.

```powershell
# 1. Sync deps (incl. UI)
uv sync --extra dev --extra ui
# or: make install-ui

# 2. Env file — supply your own MISTRAL_API_KEY in `.env`
Copy-Item .env.example .env          # PowerShell
# cp .env.example .env               # Unix / Git Bash

# 3. Launch the chat UI
uv run streamlit run app/streamlit_app.py
# or: make ui
```

`MISTRAL_API_KEY` is required for embeddings (`mistral-embed`). Supply your own Mistral key;
external API calls are subject to your provider quotas (not claimed free here).

Choose SQL generation independently in `.env` with
`NL_SQL_DEFAULT_PROVIDER=mistral|github_models|groq|ollama`. Hosted alternatives
use your matching `GITHUB_TOKEN` or `GROQ_API_KEY`; Ollama needs no generation
key but must be running with `NL_SQL_OLLAMA_GEN_MODEL` pulled. This setting
changes SQL/explanation generation only—query embeddings still use Mistral.

Postgres is optional (local/CI). The public HF Space is SQLite-only.

### B. Full local rebuild (12 DBs)

Download data and rebuild the schema index for all 12 DBs:

```powershell
# Download data (one-time)
uv run python scripts/download_data.py chinook
uv run python scripts/download_data.py bird-mini-dev

# Build the schema index (one-time, ~2 min for all 12 DBs)
uv run python scripts/build_index.py --db all
```

Then launch the UI as in (A).

Публичный демо — Hugging Face Space (Docker). Как он деплоится (tracked-only + prune),
см. [`DEPLOY.md`](DEPLOY.md).

## Документация

| Файл | Содержание |
|---|---|
| [docs/BACKLOG.md](docs/BACKLOG.md) | Живой трекер: что сделано, что gated, что won't-fix |
| [docs/00_task.md](docs/00_task.md) | Постановка задачи (что / почему / scope / DoD) |
| [docs/01_architecture.md](docs/01_architecture.md) | v1 — superseded, оставлен как исторический |
| [docs/02_architecture_v2.md](docs/02_architecture_v2.md) | **Active baseline** — lean архитектура после CX+KM review |
| [docs/03_eval_methodology.md](docs/03_eval_methodology.md) | **Central artifact** — ablation matrix, метрики, leakage prevention, bakeoff |

## Стек (lean)

- **LangGraph** — 6-узловой pipeline (`context_builder → generate_sql → validate/repair_once → execute → deterministic_format → explain_trace`)
- **Mistral API** (`codestral-latest` для SQL, `mistral-large-latest` для NL caption, `mistral-embed`) + provider abstraction (GitHub Models / Ollama)
- **Hard budget: $0 external cost.** Primary: Mistral La Plateforme (`codestral-latest` SQL + `mistral-large-latest` NL + `mistral-embed`). Voting layers cycled через free-tier Groq (llama-3.3-70b / qwen3-32b / gpt-oss-20b — TPM/TPD-bounded) + OpenRouter free models (nemotron-3-super-120b — 50/day account-wide) + Sonnet 4.6 via GraceKelly Perplexity bridge (Chrome-gated). См. `docs/v11_saturation_evidence.md` для actual reach × rescues × why-stopped per провайдер.
- **ChromaDB** — 2 коллекции: `schema_chunks` + `fewshot_qsql`
- **SQLite** (read-only) — target БД по умолчанию: Chinook + 11 BIRD Mini-Dev slices локально (вся eval на SQLite); на live Space — 9 (три самых больших > 100 MB/файл, см. DEPLOY.md).
- **Postgres 16** — второй backend с genuinely read-only транзакциями (execution-option, не роль-плацебо); запускается локально через `docker-compose.yml` (profile `postgres`). **Прогнан, а не только заявлен:** `codebase_community` (StackExchange-mini, 741 646 строк) залит из официального BIRD PG-дампа (`scripts/extract_pg_dump_slice.py`), и тот же пайплайн на BIRD-овском **Postgres-gold** даёт **49.0% EA (24/49)** против 44.9% на SQLite для тех же вопросов, validity 100% — движок переносим. Живой прогон нашёл два бага, невидимых на SQLite (`%` в `LIKE` ронял psycopg-путь; `Decimal` из `numeric` занижал скоринг) — оба починены, см. `docs/03_eval_methodology.md` §14. Read-only enforcement проверяется на живом PG16 в CI. На HF Space не тянется (SQLite-only деплой).
- **sqlglot** — AST guard, dialect translation
- **FastAPI + Pydantic v2** — API (X-API-Key + безусловный token-bucket rate-limit)
- **Streamlit** — UI
- **Plotly** — детерминированный chart picker, без LLM-generated specs
- **diskcache** — кэш LLM generate/embed ответов (используется и для быстрого детерминированного прогона eval)

## Eval — где мы и где потолок

| Контрольная точка | Целевое EA | Фактическое |
|---|---:|---:|
| Week 3 hard checkpoint | ≥ 35% | 47% (config A) ✅ |
| Week 4 baseline | ≥ 35–40% | 51% (config C) ✅ |
| Week 8+ stretch | ≥ 50% | 57% (hybrid + Sonnet) ✅ |
| **Продуктовый пайплайн** (codestral, одна команда) | — | **61.5%** ✅ |
| Тот же пайплайн, лучший бесплатный генератор (`mimo-v2.5-free`) | — | **68.5%** |
| Тот же пайплайн, `claude-opus-4-8` (effort=max) | — | **79.5%** |
| GPT-4 zero-shot reference | — | 47.8% |
| Published SOTA (paid API + fine-tuning) | — | 73–76% (CHESS) |
| Human expert baseline (BIRD paper) | — | 92.96% |

Все три верхние строки — **один и тот же пайплайн**, отличается только генератор: это и есть главный вывод проекта (см. [анатомию потолка](docs/ceiling_anatomy.md)). Опубликованы они как исследовательские точки: `claude-opus-4-8` едет на личной подписке и в HF Space не вызывается, поэтому продуктовое число — 61.5%.

Судить эти числа по одному лишь EA не стоит: у BIRD-разметки собственный коридор **±16.6 п.п.** (33 вопроса из 199 меняют вердикт от одной лишь переразметки gold). Устойчивая метрика — «чинит/ломает» на вопросах, где обе разметки согласны.

Кроме этого, в архиве проекта есть eval-only композиции — merge'и многих прогонов разных провайдеров поверх per-question подсказок. Они не воспроизводятся и не являются конфигурацией пайплайна, поэтому в таблице выше их нет; разбор с числами — в методологии.

> Полная по-версионная трасса, per-qid rescues, saturation-evidence и audit-методология — в [`docs/03_eval_methodology.md`](docs/03_eval_methodology.md).

Калибровка: GPT-4 zero-shot на BIRD Mini-Dev = 47.8 / 40.8 / 35.8% EX (SQLite/MySQL/PostgreSQL). Все наши числа на SQLite split — `dev_split` deterministic, seed=0.

## Roadmap

Stages 1–10 закрыты (см. статус выше). Дальнейшие этапы и архитектурный контекст — `docs/02_architecture_v2.md` §11.

## License

MIT. See [LICENSE](LICENSE).
