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

Прогон делается на одном и том же **dev split** (250 примеров из 500 Mini-Dev — детерминированный sample) через **5 конфигураций**, каждая надстраивается над предыдущей:

| # | Конфигурация | Что включено |
|---|---|---|
| **A** | `full_schema` baseline | Вся схема целиком в prompt (если влезает; иначе truncate). Никакой RAG, никаких few-shot, никакого repair. |
| **B** | `BM25 cards` | BM25 retrieval топ-N таблиц как table cards (имя+колонки+типы). Без few-shot, без repair. |
| **C** | `Chroma cards` | Dense retrieval (mistral-embed) топ-N table cards + FK graph traversal. Без few-shot, без repair. |
| **D** | `+ fewshot` | C + top-k few-shot Q→SQL примеров из train split. Без repair. |
| **E** | `+ repair_once` | D + один repair pass при FAIL validate/execute. **Это финальная конфигурация v2.** |

### 4.2 Что репортится для каждой конфигурации

```
Configuration A: full_schema
  EA (overall):           XX.X%
  EA (simple):            XX.X%
  EA (moderate):          XX.X%
  EA (challenging):       XX.X%
  EA (SQLite/MySQL/PG):   XX.X / XX.X / XX.X
  Schema Recall@5:        XX.X%
  SQL Validity Rate:      XX.X%
  First-pass / Final EA:  XX.X / XX.X (для E одно число)
  Empty-Result Rate:      XX.X%
  Latency P50 / P95:      X.Xs / X.Xs
  Cost per query (avg):   $X.XXXX
  Tokens P50 / P95:       XXXX / XXXXX
```

### 4.3 Что должно быть видно из таблицы

Это и есть «инженерный сигнал» в портфолио:

- **A → B:** даёт ли BM25 retrieval выигрыш над full_schema? (на BIRD обычно да, потому что некоторые БД не влезают)
- **B → C:** даёт ли dense retrieval над BM25 measurable lift? (часто да, +2-5%)
- **C → D:** насколько важен few-shot retrieval? (обычно +5-10%)
- **D → E:** оправдан ли repair loop? (обычно +2-4%, но видна и trade-off на latency/cost)

Если B → C даёт ≤+1% — **обоснование Chroma снято**, переходим на BM25.
Если D → E даёт ≤+1% — **repair убирается** как лишняя сложность.

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

**Cost estimate:** см. `02_architecture_v2.md §6.5` — один полный eval-прогон 5 конфигураций = ~2600 unique generation calls (после первого прогона повторы = 0 API calls благодаря cache).

### 6.3 Pre-release (manual, перед merge в main или релизом)

- **Полная ablation** (A → E) на dev split.
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

### Execution Accuracy on BIRD Mini-Dev (250 dev sample, SQLite)

| Configuration               | EA (overall) | Simple | Moderate | Challenging |
|----------------------------|-------------|--------|----------|-------------|
| A: full_schema             | XX.X%       | XX.X%  | XX.X%    | XX.X%       |
| B: BM25 cards              | XX.X%       | XX.X%  | XX.X%    | XX.X%       |
| C: Chroma cards            | XX.X%       | XX.X%  | XX.X%    | XX.X%       |
| D: + fewshot               | XX.X%       | XX.X%  | XX.X%    | XX.X%       |
| E: + repair_once (final)   | XX.X%       | XX.X%  | XX.X%    | XX.X%       |
| Reference: GPT-4 zero-shot | 47.8%       | —      | —        | —           |

### Provider Bakeoff (30 curated questions, configuration E)

| Provider              | EA  | Validity | P50 latency | Cost / 30q |
|----------------------|-----|----------|-------------|------------|
| Mistral codestral    | XX% | XX%      | X.Xs        | $X.XX      |
| OpenAI gpt-4o        | XX% | XX%      | X.Xs        | $X.XX      |
| Ollama qwen2.5-coder | XX% | XX%      | X.Xs        | $0.00      |
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
- [ ] README результат-таблицы заполнены реальными числами (не XX.X%)
- [ ] Hard checkpoint week 3 пройден (EA ≥35% или scope-down принят)
