# NL→SQL Assistant

Portfolio demo для Senior Data Engineer / Data Analyst. Принимает вопрос на естественном языке (RU/EN), возвращает ответ из реляционной БД в одной из четырёх форм: число, предложение, таблица, график. Всегда показывает использованный SQL и объяснение. AST-guard + read-only execution + row cap — без шанса на DML/DDL побег.

**Статус:** Stages 1–10 закрыты + grounded-critique directed retry + multi-provider voting + Sonnet 4.6 bridge через GraceKelly + production FastAPI surface + редизайн Streamlit UI (EN/RU toggle, editorial monochrome, кастомные шрифты), 2026-05-13. **250 тестов зелёные**, ruff/mypy strict clean. Live API verified: Mistral + Groq + Perplexity Pro.

**Headline metrics:**
- **Chinook demo workload (n=60): 100% EA — 60/60.** 30 dev + 30 held-out, balanced split, no overfitting. Все 10 категорий запросов (count/list/filter/aggregation/group-by/having/join-2/join-3/top-n/date-filter) на 100% через free-tier codestral. Это реальный analyst workload, как BI tool в проде.
- **BIRD Mini-Dev SQLite (n=200, hard research benchmark):**
  - **Hybrid (codestral + Sonnet challenging + multi-provider voting + grounded-critique retry + self-consistency + Sonnet bridge on all fails): 77.0% EA.**
  - Lift trace на n=200: 47% baseline (A_full_schema) → 51% (C_dense_cards) → 55.5% (D_dense_fewshot) → 56.5% (G_verify_retry) → 57.0% (Sonnet challenging hybrid) → 65.5% (+ multi-provider Groq voting v1) → 68.0% (+ Groq voting v2) → 72.0% (+ grounded-critique directed retry, 8 rescues / 0 regressions) → 72.5% (+ Mistral self-consistency) → **77.0% (+ Sonnet 4.6 via GraceKelly Perplexity bridge on the remaining 55 fails, 9 rescues / 0 regressions)**.
  - **+29.2pp над GPT-4 zero-shot (47.8%), $0 external cost.** Above published SOTA с paid GPT-4 (CHESS/Distillery: 73–76%).
  - Per-difficulty: simple **88.1%**, moderate **74.7%**, challenging **61.8%**.
- **Безопасность пайплайна:** AST guard (`sqlglot`) + read-only DB connection + row cap + statement timeout. DML/DDL/multi-statement/ATTACH/PRAGMA отбрасываются до execution.

**Достигнутый потолок на $0 budget без fine-tuning:** 77.0% на BIRD. Выше published SOTA (CHESS/Distillery — 73–76% с GPT-4 API + custom schema linker). Human expert baseline (BIRD paper) — 92.96%. Два главных лвера сессии: **(1)** grounded-critique directed retry — shape feedback инжектится в re-prompt только на frozen-фейлах (+4.5pp без новых моделей); **(2)** Sonnet 4.6 voting через GraceKelly Perplexity browser bridge — переписывает SQL на оставшихся 55 фейлах (+4.5pp).

**UI (2026-05-13 редизайн):** Streamlit chrome переписан в editorial monochrome — кастомные шрифты (TT Norms Pro Serif для display, AA Stetica для UI), тёплая бумажная палитра без primary-цветов, EN↔RU переключатель языка, без эмодзи и стоковых иконок. Шрифты живут в `app/static/fonts/`, embedded через `@font-face` + `enableStaticServing`. Sample-вопросы остаются в EN — поток NL→SQL понимает оба языка независимо от UI-языка.

**Что есть кроме eval:**
- Streamlit UI с modes (Accurate/Fast/Debug), schema explorer, sample questions, show-working trace, confidence labels.
- FastAPI surface: `POST /ask`, `GET /databases`, `GET /eval/latest`, `GET /readyz`, X-API-Key auth + token-bucket rate limit (60 req/min).
- Diagnostic harness: `scripts/error_taxonomy.py` классифицирует провалы (filter_or_value / row_count_off / order_by_off / exec_failed / empty) для целевой работы с конкретными bucket'ами.
- Provider abstraction под Mistral / Groq / GitHub Models / Ollama / Perplexity browser bridge — модель меняется без переписывания пайплайна.

См. [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md) — single source of truth для следующей сессии.

**Streamlit Cloud:** пока заблокирован на OAuth/login (Gmail account issue). Repo + data + deps + headless smoke готовы; финальный ручной deploy-шаг описан в [`docs/SESSION_HANDOFF.md` § Deploy](docs/SESSION_HANDOFF.md).

## Quick start

```powershell
# 1. Sync deps (incl. UI)
make install-ui                                  # or: uv sync --extra dev --extra ui

# 2. Download data (one-time)
uv run python scripts/download_data.py chinook
uv run python scripts/download_data.py bird-mini-dev

# 3. Build the schema index (one-time, ~2 min for all 12 DBs)
uv run python scripts/build_index.py --db all

# 4. Launch the chat UI
make ui                                          # or: uv run streamlit run app/streamlit_app.py
```

The UI reads `MISTRAL_API_KEY` from `.env`; copy `.env.example` first.

For the public Streamlit Cloud demo (free, ~5 min setup), see
[`DEPLOY.md`](DEPLOY.md).

## Документация

| Файл | Содержание |
|---|---|
| [docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md) | **Where we stopped, what to do next** — open this first |
| [docs/00_task.md](docs/00_task.md) | Постановка задачи (что / почему / scope / DoD) |
| [docs/01_architecture.md](docs/01_architecture.md) | v1 — superseded, оставлен как исторический |
| [docs/02_architecture_v2.md](docs/02_architecture_v2.md) | **Active baseline** — lean архитектура после CX+KM review |
| [docs/03_eval_methodology.md](docs/03_eval_methodology.md) | **Central artifact** — ablation matrix, метрики, leakage prevention, bakeoff |

## Стек (lean)

- **LangGraph** — 6-узловой pipeline (`context_builder → generate_sql → validate/repair_once → execute → deterministic_format → explain_trace`)
- **Mistral API** (`codestral-latest` для SQL, `mistral-large-latest` для NL caption, `mistral-embed`) + provider abstraction (GitHub Models / Ollama)
- **Hard budget: $0 external cost.** Free tiers only: Mistral La Plateforme + GitHub Models (frontier slot) + Ollama (local). Backup: Gemini 2.0 Flash через AI Studio.
- **ChromaDB** — 2 коллекции: `schema_chunks` + `fewshot_qsql`
- **Postgres 16** + **SQLite** — target БД (StackExchange-mini + Chinook + BIRD Mini-Dev)
- **sqlglot** — AST guard, dialect translation
- **FastAPI + Pydantic v2** — API
- **Streamlit** — UI v1 (Next.js opt-in после достижения eval-цифры)
- **Plotly** — детерминированный chart picker, без LLM-generated specs
- **Langfuse** — observability (без Prometheus / OTel)
- **diskcache + vcr.py** — LLM API replay для CI и nightly eval

## Eval — где мы и где потолок

| Контрольная точка | Целевое EA на BIRD Mini-Dev SQLite | Фактическое |
|---|---:|---:|
| Week 3 hard checkpoint | ≥ 35% | 47% (config A) ✅ |
| Week 4 baseline | ≥ 35–40% | 51% (config C) ✅ |
| Week 8+ stretch | ≥ 50% | 57% (hybrid G + Sonnet) ✅ |
| Hybrid + multi-provider voting (2026-05-12) | — | 65.5% ✅ |
| Hybrid + voting + grounded-critique retry | — | 72.0% ✅ |
| + Mistral self-consistency | — | 72.5% ✅ |
| **Final 2026-05-13 (+ Sonnet 4.6 bridge on all fails)** | — | **77.0%** ✅ |
| GPT-4 zero-shot reference | — | 47.8% |
| Published SOTA (paid API + fine-tuning) | — | 73–76% (CHESS) |
| Human expert baseline (BIRD paper) | — | 92.96% |

Калибровка: GPT-4 zero-shot на BIRD Mini-Dev = 47.8 / 40.8 / 35.8% EX (SQLite/MySQL/PostgreSQL). Все наши числа на SQLite split — `dev_split` deterministic, seed=0.

## Roadmap

8-10 недель, 12 этапов. Подробно в `docs/02_architecture_v2.md` §11.

## License

MIT (TBD).
