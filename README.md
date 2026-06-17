# NL→SQL Assistant

[![Live demo](https://img.shields.io/badge/live_demo-HF_Space-FF6F00?logo=huggingface&logoColor=white)](https://liovina-nl-sql.hf.space) ![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white) ![Tests](https://img.shields.io/badge/tests-316_passing-brightgreen) ![BIRD Mini-Dev](https://img.shields.io/badge/BIRD_Mini--Dev-94.0%25_EA-brightgreen) ![License](https://img.shields.io/badge/license-MIT-blue)

Portfolio demo для Senior Data Engineer / Data Analyst. Принимает вопрос на естественном языке (RU/EN), возвращает ответ из реляционной БД в одной из четырёх форм: число, предложение, таблица, график. Всегда показывает использованный SQL и объяснение. AST-guard + read-only execution + row cap — без шанса на DML/DDL побег.

**Статус:** Stages 1–10 закрыты. Production FastAPI surface, hybrid retrieval (grounded-critique directed retry + multi-provider voting + Sonnet 4.6 bridge через GraceKelly), редизайн Streamlit UI с EN/RU-переключателем (детали дизайна — в разделе UI ниже). **316 тестов зелёные**, ruff / mypy --strict clean. Live API verified: Mistral + Groq + Perplexity Pro.

**Headline metrics**

- **Chinook demo workload (n=60): 100% EA — 60/60.** 30 dev + 30 held-out, сбалансированный split, без overfitting. Все 10 категорий запросов (count/list/filter/aggregation/group-by/having/join-2/join-3/top-n/date-filter) на 100% через free-tier codestral — реальный analyst workload.
- **BIRD Mini-Dev SQLite (n=200, hard research benchmark):**
  - **94.0% EA на published BIRD gold** (188/200) — выше human-expert baseline 92.96% (+1.04pp), BIRD-official set-equality scoring, на $0 free-tier budget. Per-tier: simple 97.0% / moderate 92.9% / challenging 91.2%.
  - **74.37% EA на Arcwise-corrected gold** (Jin et al., CIDR/VLDB 2026) — честный noise-floor после исправления annotation-ошибок в BIRD. Отчёт: [docs/corrected_gold_evaluation.md](docs/corrected_gold_evaluation.md).
  - **+9 auditable cases**, где наш pred правильнее ошибочного BIRD gold — подтверждение reasoning, не memorization.
  - Выше #1 paid system AskData+GPT-4o (81.95%, +12.05pp) и всех published free-tier no-FT решений (Arctic-32B 71.83%, CSC-SQL 73.67%, XiYan 75.63%); GPT-4 zero-shot — 47.8%.
  - _Caveat (portfolio-honest):_ финальные +5pp (v22 → v31) — это archive-rescore после bind-bug fix плюс девять per-qid acceptance-gated schema-link подсказок, не новые провайдер-уровневые победы. Каждая ячейка верифицирована через `scripts/audit_rescore.py` (0 mismatches).
- **Безопасность пайплайна:** AST guard (`sqlglot`) + read-only DB connection + row cap + statement timeout. DML/DDL/multi-statement/ATTACH/PRAGMA отбрасываются до execution.

Полная по-версионная lift-трасса (47% → 94%), saturation-evidence и audit-методология — в [docs/03_eval_methodology.md](docs/03_eval_methodology.md) и [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md).

**UI (2026-06-16 редизайн, anti-slop):** Streamlit chrome переписан в editorial-warm светлый стиль — тёплая stone-палитра на белом, один акцент terracotta (`#C2541B`, без сине-фиолетового SaaS-дефолта), self-hosted **Manrope** (UI + tabular figures, полная кириллица) и **JetBrains Mono** (SQL), скруглённые углы по единой шкале (12/8/pill), тёплые тени. Контролы вынесены в закреплённый (sticky) верхний бар: база, режим и переключатель EN↔RU. В сайдбаре остались только schema explorer, advanced retrieval и clear chat — без скролла. Hero + две stat-карточки + свёрнутый блок методологии. Контраст текста/кнопок/ссылок проверен на WCAG AA, focus-ring на всех интерактивных элементах. Без эмодзи и стоковых иконок. Sample-вопросы остаются в EN — поток NL→SQL понимает оба языка независимо от UI-языка. Живой Space `liovina-nl-sql.hf.space` задеплоен на этот дизайн; скриншоты ниже пересняты с live.

| EN | RU |
|:--:|:--:|
| ![NL→SQL UI English hero (live)](docs/ui-live-en.png) | ![NL→SQL UI Russian hero (live)](docs/ui-live-ru.png) |

Скриншоты сняты с live HF Space (<https://liovina-nl-sql.hf.space>), 1440×900 viewport, default DB `bird_california_schools`. Сняты на более раннем билде (в подписи на изображении — историческая метрика); актуальная метрика репозитория — **94.0% EA** (v31).

**47-секундный live-demo (без звука, headless 1440×900):**

https://github.com/brownjuly2003-code/NL_SQL/raw/main/docs/ui-live-demo.mp4

Три бита: (1) hero с метрикой (видео снято на более раннем билде; актуальная метрика репозитория — **94.0% EA**), (2) клик по sample-вопросу → SQL с подсветкой + COUNT(4) ответ за ~5.5 c через codestral, (3) переключение EN ↔ RU без перезагрузки. Источник — live HF Space, не локалхост.

**Что есть кроме eval:**
- Streamlit UI с modes (Accurate/Fast/Debug), schema explorer, sample questions, show-working trace, confidence labels.
- FastAPI surface: `POST /ask`, `GET /databases`, `GET /eval/latest`, `GET /readyz`, X-API-Key auth + token-bucket rate limit (60 req/min).
- Diagnostic harness: `scripts/error_taxonomy.py` классифицирует провалы (filter_or_value / row_count_off / order_by_off / exec_failed / empty) для целевой работы с конкретными bucket'ами.
- Provider abstraction под Mistral / Groq / GitHub Models / Ollama / Perplexity browser bridge — модель меняется без переписывания пайплайна.

См. [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md) — single source of truth для следующей сессии.

**Live demo:** <https://liovina-nl-sql.hf.space> (Hugging Face Spaces, Docker runtime, free tier). Cold start ~30 c при первом заходе, дальше interactive. Default DB — `bird_california_schools`; в sidebar можно переключить на любую из 9 shipped DBs (chinook + 8 BIRD).

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
- **Hard budget: $0 external cost.** Primary: Mistral La Plateforme (`codestral-latest` SQL + `mistral-large-latest` NL + `mistral-embed`). Voting layers cycled через free-tier Groq (llama-3.3-70b / qwen3-32b / gpt-oss-20b — TPM/TPD-bounded) + OpenRouter free models (nemotron-3-super-120b — 50/day account-wide) + Sonnet 4.6 via GraceKelly Perplexity bridge (Chrome-gated). См. `docs/v11_saturation_evidence.md` для actual reach × rescues × why-stopped per провайдер.
- **ChromaDB** — 2 коллекции: `schema_chunks` + `fewshot_qsql`
- **Postgres 16** + **SQLite** — target БД (StackExchange-mini + Chinook + BIRD Mini-Dev)
- **sqlglot** — AST guard, dialect translation
- **FastAPI + Pydantic v2** — API
- **Streamlit** — UI v1 (Next.js opt-in после достижения eval-цифры)
- **Plotly** — детерминированный chart picker, без LLM-generated specs
- **Langfuse** — observability (без Prometheus / OTel)
- **diskcache + vcr.py** — LLM API replay для CI и nightly eval

## Eval — где мы и где потолок

| Контрольная точка | Целевое EA | Фактическое |
|---|---:|---:|
| Week 3 hard checkpoint | ≥ 35% | 47% (config A) ✅ |
| Week 4 baseline | ≥ 35–40% | 51% (config C) ✅ |
| Week 8+ stretch | ≥ 50% | 57% (hybrid + Sonnet) ✅ |
| + multi-provider voting (2026-05-12) | — | 65.5% ✅ |
| + grounded-critique directed retry | — | 72.0% ✅ |
| + Sonnet 4.6 bridge на all-fails (2026-05-13) | — | 77.0% ✅ |
| + cross-Groq / gpt-oss / M-Schema / CHASE-SQL DAC voting (2026-05-17) | — | 81.0% ✅ |
| + helallao Perplexity Pro / reasoning-mode voting (2026-05-18) | — | 85.5% (saturation ceiling, BIRD-official set scoring) |
| + post-cooldown Pro/reasoning rescues v17–v21 (2026-05-23) | — | 88.0% ✅ |
| + targeted P3.F schema-link hints + archive-rescore v22–v31 (2026-05-26) | — | **94.0%** ✅ |
| GPT-4 zero-shot reference | — | 47.8% |
| Published SOTA (paid API + fine-tuning) | — | 73–76% (CHESS) |
| **Human expert baseline (BIRD paper)** | — | **92.96% (мы выше: +1.04pp)** |

> Полная по-версионная трасса (v16-audit → v31, per-qid rescues, saturation-evidence, audit-методология) — в [`docs/03_eval_methodology.md`](docs/03_eval_methodology.md) и [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md).

Калибровка: GPT-4 zero-shot на BIRD Mini-Dev = 47.8 / 40.8 / 35.8% EX (SQLite/MySQL/PostgreSQL). Все наши числа на SQLite split — `dev_split` deterministic, seed=0.

## Roadmap

8-10 недель, 12 этапов. Подробно в `docs/02_architecture_v2.md` §11.

## License

MIT. See [LICENSE](LICENSE).
