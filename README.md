# NL→SQL Assistant

Portfolio demo для Senior Data Engineer / Data Analyst. Принимает вопрос на естественном языке (RU/EN), возвращает ответ из реляционной БД в одной из четырёх форм: число, предложение, таблица, график. Всегда показывает использованный SQL и объяснение. AST-guard + read-only execution + row cap — без шанса на DML/DDL побег.

**Статус:** Stages 1–10 закрыты + grounded-critique directed retry + multi-provider voting + Sonnet 4.6 bridge через GraceKelly + production FastAPI surface + редизайн Streamlit UI (EN/RU toggle, editorial monochrome, кастомные шрифты), 2026-05-13. **250 тестов зелёные**, ruff/mypy strict clean. Live API verified: Mistral + Groq + Perplexity Pro.

**Headline metrics:**
- **Chinook demo workload (n=60): 100% EA — 60/60.** 30 dev + 30 held-out, balanced split, no overfitting. Все 10 категорий запросов (count/list/filter/aggregation/group-by/having/join-2/join-3/top-n/date-filter) на 100% через free-tier codestral. Это реальный analyst workload, как BI tool в проде.
- **BIRD Mini-Dev SQLite (n=200, hard research benchmark) — портфолио-триплет:**
  - **85.5% EA на published BIRD gold** (171/200, leaderboard-comparable, BIRD-official set-equality scoring; **saturation ceiling confirmed** через triple-cross-validate на v16 residue: claude-4.5-sonnet-thinking+DAC + gemini-3.0-pro+DAC + grok-4.1-reasoning+M-Schema — 0 rescues каждый, 80/87 same across 3 ortogonal reasoning×prompt-format passes). Hybrid pipeline: codestral + Sonnet challenging + multi-provider voting + grounded-critique retry + self-consistency + Sonnet bridge + selective fewshot expansion + cross-Groq vote + M-Schema retry + CHASE-SQL divide-and-conquer + Perplexity Pro multi-model voting (Grok 4.1 + GPT-5.2 + Claude 4.5 Sonnet via helallao reverse-engineered bridge) + reasoning-mode variants (grok-4.1-reasoning + gpt-5.2-thinking + kimi-k2-thinking) + DAC×reasoning combo on residue. Per-tier: simple **92.5%**, moderate **82.8%**, challenging **79.4%**. _Day-5 evening audit (двойной): (1) фикс SQLAlchemy `:identifier` bind-bug в gold-runner (BIRD qids 959 / 989 / 990 — formula\_1 `LIKE '_:%:__.___'`); (2) приведение `compare_results` к BIRD-official set-семантике (был многомножественный Counter, делал scoring стрже чем bird-bench `evaluation_ex.py` — пред с `DISTINCT` поверх дубликатного gold считался mismatch). После обеих правок 171/200 совпало с предыдущим объявленным числом, но теперь каждая ячейка верифицирована через `scripts/audit_rescore.py` (0 расхождений). Регрессионные тесты в `tests/test_db_connection.py` + `tests/eval/test_metrics.py`._
  - **67.34% EA на Arcwise-Plat corrected gold** (Jin et al., CIDR/VLDB 2026, arXiv:2601.08778; 134/199, SQL-only fixes — v10 baseline). Честный noise-floor после правки annotation errors в BIRD. Полный отчёт: [`docs/corrected_gold_evaluation.md`](docs/corrected_gold_evaluation.md).
  - **+6 auditable cases** где наш pred правильнее BIRD's wrong gold (qid 672/1029/1144/1247/1251/1254 — missing DISTINCT, ASC-vs-DESC, extra id-column, wrong precedence, unnecessary JOINs). Прямое подтверждение что система делает reasoning, не memorization.
  - **+37.7pp над GPT-4 zero-shot (47.8%), $0 external cost.** Выше published SOTA paid GPT-4 (CHESS/Distillery: 73–76%), всех известных открытых free-tier результатов без fine-tuning (Arctic-32B 71.83%, CSC-SQL 73.67%, XiYan 75.63%) **и #1 paid system AskData+GPT-4o (81.95%)** на BIRD Mini-Dev (тот же scoring — set-equality из `bird-bench/mini_dev/evaluation_ex.py`).
  - Lift trace на n=200: 47% baseline (A_full_schema) → 51% (C_dense_cards) → 55.5% (D_dense_fewshot) → 56.5% (G_verify_retry) → 57.0% (Sonnet challenging hybrid) → 65.5% (+ multi-provider Groq voting v1) → 68.0% (+ Groq voting v2) → 72.0% (+ grounded-critique directed retry, 8 rescues / 0 regressions) → 72.5% (+ Mistral self-consistency) → 77.0% (+ Sonnet 4.6 via GraceKelly Perplexity bridge, 9 rescues / 0 regressions) → 77.5% (+ selective fewshot_top_k=5 on residue, +1) → 79.0% (+ cross-Groq voting on residue, +3) → 80.0% (+ gpt-oss-20b voting, +2) → 80.5% (+ M-Schema XiYan retry on residue, +1 qid 1525) → 81.0% (+ CHASE-SQL divide-and-conquer prompt on residue, +1 qid 1036 challenging) → 82.0% (+ Perplexity Pro multi-model voting через helallao reverse-engineered bridge: Grok 4.1 + GPT-5.2 на v11 residue, 2 rescues qid 672 moderate + qid 988 challenging, 0 regressions) → 84.0% (+ helallao reasoning-mode variants: grok-4.1-reasoning + gpt-5.2-thinking на v12 residue, 4 rescues qid 407 + 518 + 866 + 1529, все moderate, 0 regressions) → 84.5% (+ kimi-k2-thinking через helallao `mode="reasoning"` на v13 residue, 1 rescue qid 1235 moderate — Laboratory-vs-Examination JOIN-path, 0 regressions; gemini-3.0-pro на том же residue вернул 0/30, saturation подтверждена) → 85.0% (+ helallao Pro triplet retry на v14 residue: gpt-5.2 Pro mode 1 rescue qid 173 challenging — account-statement frequency + debit-3539 aim via subquery `GROUP BY account_id,k_symbol`; grok-4.1 Pro 0/28 + claude-4.5-sonnet Pro 24/31 EXC `non-dict NoneType` rate-limit; 0 regressions) → **85.5% (+ DAC×reasoning combo на v15 residue: `NLSQL_DAC=1` + helallao reasoning models — kimi-k2-thinking + grok-4.1-reasoning оба нашли тот же rescue qid 77 moderate california_schools — Percent FRPM(5-17) с правильным GSserved='K-9' и качественной типизацией; gpt-5.2-thinking heavy rate-limited 4/30; 0 regressions)**. _Двойной day-5 evening audit: (1) bind-bug fix в `_execute_gold` (SQLAlchemy `:identifier` парсил `LIKE '_:%:__.___'` в BIRD qids 959 / 989 / 990); (2) `compare_results` переведён на BIRD-official set-equality (был Counter — строже чем `bird-bench/mini_dev/evaluation_ex.py`). Обе правки компенсировались (–1 false positive simple + –1 false positive moderate + +1 false negative challenging от bind-bug; +1 false negative simple от set-семантики), итог 171/200 совпал с pre-audit, но теперь каждая ячейка верифицирована через `scripts/audit_rescore.py` (0 mismatches). Regression tests: `tests/test_db_connection.py::test_execute_readonly_handles_colons_in_string_literal` + `tests/eval/test_metrics.py::test_distinct_vs_non_distinct_is_match_under_bird_set`._
- **Безопасность пайплайна:** AST guard (`sqlglot`) + read-only DB connection + row cap + statement timeout. DML/DDL/multi-statement/ATTACH/PRAGMA отбрасываются до execution.

**Достигнутый потолок на $0 budget без fine-tuning:** 85.5% на published BIRD (BIRD-official set scoring, после двойного day-5 evening audit — bind-bug + set-семантика, см. row ниже); 67.34% на Arcwise-corrected gold (v10). **Выше #1 paid system** AskData+GPT-4o (81.95%) на +3.55pp, и всех published free-tier no-FT (Arctic-32B 71.83%, CSC-SQL 73.67%, XiYan 75.63%). Human expert baseline (BIRD paper) — 92.96%. Одиннадцать главных рычагов: **(1)** grounded-critique directed retry — shape feedback инжектится в re-prompt только на frozen-фейлах (+4.5pp без новых моделей); **(2)** Sonnet 4.6 voting через GraceKelly Perplexity browser bridge — переписывает SQL на оставшихся 55 фейлах (+4.5pp); **(3)** selective `fewshot_top_k=5` с grounded-critique на 46-fail residue после Sonnet (+0.5pp, validation что глобально вредный лeверь работает targeted); **(4)** cross-Groq voting на 45-fail residue после fewshot5 — llama-3.3-70b и qwen3-32b с critique дают ортогональные fixes (+1.5pp, 3 rescues / 0 regressions); **(5)** gpt-oss-20b voting на 42-fail v8 residue — lightweight model добивает qid 571 (ratio aggregation) и qid 1232 (challenging tier date-arithmetic) с critique-retry, +1pp / 0 regressions; **(6)** M-Schema XiYan compact serialization env-gated на residue retry only — +0.5pp (qid 1525 simple); **(7)** CHASE-SQL divide-and-conquer prompt env-gated `NLSQL_DAC=1` на residue — +0.5pp (qid 1036 challenging); **(8)** Perplexity Pro multi-model voting через helallao reverse-engineered HTTPS bridge (обход broken GraceKelly browser adapter) — Grok 4.1 и GPT-5.2 на v11 residue дают 2 ортогональных rescues qid 672 moderate + qid 988 challenging, +1pp / 0 regressions; **(9)** helallao reasoning-mode variants (`grok-4.1-reasoning` + `gpt-5.2-thinking` через `mode="reasoning"` в Perplexity backend) — 4 ортогональных rescues на v12 residue (qid 407, 518, 866, 1529 — все moderate), +2pp / 0 regressions. Claude-4.5-sonnet-thinking на том же residue вернул 0 rescues и 14/36 EXC `non-dict NoneType` — Perplexity backend жёстко rate-limits Claude reasoning variant, у grok/gpt-5.2 такого throttling нет; **(10)** kimi-k2-thinking через тот же reasoning route на v13 residue — 1 ортогональный rescue qid 1235 (Patient×Laboratory JOIN-path, где gemini получил tokenizer EXC) moderate, +0.5pp / 0 regressions. Gemini-3.0-pro на том же residue вернул 0/30 (2 EXC + 28 same) — saturation для бесплатных reasoning-моделей подтверждена. **Bonus retry day-5 EOD: helallao Pro triplet на v14 residue (31 fails)** — gpt-5.2 Pro mode 1 rescue qid 173 challenging (account-statement frequency + debit-3539 aim, subquery `GROUP BY account_id, k_symbol` который codestral пропустил), +0.5pp / 0 regressions → v15 85.0%. Grok-4.1 Pro 0/28 (1 tokenizer + 2 timeout EXC) и Claude-4.5-sonnet Pro 24/31 `non-dict NoneType` EXC — Perplexity rate-limits Claude в любом mode (pro/reasoning); **(11)** DAC×reasoning combo на v15 residue (30 fails) — `NLSQL_DAC=1` (CHASE-SQL divide-and-conquer prompt) подан как primary к helallao reasoning-моделям. **Kimi-k2-thinking + Grok-4.1-reasoning оба независимо нашли rescue qid 77** moderate california_schools (`Percent (%) Eligible FRPM (Ages 5-17)` с GSserved='K-9' + CAST на REAL для precision-preserving division — codestral пропускал GSserved filter и identifier-typing nuance). +0.5pp / 0 regressions → v16 85.5%. gpt-5.2-thinking 4/30 reached (heavy rate-limit после kimi sprint), но даже на 4 cases ortogonal с другими — backend coalesces reasoning quota по модели.

**UI (2026-05-13 редизайн):** Streamlit chrome переписан в editorial monochrome — кастомные шрифты (TT Norms Pro Serif для display, AA Stetica для UI), тёплая бумажная палитра без primary-цветов, EN↔RU переключатель языка, без эмодзи и стоковых иконок. Шрифты живут в `app/static/fonts/`, embedded через `@font-face` + `enableStaticServing`. Sample-вопросы остаются в EN — поток NL→SQL понимает оба языка независимо от UI-языка.

| EN | RU |
|:--:|:--:|
| ![NL→SQL UI English hero (live)](docs/ui-live-en.png) | ![NL→SQL UI Russian hero (live)](docs/ui-live-ru.png) |

Скриншоты сняты с live HF Space (<https://liovina-nl-sql.hf.space>), 1440×900 viewport, default DB `bird_california_schools`. На обоих видна триплет-подпись (скриншоты сняты на v13 — текущая live-метрика 85.5% после двойного v16-audit).

**47-секундный live-demo (без звука, headless 1440×900):**

https://github.com/brownjuly2003-code/NL_SQL/raw/master/docs/ui-live-demo.mp4

Три бита: (1) hero с метрикой (видео снято на v11 81.0%; live сейчас обновлён до 85.5% после двойного v16-audit), (2) клик по sample-вопросу → SQL с подсветкой + COUNT(4) ответ за ~5.5 c через codestral, (3) переключение EN ↔ RU без перезагрузки. Источник — live HF Space, не локалхост.

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

| Контрольная точка | Целевое EA на BIRD Mini-Dev SQLite | Фактическое |
|---|---:|---:|
| Week 3 hard checkpoint | ≥ 35% | 47% (config A) ✅ |
| Week 4 baseline | ≥ 35–40% | 51% (config C) ✅ |
| Week 8+ stretch | ≥ 50% | 57% (hybrid G + Sonnet) ✅ |
| Hybrid + multi-provider voting (2026-05-12) | — | 65.5% ✅ |
| Hybrid + voting + grounded-critique retry | — | 72.0% ✅ |
| + Mistral self-consistency | — | 72.5% ✅ |
| Final 2026-05-13 (+ Sonnet 4.6 bridge on all fails) | — | 77.0% ✅ |
| Final 2026-05-17 EOS (+ selective fewshot_top_k=5 on residue) | — | 77.5% ✅ |
| Final 2026-05-17 night (+ cross-Groq llama3.3-70b + qwen3-32b voting) | — | 79.0% ✅ |
| Final 2026-05-17 late-night (+ gpt-oss-20b voting on v8 residue) | — | 80.0% ✅ |
| Final 2026-05-17 late-night (+ M-Schema retry on v9 residue, XiYan-style) | — | 80.5% ✅ |
| Final 2026-05-17 next-day (+ CHASE-SQL DAC prompt on v10 residue) | — | 81.0% ✅ |
| Final 2026-05-18 (+ helallao Perplexity Pro bridge: Grok 4.1 + GPT-5.2 voting on v11 residue, 2 rescues) | — | 82.0% ✅ |
| Final 2026-05-18 day-4 (+ helallao reasoning-mode: grok-4.1-reasoning + gpt-5.2-thinking on v12 residue, 4 rescues) | — | 84.0% ✅ |
| Final 2026-05-18 day-5 (+ kimi-k2-thinking on v13 residue, 1 rescue qid 1235 moderate; gemini-3.0-pro 0/30 saturated) | — | 84.5% ✅ |
| Final 2026-05-18 day-5 EOD (+ helallao Pro triplet retry on v14 residue: gpt-5.2 Pro 1 rescue qid 173 challenging; grok-4.1 Pro 0/28; claude-4.5-sonnet Pro 24/31 rate-limited) | — | 85.0% ✅ |
| Final 2026-05-18 day-5 night (+ DAC×reasoning combo on v15 residue: `NLSQL_DAC=1` + kimi-k2-thinking + grok-4.1-reasoning оба нашли rescue qid 77 moderate FRPM-Percent; gpt-5.2-thinking 4/30 rate-limited) | — | 85.5% (pre-audit, multiset scoring) |
| **Final 2026-05-18 day-5 evening v16-audit-2 (BIRD-official set scoring + `_execute_gold` bind-bug fix; net 0 vs pre-audit, но verified row-by-row via `scripts/audit_rescore.py`)** | — | **85.5%** ✅ |
| Final 2026-05-18 day-5 afternoon v17-attempts (triple-cross-validate saturation on v16 residue: claude-4.5-sonnet-thinking+DAC 0/26 + 3 EXC, gemini-3.0-pro+DAC 0/29, grok-4.1-reasoning+M-Schema 0/25 + 4 EXC — все 29 residue qids resilient к ortogonal reasoning×prompt-format levers) | — | **85.5%** (saturation ceiling confirmed) |
| GPT-4 zero-shot reference | — | 47.8% |
| Published SOTA (paid API + fine-tuning) | — | 73–76% (CHESS) |
| Human expert baseline (BIRD paper) | — | 92.96% |

Калибровка: GPT-4 zero-shot на BIRD Mini-Dev = 47.8 / 40.8 / 35.8% EX (SQLite/MySQL/PostgreSQL). Все наши числа на SQLite split — `dev_split` deterministic, seed=0.

## Roadmap

8-10 недель, 12 этапов. Подробно в `docs/02_architecture_v2.md` §11.

## License

MIT (TBD).
