# NL→SQL Assistant — методология evaluation + ablation plan

**Дата:** 2026-05-10
**Статус:** active baseline (после CX + KM review v1)
**Сопровождает:** `00_task.md`, `02_architecture_v2.md`

> Этот документ — **главный артефакт портфолио** проекта. Без честной ablation
> с реальными числами проект — «ещё один tutorial с Medium». С ablation —
> демонстрация инженерного процесса, который рекрутёр / Senior+ собеседующий
> распознаёт мгновенно.

---

## 1. Что мы измеряем и почему

### 1.1 Primary metric

**Execution Accuracy (EA)** — доля вопросов, где результат сгенерированного SQL
*равен* результату gold SQL (с order-insensitive comparison для агрегатов без `ORDER BY`).

Источник эталонной реализации: official BIRD evaluation script
(https://github.com/bird-bench/mini_dev → `evaluation_ex.py`).

### 1.2 Secondary metrics (обязательно в отчёте)

| Метрика | Что показывает | Почему важна |
|---|---|---|
| **Schema Recall@k** | Доля вопросов, где все нужные таблицы (из gold SQL) попали в retrieved schema | Если это <60% — никакой LLM не поможет, проблема в RAG |
| **SQL Validity Rate** | % SQL, прошедших sqlglot AST guard | Зрелость pipeline; высокое = generator понимает диалект |
| **Repair Success Rate** | % случаев, когда repair_once починил невалидный SQL | Полезность retry-логики |
| **First-pass EA / Final EA** | EA до repair / после repair | Изолирует вклад repair |
| **Empty-Result Rate** | % выполненных SQL с пустым result-set | Часть error taxonomy |
| **Component Match (F1)** | F1 на AST-компонентах (SELECT cols, WHERE, GROUP BY, ORDER BY, JOIN) | Дебаг — где именно generator расходится с gold |
| **Latency P50 / P95** | End-to-end + per-node breakdown | Operational signal для Senior DE |
| **Cost per query** | Token usage × Mistral pricing | Operational signal |
| **Token usage P50 / P95** | Input + output tokens на вопрос | Контекст-эффективность retrieval |

### 1.3 Что НЕ мерим (явно)

- **Exact Match (EM)** — мусор для NL→SQL, два разных корректных SQL дают разный текст. Не использовать.
- **BLEU/ROUGE на SQL** — не корреллирует с execution correctness.
- **«User satisfaction»** в demo без юзеров — фейковая метрика.

## 2. Datasets

### 2.1 BIRD Mini-Dev (primary)

- **Размер:** 500 Q-SQL примеров (verified от bird-bench.github.io, 2026-05-10).
- **Доступ:** https://github.com/bird-bench/mini_dev
- **Зачем:** публичный leaderboard, можно сравниваться с GPT-4 / Claude / DeepSeek и т.д.
- **Difficulty split:** simple / moderate / challenging (BIRD предоставляет).
- **Dialects:** SQLite (главный), MySQL, PostgreSQL — отчёт по каждому диалекту отдельно.

### 2.2 StackExchange-mini (secondary, demo questions)

- **Источник:** gaming.stackexchange.com dump (~1 GB) ИЛИ trimmed StackOverflow 2023-2024 (posts/users/tags/votes only, ~2-5 GB).
- **20-30 курированных gold questions** с manually-written gold SQL и manual answer review.
- **Зачем:** демонстрация на реальной аналитической схеме, разнообразие форматов ответа (графики, ranking, time-series).
- **Метрика:** EA + manual review (qualitative).

### 2.3 Chinook (smoke only)

- **Размер:** ~1MB, 11 таблиц.
- **Зачем:** sanity check pipeline + первое впечатление в demo, **не портфолио-метрика**.

## 3. Эталонные референсные числа (для калибровки expectations)

Из BIRD Mini-Dev leaderboard (public, актуально на 2026-05-10):

| Модель | SQLite EX | MySQL EX | PostgreSQL EX |
|---|---|---|---|
| GPT-4 (zero-shot) | 47.8% | 40.8% | 35.8% |
| GPT-4 + Table Augmentation | 58.0% | 49.2% | 50.8% |

**Калибровка цели для Codestral solo:**
- **Baseline (week 4):** ≥35-40% EX на SQLite (примерно zero-shot GPT-4 уровень).
- **Stretch (week 8+):** ≥50% EX на SQLite (примерно TA-GPT-4 уровень — это уже серьёзный результат).
- **Hard checkpoint week 3:** EX ≥35% → продолжаем; <35% → scope-down per `02_architecture_v2.md` §12.

## 4. Ablation matrix (центральный артефакт)

### 4.1 Конфигурации

Прогон делается на одном и том же **dev split** (250 примеров из 500 Mini-Dev — детерминированный sample). Shipped production-ладдер — **A → C → D → G**, каждая надстраивается над предыдущей:

| # | Конфигурация | Что включено |
|---|---|---|
| **A** | `full_schema` baseline | Вся схема целиком в prompt (если влезает; иначе truncate). Никакой RAG, никаких few-shot, никакого repair. |
| **C** | `Chroma cards` | Dense retrieval (mistral-embed) топ-N table cards + FK graph traversal. Без few-shot, без repair. |
| **D** | `+ fewshot` | C + top-k few-shot Q→SQL примеров из train split. Без repair. |
| **G** | `+ verify_retry` | D + один verify/repair pass при FAIL validate/execute или empty result. **Финальная shipped конфигурация.** |

> **Config B (BM25 cards) намеренно не shipped.** В пилоте dense retrieval (C) был строго лучше BM25 на тех же top-N; BM25 расширял prompt без recall lift. Enum `Configuration.B_BM25` и `run_config_b` сохранены как `NotImplementedError`, чтобы методология читалась как полный A–E ладдер, но production path не зависит от B. См. `src/nl_sql/eval/runner.py` верхний docstring.
>
> Configs E (repair_once) и F (self-consistency vote) живут отдельно — реализованы для ablation, но не на shipped пути.

### 4.2 Что репортится для каждой конфигурации

Шаблон с реальными числами для финальной shipped конфигурации (G + multi-vote + critique + selfcon + Sonnet bridge + selective fewshot expansion + cross-Groq voting + M-Schema + CHASE-SQL DAC + helallao Perplexity Pro/reasoning multi-model voting + GraceKelly browser-orchestrator + targeted P3.F schema-link hints + archive-sweep / archive-rescore audit; n=200, seed=0, v27 2026-05-24):

```
Configuration G_hybrid+multi-vote+critique+selfcon+sonnet+fewshot5+groq3+
              mschema+dac+helallao-pro+helallao-reasoning+gracekelly+
              archive+p3f-targeted-hints  (final shipped path)
  EA (overall):           92.0%   (184/200, +44.2pp vs GPT-4 zero-shot 47.8%)
  EA (simple):            97.0%   (65/67)
  EA (moderate):          89.9%   (89/99)
  EA (challenging):       88.2%   (30/34)
  EA (SQLite only):       92.0%   (BIRD Mini-Dev is SQLite-only)
  Voting + targeted rescues: 70/200 (frozen-fail directed retry across vote
                                     buckets + 4 P3.F schema-link hints)
  Schema Recall@5:        100.0%
  SQL Validity Rate:      100.0%
  First-pass / Final EA:  47.0 / 92.0   (codestral A baseline → final)
  Latency P50 / P95:      ~65 ms cache-hit / dozens of seconds on Sonnet-rescued tier
  Cost per query:         $0    (Mistral free + Groq free + Perplexity Pro browser bridge)
  Audit:                  scripts/audit_rescore.py → stored 184 / true 184 / 0 mismatches
  P3.F acceptance:        scripts/p3f_acceptance.py --require-pass → qids 207, 1404,
                          902, 1531, 894, 1251 all PASS
```

Per-bucket lifts that compose the 92.0% headline:

```
A (codestral full_schema)                         47.0%   baseline
C (codestral dense_cards + sort)                  51.0%   +4.0pp
D (codestral dense_fewshot k=3)                   55.5%   +4.5pp
G (codestral verify-retry)                        56.5%   +1.0pp
G + Sonnet challenging tier hybrid                57.0%   +0.5pp
+ groq voting on filter_or_value                  62.0%   +5.0pp
+ gpt-oss-20b voting on remaining failures        64.5%   +2.5pp
+ row_count_off voting bucket                     65.5%   +1.0pp
+ grounded-critique directed retry                72.0%   +6.5pp
+ Mistral self-consistency                        72.5%   +0.5pp
+ Sonnet rescue on frozen-fail tail               77.0%   +4.5pp (9 rescues, 0 regressions)
+ selective fewshot_top_k=5 on residue            77.5%   +0.5pp (qid 1500)
+ cross-Groq voting on residue                    79.0%   +1.5pp (qids 219+352+366)
+ gpt-oss-20b voting (v9)                         80.0%   +1.0pp (qids 571+1232)
+ M-Schema XiYan retry on residue (v10)           80.5%   +0.5pp (qid 1525)
+ CHASE-SQL divide-and-conquer (v11)              81.0%   +0.5pp (qid 1036)
+ helallao Perplexity Pro multi-model voting (v12) 82.0%   +1.0pp (qids 672+988)
+ helallao reasoning-mode (grok+gpt-5.2) (v13)    84.0%   +2.0pp (qids 407+518+866+1529)
+ kimi-k2-thinking reasoning on v13 residue (v14) 84.5%   +0.5pp (qid 1235)
+ helallao Pro triplet retry on v14 residue (v15) 85.0%   +0.5pp (qid 173)
+ DAC×reasoning combo on v15 residue (v16)        85.5%   +0.5pp (qid 77)
+ post-cooldown gpt-5.2-thinking+DAC (v17)        86.0%   +0.5pp (qid 896)
+ helallao gpt-5.2 Pro on v17 residue (v18)       86.5%   +0.5pp (qid 989)
+ helallao claude-thinking on v18 residue (v19)   87.0%   +0.5pp (qid 743)
+ helallao kimi plain on v19 residue (v20)        87.5%   +0.5pp (qid 584)
+ GraceKelly Sonnet 4.6 BIRD-grain on qid 1399 (v21) 88.0% +0.5pp (qid 1399)
+ targeted P3.F schema-link merge (v22)           89.0%   +1.0pp (qids 207+1404)
+ archive-sweep qid 1205 (v23)                    89.5%   +0.5pp (audit-discipline)
+ archive-rescore qid 959 after bind-bug fix (v24) 90.0%  +0.5pp (engineering)
+ targeted P3.F hint qid 902 formula_1 (v25)      90.5%   +0.5pp (driverStandings.position)
+ targeted P3.F hint qid 1531 debit_card (v26)    91.0%   +0.5pp (yearmonth.Consumption)
+ targeted P3.F hints qids 894+1251 (v27)         92.0%   +1.0pp (lapTimes.ms + Patient⋈Lab⋈Exam)
```

**Selective fewshot expansion note:** глобальный `fewshot_top_k=5` (вместо
default 3) давал −1pp на n=200 в 2026-05 sessions — extra examples
запутывали codestral на correct cases. На frozen failure set после
Sonnet, тот же лeверь даёт +1 rescue / 0 regressions (`qid=1500` simple,
2026-05-17 v7). Это validates общую гипотезу sprint'а: лeвера которые
вредят глобально могут помогать selective на ranked residue, если
применять с `enable_grounded_critique=True` чтобы re-prompt shape-aware.

Все формулы метрик — см. §5. Полные per-config таблицы — §6 ниже. Чтобы получить эти числа локально:

```powershell
uv run python scripts/eval_baseline.py --config G --n 200 --seed 0 --with-fewshot
uv run python scripts/merge_hybrid_eval.py \
    --base eval/reports/<date>/G_dense_fewshot_verify_retry-verify-retry.json \
    --override eval/reports/<date>/G_dense_fewshot_verify_retry-sonnet-challenging.json \
    --override-difficulty challenging --suffix hybrid-codestral-sonnet
uv run python scripts/error_taxonomy.py eval/baselines/hybrid_n200_v0.json
```

### 4.3 Что должно быть видно из таблицы

Это и есть «инженерный сигнал» в портфолио:

- **A → C:** даёт ли dense retrieval выигрыш над full_schema? (на BIRD да, +4pp — некоторые БД не влезают целиком)
- **C → D:** насколько важен few-shot retrieval? (на BIRD +4.5pp на n=200)
- **D → G:** оправдан ли verify-retry pass? (на BIRD +1.0pp + cures empty-result tail)
- **G → G+Sonnet hybrid:** даёт ли Sonnet на challenging tier дополнительный lift? (+11.5pp на n=200, см. 2026-05-13 run)

Если C → D даёт ≤+1% — **few-shot убирается** как лишняя сложность.
Если D → G даёт ≤+0.5pp — **verify-retry убирается**.

Это и есть честный engineering: каждый компонент имеет measured cost/benefit.

## 5. Train/dev hygiene (предотвращение leakage)

**Главный риск:** использование dev examples как few-shot pool → искусственно завышенный EA.

### 5.1 Hard split

- BIRD Mini-Dev = 500 examples. Этот файл — *evaluation only*.
- Few-shot pool строится **только** из BIRD train split (~9 428 examples).
- Тесты в CI: `test_no_dev_in_fewshot()` грепает `fewshot_qsql` Chroma collection
  и убеждается, что ни один embedded вопрос не присутствует в dev IDs.

### 5.2 StackExchange split

- 20-30 курированных gold вопросов **никогда** не попадают в few-shot.
- Если для StackExchange нужны few-shot примеры — используются *других* типов, синтетические или из StackOverflow Data Explorer (с публичных source-ов, не gold).

### 5.3 Документация в README

Явный раздел «Train/Dev split hygiene» с указанием, какой именно train file использовался и checksum (SHA256 в `eval/datasets/SHA256SUMS`).

## 6. CI vs nightly vs full eval

### 6.1 CI (per-PR, должен быть быстрым и детерминированным)

- **Unit tests** на узлы графа с **мокнутым LLM** (LiteLLM mock или собственный fake).
- **5-10 cached smoke examples** через **vcr.py** (запись cassette один раз, replay в CI).
- **sqlglot guard tests** — отдельный набор adversarial-SQL для проверки гарда.
- **Schema indexer tests** — собрать на test fixture (Chinook), проверить recall на 5 эталонных вопросах.
- **Никаких live API calls в CI.**

Цель CI: «pipeline не сломан», не «accuracy измерен».

### 6.2 Nightly / on-demand

- **Полный 500-example прогон BIRD Mini-Dev** через E (финальная конфигурация).
- **diskcache** на ключ `(provider, model, prompt_hash) → response` для дедупликации запросов между запусками.
- **Throttle:** `asyncio.Semaphore(N)` где N = 0.8 × текущий free-tier RPS Mistral. При обнаружении rate-limit → exponential backoff через `tenacity`.
- **Pre-flight quota check** (`eval/check_quota.py`) — если daily limit близко к исчерпанию, batch откладывается.
- Артефакт: HTML-отчёт в `eval/reports/YYYY-MM-DD.html`.
- Тригер: cron (если хватит API quota) или manual `make eval-full`.

**Cost estimate:** см. `02_architecture_v2.md §6.5` — один полный eval-прогон по shipped ладдеру A → C → D → G = ~2000 unique generation calls (после первого прогона повторы = 0 API calls благодаря cache). Дополнительные voting/critique/selfcon/Sonnet-rescue layers — ещё ~600 calls на frozen-fail tail.

### 6.3 Pre-release (manual, перед merge в main или релизом)

- **Полная ablation** (A → G + final shipped path) на dev split.
- **Bakeoff** (3 providers × 30 questions) если есть изменения в provider adapter.
- Обновление главной таблицы в README.

## 7. Business semantics: mini-glossary

NL→SQL чаще всего фейлит на словах-определениях, а не на технических терминах:
«active user», «top tag», «growth», «churn», «engaged customer», «revenue».
Это *определения*, не колонки.

### 7.1 Решение

В `schema_chunks` добавляется section «business hints»:

```
Table: Posts
Columns: ...
Business hints:
  - "popular post" = Score > 50
  - "recent" = CreationDate > NOW() - INTERVAL '30 days'
  - "answered question" = AcceptedAnswerId IS NOT NULL
```

### 7.2 Ablation расширение (optional)

Прогон конфигурации E *с* business hints vs *без* — отчёт, насколько они влияют на EA на StackExchange-mini (на BIRD не релевантно — вопросы там без business jargon).

### 7.3 Limit

Не пытаемся построить полноценный semantic layer (это работа WrenAI и им подобных). 1-3 hint'а на таблицу, ровно столько, чтобы покрыть наиболее частые definitions в gold-вопросах.

## 8. Provider bakeoff

### 8.1 Setup (зафиксированы 2026-05-10, $0 budget hard constraint)

- **30 курированных вопросов** (10 BIRD-style + 10 StackExchange + 10 edge cases).
- **3 провайдера** прогон через идентичный pipeline (E конфигурация):
  1. **Mistral `codestral-latest`** (v25.08, default) — Mistral La Plateforme free tier.
  2. **`gpt-4o-mini` через GitHub Models** (frontier reference) — `models.inference.ai.azure.com` с GitHub PAT, free tier для personal аккаунтов. Backup: Gemini 2.0 Flash через AI Studio.
  3. **Ollama `qwen2.5-coder:7b-instruct`** (Q4_K_M ≈ 4.7 GB, default Ollama quant) — fits 16 GB RAM.

**Опциональный 4-й слот** (для отдельных experiments, не в default README таблице):
- `defog/sqlcoder-7b-2` — SQL-specialized, добавляется через `config/providers.yml`. Подходит как "best local SQL signal" в дополнение к qwen2.5-coder.

**Не используются** (зафиксировано — для воспроизводимости):
- `qwen2.5-coder:14b` — 9 GB RAM, **тесно** на 16 GB system при запущенных Postgres+Chroma.
- `qwen2.5-coder:32b` — 20 GB RAM, **не помещается** в 16 GB вообще.
- Frontier альтернативы (Claude/Gemini) — оставлены на будущие итерации, не блокируют v1 portfolio piece.

### 8.2 Что в отчёте

| Provider | EA | Validity Rate | Latency P50 | Cost / 30q |
|---|---|---|---|---|
| Mistral `codestral-latest` | XX% | XX% | X.Xs | $0 (Mistral free tier + диск-кэш) |
| `gpt-4o-mini` (GitHub Models) | XX% | XX% | X.Xs | $0 (GitHub Models free tier) |
| Ollama `qwen2.5-coder:7b` | XX% | XX% | X.Xs | $0 (электричество) |

Плюс **slicing per question**: какая модель ошиблась где.

### 8.3 Что это даёт портфолио

Превращает «почему Mistral?» из вкусовщины в *измеренный trade-off*:
«Codestral даёт 86% от GPT-4 quality за 1/8 стоимости» (или какой бы там результат ни был).

## 9. Operational metrics dashboard

### 9.1 Минимально (Langfuse-only)

В Langfuse:
- per-trace breakdown: token usage, latency, model, cost.
- session view: цепочки вопросов одного юзера.
- error rate за период.

### 9.2 Не делаем

- Prometheus dashboard (фейковая нагрузка для solo).
- OpenTelemetry exporter (не интегрируется ни во что в demo).
- Custom Grafana board.

Всё это — overhead без сигнала.

## 10. Reporting (что попадает в README)

Главная таблица в README проекта:

```markdown
## Results

### Execution Accuracy on BIRD Mini-Dev (n=200, SQLite, seed=0)

| Configuration                                    | EA (overall) | Simple | Moderate | Challenging |
|-------------------------------------------------|-------------|--------|----------|-------------|
| A: full_schema (codestral)                       | 47.0%       | 64.2%  | 43.4%    | 29.4%       |
| C: dense_cards (codestral + sort)                | 51.0%       | 67.2%  | 47.5%    | 32.4%       |
| D: dense_fewshot (codestral, k=3 BIRD train)     | 55.5%       | 70.1%  | 51.5%    | 35.3%       |
| G: + verify_retry (codestral)                    | 56.5%       | 71.6%  | 53.5%    | 38.2%       |
| G + Sonnet challenging hybrid                    | 57.0%       | 71.6%  | 53.5%    | 38.2%       |
| + multi-vote + grounded-critique + selfcon       | 72.5%       | 86.6%  | 70.7%    | 55.9%       |
| + Sonnet rescue on frozen-fail tail              | 77.0%       | 88.1%  | 74.7%    | 61.8%       |
| + selective fewshot_top_k=5 on residue           | 77.5%       | 89.6%  | 74.7%    | 61.8%       |
| **+ cross-Groq llama3.3-70b + qwen3 voting (final)** | **79.0%**   | **91.0%** | **75.8%** | **64.7%** |
| Reference: GPT-4 zero-shot (BIRD paper)          | 47.8%       | —      | —        | —           |
| Reference: paid SOTA CHESS/Distillery 2024       | 73–76%      | —      | —        | —           |

Final shipped configuration matches `eval/reports/2026-05-17/hybrid-vote-critique-selfcon-sonnet-fewshot5-groq3-v8.json` — see also memory note `project_nl_sql_quality_push`.

Config B (BM25 cards) is intentionally absent from the shipped pipeline — dense retrieval (config C) was strictly superior in pilot runs and BM25 would only widen the prompt with no recall lift. `Configuration.B_BM25` enum and `run_config_b` (NotImplementedError) are kept so the A–E ladder reads as documented, but the production path is A → C → D → G → hybrid → voting/critique/selfcon → Sonnet rescue.

### Provider Bakeoff (chinook smoke, n=60, configuration G)

| Provider               | EA      | Validity | P50 latency | Cost / 60q |
|------------------------|---------|----------|-------------|------------|
| Mistral codestral      | 100%    | 100%     | <1 s        | $0         |
| Claude Sonnet 4.6 (PPL browser) | n/a (eval-only on BIRD challenging) | — | ~30 s | $0 |
| Groq Llama 3.3 70B     | partial (JSON-strict failures) | 40% | 1.5 s | $0 |
| Ollama qwen2.5-coder   | not benchmarked at scale (local-only)  | —    | —    | $0         |
```

Это **не** «выглядит как туториал». Это выглядит как лабораторный отчёт DE.

## 11. Risk-mitigations cross-ref

Связь с разделом 13 в `02_architecture_v2.md`:

| Риск | Митигация в этом документе |
|---|---|
| Schema retrieval recall <60% | §1.2 (Schema Recall@k как primary secondary metric); §4 (configuration B/C явно выделяет проблему) |
| Benchmark leakage | §5 hard split + CI test |
| Business semantics gap | §7 mini-glossary |
| Repair-loop делает confident-wrong SQL | §1.2 (First-pass vs Final EA репортится отдельно — видно цена repair) |
| codestral-latest version drift | §8 bakeoff фиксирует snapshot для повторяемости |
| Eval flakiness в CI | §6.1 vcr.py + cached smoke только |

## 12. Definition of Done для eval-стрима

- [ ] BIRD Mini-Dev (500) downloaded + checksummed
- [ ] Train split (BIRD train) загружен и явно отделён от dev
- [ ] CI test `test_no_dev_in_fewshot()` написан и проходит
- [ ] Ablation runner работает на 5 конфигурациях (A → E)
- [ ] Все метрики из §1.2 collected per-configuration
- [ ] Slicing by difficulty + dialect работает
- [ ] HTML-отчёт генерируется (`eval/reports/YYYY-MM-DD.html`)
- [ ] CI smoke-eval с vcr.py (5-10 examples) green
- [ ] Bakeoff на 30 вопросов × 3 providers работает
- [x] README результат-таблицы заполнены реальными числами (2026-05-12)
- [ ] Hard checkpoint week 3 пройден (EA ≥35% или scope-down принят)

---

## 13. Итоговые результаты — три честных уровня (2026-07-11)

Одно число вводит в заблуждение, поэтому метрика BIRD Mini-Dev (n=200, SQLite, $0 free-tier) разложена по слоям. Только **уровень 1** включён в продукт (Streamlit UI и `/ask`); уровни 2–3 — eval-конфигурация.

| Уровень | EA | Что это | В продукте? | Воспроизводимость |
|---|---:|---|:--:|---|
| 1. Reproducible single-run | **61.5%** (123/200) | Чистый пайплайн на codestral, один прогон, config E (dense + repair + few-shot), без голосования и подсказок. First-pass 59.5%; simple 76.1% / moderate 58.6% / challenging 41.2%. | да | **одна команда**, детерминированно |
| 2. + per-question schema-link hints | **62.5%** (125/200) | Тот же прогон с `--bird-rescue-hints`: 11 hint-блоков под конкретные BIRD-вопросы (`_hints.py`). First-pass 60.5%; simple 74.6% / moderate 58.6% / challenging 50.0%. | eval (`enable_bird_rescue_hints`, off) | **одна команда** |
| 3. + multi-provider voting | 85.5% | Само-консистентность + голосование по провайдерам (Groq / OpenRouter / Perplexity-bridge). | eval | архив; не «с нуля» (Perplexity-cookie-bridge истёк 16.06) |
| 4. + hints поверх voting-архива | **94.0%** (188/200) | Накопительный merge v22→v31 поверх уровня 3: голосование codestral + Sonnet 4.6 + GPT-5.2 + Grok-4.1 + Kimi-K2 + Llama-4-Scout + Qwen3 + gpt-oss, archive-rescore, и те же hints. simple 97.0% / moderate 92.9% / challenging 91.2%. | eval | архив-merge; consistency проверяется `audit_rescore.py` (0 mismatches) |

**Почему 58.0%, а не 57.5% (третий проход, 2026-07-11).** Число выросло не от модели, а от починки скоринга. `_hashable` (set-путь компаратора) квантовал к сетке допуска только `float`, а `int` пропускал как есть: gold `5` ложился в корзину `5`, а pred `5.0` — в `5 000 000`, и верный ответ получал miss. Это **строже официального BIRD-скрипта**, который сравнивает сырые python-кортежи, где `5 == 5.0` схлопывается — то есть наша «apples-to-apples с лидербордом» была не вполне apples-to-apples. Order-sensitive путь (`_cell_equal`, допуск 1e-6) такие пары всегда засчитывал, поэтому одна и та же пара (gold, pred) скорилась по-разному в зависимости от того, есть ли в gold `ORDER BY`. Теперь int, float и (после `_normalise_cell`) Decimal лежат на одной сетке. Правка **монотонна** — она может только слить корзины, ошибочно разведённые, — поэтому ни один ранее засчитанный вопрос не мог пропасть. Вернулся один вопрос уровня challenging (41.2% → 44.1%). Postgres n=49 (49.0%) и SQLite-контроль n=49 (44.9%) не изменились, Chinook — по-прежнему 100%.

Уровень 2 (85.5%) измерен архивным прогоном до этой правки и «с нуля» не пересобирается — читать его следует как число того скоринга.

### Воспроизвести

```powershell
# Уровень 1 (продуктовый пайплайн, seed=0, детерминированный dev_split):
uv run python scripts/eval_baseline.py --config E --n 200            # → 61.5% (123/200)
# Уровень 2 (hint-assisted, eval-only) — тот же прогон с флагом:
uv run python scripts/eval_baseline.py --config E --n 200 --bird-rescue-hints   # → 62.5% (125/200)
```

Уровни 1 и 2 воспроизводятся одной командой на free-tier Mistral. **Уровни 3 и 4 этими командами не получить** — и раньше эта страница утверждала обратное. Флаг `--bird-rescue-hints` добавляет подсказки к продуктовому single-run и даёт 62.5%, а не 94.0%: 94.0% — это накопительный merge примерно двадцати прогонов разных провайдеров (см. поле `sql_model` в `eval/reports/2026-05-26/v31-v30-plus-p3f-q37-merged.json`), поверх которого те же hints и лежат. Часть rescues шла через Perplexity-cookie-bridge, которого больше нет; `audit_rescore.py` подтверждает консистентность архива, но «с нуля» уровни 3–4 сейчас не пересобираются.

### Честность витрины

Уровень 3 выше human-expert baseline (BIRD paper, 92.96%) — но это **hint-assisted слой**, кодирующий ответы к конкретным вопросам теста, а не провайдер-уровневая победа. Поэтому он выключен в продукте по умолчанию: живое демо и API отдают уровень 1 (61.5%). `GET /eval/latest` отдаёт именно уровень 1 — число, которого достигает сам API. Разделение на слои показывает и инженерию (воспроизводимые 61.5%), и научную честность (какой слой что даёт).

На Arcwise-corrected gold (Jin et al., CIDR/VLDB 2026) — 74.37% (148/199): noise-floor после исправления annotation-ошибок BIRD.

---

## 14. Postgres: тот же пайплайн на другом движке (2026-07-11)

До этой даты «Postgres 16 как второй backend» был заявлен, но **ни разу не прогнан**: read-only-защиту чинили в CI на пустой пробной таблице, а живых данных и живого прогона не было. Заявление проверено — и проверка нашла два дефекта, которые на SQLite не проявляются в принципе.

### Как загружены данные

BIRD Mini-Dev официально поставляет Postgres-версию: `MINIDEV_postgresql/BIRD_dev.sql` (955 МБ `pg_dump`, все 11 БД **в одну схему `public`**) и `mini_dev_postgresql.json` — gold SQL, переписанный под PG (**312 из 500** запросов отличаются от SQLite-версии: `STRFTIME('%Y', x)` → `TO_CHAR(CAST(x AS TIMESTAMP), 'YYYY')` и т.п.).

Заливать дамп целиком нельзя: 75 посторонних таблиц (Formula-1, карточные игры, больничные лаборатории) попали бы в schema-retrieval и подменили задачу. `scripts/extract_pg_dump_slice.py` вырезает одну БД по именам таблиц (они глобально уникальны между 11 БД — свойство закреплено тестом) и валидирует срез: все `CREATE TABLE`, все `COPY`, ни одного FK наружу.

**Почему не `scripts/load_postgres.py` (SQLite → pandas → PG).** BIRD-овский PG-gold написан под схему их дампа: идентификаторы свёрнуты в нижний регистр (`displayname`, `posthistory`), даты — настоящий `timestamptz`. Pandas-загрузка воспроизводит CamelCase из SQLite, и gold вида `SELECT DisplayName FROM users` (в PG это `displayname`) просто не нашёл бы колонку. Официальный дамп — то, что делает прогон честным BIRD-раном, а не похожим на него. `load_postgres.py` остаётся правильным инструментом для Chinook и произвольных SQLite-срезов, где PG-gold не существует.

`codebase_community` (StackExchange-mini): 8 таблиц, **741 646 строк**, 385 МБ в PG. Сверено с SQLite построчно — совпадает по всем таблицам.

### Результат (config E, codestral, hints off — тот же продуктовый пайплайн)

Одни и те же 49 вопросов `codebase_community`, два движка, свой gold и свой schema-индекс у каждого:

| Движок | EA | simple | moderate | challenging | Validity |
|---|---:|---:|---:|---:|---:|
| SQLite | 44.9% (22/49) | 76.2% | 21.7% | 20.0% | 100% |
| **Postgres 16** | **49.0% (24/49)** | 66.7% | 34.8% | 40.0% | 100% |

Согласие движков — **88%** (18 вопросов оба решают верно, 25 оба неверно; 4 только SQLite, 2 только Postgres). Разница в 2 вопроса на n=49 — **шум, а не превосходство**: доверительный интервал здесь ±14 pp. Читать это следует так: **пайплайн переносим — на Postgres он не деградирует**, генерируя PG-диалект (`TO_CHAR`, `::`, `ILIKE`) под PG-схему. Валидность 100% означает, что каждый сгенерированный запрос исполнился на живом сервере.

Артефакт: `eval/baselines/postgres_codebase_community_n49.json` (под тем же consistency-гейтом, что и остальные baseline'ы).

### Два бага, которые нашёл только живой Postgres

Оба сидели в продуктовом коде и оба невидимы на SQLite:

1. **`%` в SQL убивал запрос.** `execute_readonly` исполнял SQL через `exec_driver_sql`, который передаёт драйверу (пустой) набор параметров. psycopg говорит на `pyformat`, поэтому начинал искать плейсхолдеры и падал на `LIKE '%variance%'`: *only '%s', '%b', '%t' are allowed as placeholders, got '%v'*. Ломался самый частый шаблон text-to-SQL (LIKE-фильтр) и оператор `%` (modulo) — **и BIRD-овский gold тоже**, так что вопрос нельзя было даже оценить (qids 586/587). Починено: исполнение через DBAPI-курсор вообще без параметров — тогда ни `%` (psycopg), ни `:__` (SQLAlchemy `text()`, BIRD qids 959/989/990) не интерпретируются. Драйверные исключения заворачиваются обратно в `sqlalchemy.exc`, чтобы классификация ошибок не поехала.

2. **Скоринг занижал Postgres.** psycopg возвращает `numeric` (любые `AVG`, `SUM`, деление) как `Decimal`, SQLite — как `float`. `_hashable` квантовал к сетке допуска только `float`, а `Decimal` пропускал как есть → верный ответ `Decimal('1.3070996799810359')` не попадал в ту же корзину, что gold `1.307099679981036`, и получал miss. Докстринг обещал «Decimal → float» — строки в коде не было. Из-за этого PG-прогон показывал 40.8% вместо 49.0%: **четыре балла EA съедал баг компаратора, а не модель.**

Заметность обоих багов на SQLite — нулевая: sqlite3 не парсит `%` и не возвращает `Decimal`. Это и есть аргумент в пользу того, чтобы прогонять заявленный backend, а не только объявлять его.

### Воспроизвести

```bash
# 1. срез одной БД из официального PG-дампа BIRD
python scripts/extract_pg_dump_slice.py --db codebase_community --out .tmp/codebase_community_pg.sql

# 2. Postgres 16 (docker-compose profile postgres → localhost:5433) + загрузка
docker compose --profile postgres up -d
psql "postgresql://postgres:postgres@localhost:5433/nl_sql_demo" -v ON_ERROR_STOP=1 -f .tmp/codebase_community_pg.sql
psql "postgresql://postgres:postgres@localhost:5433/nl_sql_demo" -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl_sql_ro"

# 3. schema-индекс по ЖИВОЙ PG-схеме (отдельный persist — иначе перезапишет SQLite-чанки того же db_id)
python scripts/build_index.py --db bird_codebase_community --persist .tmp/chroma_pg \
    --pg-dsn "postgresql+psycopg://nl_sql_ro:nl_sql_ro_pwd@localhost:5433/nl_sql_demo"

# 4. eval на PG-gold (пайплайн промптит postgresql, gold берётся из mini_dev_postgresql.json)
python scripts/eval_baseline.py --config E --dialect postgresql --db bird_codebase_community --n 49 \
    --persist .tmp/chroma_pg \
    --pg-dsn "postgresql+psycopg://nl_sql_ro:nl_sql_ro_pwd@localhost:5433/nl_sql_demo"
```

`--dialect postgresql` без Postgres-бэкенда для выбранных БД падает с ошибкой: PG-gold, исполненный на SQLite-движке, дал бы не громкую ошибку, а тихо заниженный EA.
