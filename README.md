# NL→SQL Assistant

Portfolio demo для Senior Data Engineer / Data Analyst. Принимает вопрос на естественном языке (RU/EN), возвращает ответ из реляционной БД в одной из четырёх форм: число, предложение, таблица, график. Всегда показывает использованный SQL и объяснение.

**Статус:** stages 1-6 + 9 + 10 (Streamlit UI) закрыты (2026-05-10 follow-up). 200 тестов зелёные, ruff/mypy strict clean. Live API verified: Mistral + Groq. n=200 ablation: A=47.0% / C+sort+s=3=47.0% / C+sort+s=5=46.0% — at-or-above GPT-4 zero-shot reference (47.8%). См. [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md) — single source of truth для следующей сессии.

**Streamlit Cloud:** https://brownjuly2003-code-nl-sql-appstreamlit-app-ptwp4f.streamlit.app/ — пока редиректит на Streamlit OAuth/login; финальный ручной deploy-шаг описан в [`docs/SESSION_HANDOFF.md` § Deploy](docs/SESSION_HANDOFF.md#deploy--finishing-it-manually-resume-here). Repo + data + deps готовы.

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

## Eval target

| Контрольная точка | Цель |
|---|---|
| Week 3 (hard checkpoint) | Execution Accuracy ≥ 35% на BIRD Mini-Dev SQLite split — иначе scope-down |
| Week 4 (baseline) | EA ≥ 35-40% |
| Week 8+ (stretch) | EA ≥ 50% |

Калибровка: GPT-4 zero-shot на BIRD Mini-Dev = 47.8 / 40.8 / 35.8% EX (SQLite/MySQL/PostgreSQL).

## Roadmap

8-10 недель, 12 этапов. Подробно в `docs/02_architecture_v2.md` §11.

## License

MIT (TBD).
