# Review request: NL→SQL Assistant — feasibility + architecture

You are reviewing a draft for a portfolio/demo project by a Senior Data Analyst / Data Engineer
(Julia Edomskikh). The author already runs a non-trivial RAG project (RAG_Support_Assistant:
FastAPI + LangGraph + Chroma + Mistral + Postgres + Langfuse + RAGAS + mypy strict, public on GitHub).
The new project is intentionally a *demo* for the author's portfolio, NOT a SaaS.

Two documents follow:
1. `00_task.md` — task statement (what / why / scope / DoD)
2. `01_architecture.md` — proposed architecture (pipeline, schema-RAG, eval, stack, roadmap)

## What I want from you

Give a candid, technical review. Не подыгрывай, возражай по существу. Russian or English — на твой выбор.

### Block A — Целесообразность проекта (feasibility / market-fit для портфолио)

1. Велосипед или нет? Рынок NL→SQL уже переполнен (Vanna, DataHerald, WrenAI,
   defog/sqlcoder, LangChain SQLAgent, PandasAI). Стоит ли вообще делать ещё одну реализацию
   для портфолио Senior Data Engineer? Какой в этом сигнал для рекрутёра / собеседующего?
2. Если делать — какие 2-3 элемента делают этот проект *отличимым* от среднего демо-NL→SQL?
   Какие наоборот — стандартные, не дают сигнала, и можно срезать без потери ценности?
3. Адекватен ли выбор Mistral-only (codestral-2501 + mistral-large-2 + mistral-embed)?
   Не помешает ли это позиционированию (как «vendor lock-in демо»)?
   Что ответить на вопрос «а почему не GPT-4 / Claude / локальная модель»?
4. Адекватен ли выбор БД (BIRD-mini для eval + StackExchange Postgres + Chinook)?
   Какие альтернативы дали бы больше «вау» при той же сложности реализации?
5. Объективно: при честной оценке Execution Accuracy ≥50% на BIRD-mini с codestral-2501 —
   реалистичная цель или завышенная для солиста без fine-tune?

### Block B — Оценка архитектуры

1. **Pipeline (LangGraph 11 узлов).** Что лишнее? Что упущено? Узлы расположены в правильном порядке?
   Конкретно: нужны ли все retry-точки (validate, execute, verify) или избыточно?
2. **Schema-RAG из 4 коллекций Chroma** (tables / columns / fewshot_qsql / relations).
   Это правильная декомпозиция или overengineering? Как бы ты сделал иначе?
   Какой baseline для сравнения (например, простая dense-схема без разбивки)?
3. **4-уровневая защита SQL** (БД-роль / sqlglot AST / EXPLAIN-gate / runtime-лимиты).
   Все четыре уровня необходимы? Какие реальные attack vectors остаются непокрытыми?
   Это hype или реально нужно для read-only демо?
4. **Eval harness.** Достаточно ли только Execution Accuracy + Component Match?
   Что ещё мерить (например, latency, cost-per-query, partial-correct)?
   Адекватна ли идея smoke-eval на 50 примеров в CI?
5. **Multi-format render** (scalar / sentence / table / chart с auto-выбором + Vega-Lite spec из LLM).
   Это реально работает или будет фейковый «выглядит красиво на картинке, фейлит в проде»?
   Какие подводные камни в Vega-spec generation от LLM?
6. **Стек целиком.** Что тут переусложнено для demo (см. раздел 12 в архитектуре —
   автор сама пометила что считает «нагруженным, но не фейковым»)? Согласен ли ты с её делением?
7. **Roadmap из 9 этапов на 5-6 недель.** Реалистично или оптимистично?
   Какой этап скорее всего «съест» больше времени, чем ожидается?
8. **Риски в разделе 11.** Что упущено? Какие более вероятные риски не названы?

### Block C — Что бы ты предложил по-другому

Конкретно: 3-5 точечных правок к архитектуре, ranked by impact.
Не обобщения («сделай лучше»), а конкретно: «убрать X, потому что Y»; «добавить Z до W»;
«поменять A на B».

### Block D — Финальный вердикт

Одной фразой: стоит делать этот проект как portfolio piece для Senior DE? Если да —
с какими корректировками. Если нет — что делать вместо.

---

## Document 1: 00_task.md

# NL→SQL Assistant — постановка задачи

**Дата:** 2026-05-10
**Автор:** Julia Edomskikh
**Статус:** draft / scoping

---

## 1. Что делаем

Инструмент, который принимает вопрос на естественном языке (русский или английский),
обращается к реляционной БД и возвращает ответ в одной из форм:

- **Число / скаляр** — для агрегатных вопросов («сколько заказов в марте?»).
- **Текстовое предложение** — для фактоидов с подстановкой данных
  («у клиента X 12 заказов на сумму 340k за 2024 год»).
- **Таблица** — когда нужен список записей.
- **График** — когда вопрос про динамику, сравнение, распределение
  (выбор типа графика автоматический: line / bar / pie / hist / scatter).
- **SQL-запрос** — всегда показывается пользователю как «доказательство»
  + объяснение на естественном языке, что именно посчитали.

## 2. Почему это не «ещё один чат с БД»

Демо-проект для портфолио, поэтому ценность создаётся не самим NL→SQL
(он есть у Vanna, DataHerald, WrenAI, defog/sqlcoder, LangChain SQLAgent),
а тремя слоями поверх:

1. **Измеримая точность.** Eval-harness на публичных бенчмарках
   (BIRD-bench и/или Spider) с метрикой Execution Accuracy и сравнением
   против опубликованных результатов моделей. Без этого числа проект — игрушка.
2. **Self-correction loop.** Если SQL падает или возвращает 0 строк или вырожденный
   результат — граф автоматически переформулирует запрос с error-context
   (паттерн из RAG_Support_Assistant: classify → retrieve → generate → verify → retry).
3. **Schema-RAG, а не «всю схему в промпт».** На сложных БД (десятки таблиц,
   сотни колонок) полная схема не влезает и шумит. Хранилище:
   таблицы + колонки + описания + примеры значений + few-shot Q→SQL пары
   индексируются в Chroma и достаются по релевантности к вопросу.

## 3. Целевые БД

Для демо берём два разных профиля сложности:

| База | Профиль | Зачем |
|---|---|---|
| **BIRD-bench (mini)** | 95 реальных БД из 37 доменов, 12 751 Q→SQL пар с эталонными ответами | Eval-harness, число Execution Accuracy на публичном leaderboard'е |
| **StackExchange public dump** в Postgres | Реальная сложная схема (Posts, Users, Votes, Comments, Tags, Badges), миллионы строк, JSONB-поля, временные ряды | Демо-вопросы с красивыми графиками («активность по часам», «распределение тегов», «топ-N пользователей по карме») |

Опционально третья — **Sakila** или **Chinook** — для онбординг-демо
(простая, всем знакомая, быстро отрабатывает первое впечатление).

## 4. LLM

Только Mistral по API. Две модели в роутинге:

- **codestral-2501** — генерация SQL и self-correction.
  Заточен под код, на NL→SQL стабильно бьёт mistral-large.
- **mistral-large-2** — классификация интента, объяснение результата
  на естественном языке, выбор типа визуализации.

Embeddings — `mistral-embed` (для schema-RAG и few-shot retrieval).

## 5. Базовый сценарий (happy path)

```
Пользователь: "Покажи топ-10 тегов на StackOverflow по приросту вопросов в 2023 году"
   |
   v
1. Classify intent  → "aggregation + ranking + time-window + visualization"
2. Schema retrieval → достать релевантные таблицы (Posts, Tags, PostTags) + 3 few-shot примера
3. SQL generation   → codestral пишет SQL с CTE по годам и приростом
4. Validate         → синтаксис ОК, EXPLAIN ОК, SELECT-only гард прошёл
5. Execute          → 10 строк × 3 колонки
6. Verify           → результат непустой, типы соответствуют ожиданиям
7. Format           → по структуре ответа выбран bar chart + краткий текст
8. Render           → markdown-ответ + Plotly-график + блок с SQL и объяснением
```

При фейле любого шага — retry с error-context (макс. 2 попытки),
дальше — graceful failure с показом, где именно споткнулись.

## 6. Что НЕ делаем (scope cuts)

- Никаких write-операций. Read-only коннект к БД, гард на уровне SQL-парсера.
- Никакого мульти-БД join'а в одном запросе.
- Никакого fine-tuning моделей — только prompt-engineering + RAG.
- Никакой собственной аутентификации/мульти-тенанси
  (это переусложнение для демо, в RAG_SA уже отработано — здесь не повторяем).
- Никаких write-back в БД на основе вопросов пользователя.

## 7. Критерии готовности (Definition of Done)

- [ ] Execution Accuracy на BIRD-mini dev split ≥ 50% (с codestral-2501 это реалистично).
- [ ] На StackExchange — 20 эталонных вопросов проходят end-to-end с корректным ответом.
- [ ] Веб-UI: ввод вопроса, четыре формата ответа, переключение БД, история.
- [ ] CI: тесты на гард SELECT-only, на парсер схемы, на pipeline-граф.
- [ ] README + диаграмма архитектуры + страница eval-результатов.
- [ ] Деплой: docker-compose с Postgres + Chroma + FastAPI + UI.


---

## Document 2: 01_architecture.md

# NL→SQL Assistant — архитектура (максимально нагруженный вариант)

**Дата:** 2026-05-10
**Статус:** draft / pending review

> «Максимально нагруженный» здесь = всё, что реально нужно для серьёзного
> демо-проекта уровня Senior Data Engineer, без фейкового overengineering'а.
> Каждый компонент обоснован задачей; ничего «на будущее».

---

## 1. Системная диаграмма

```text
                           ┌──────────────────────────┐
                           │  Web UI (Next.js + React)│
                           │  ─ chat input            │
                           │  ─ table / chart / SQL   │
                           │  ─ history + bookmarks   │
                           └────────────┬─────────────┘
                                        │ HTTPS
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │  FastAPI gateway (auth, rate-limit, CORS)│
                  │  /ask, /databases, /history, /eval/run   │
                  └────────────┬─────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────────────┐
          │                    │                            │
          ▼                    ▼                            ▼
  ┌──────────────┐    ┌────────────────┐         ┌────────────────────┐
  │ LangGraph    │    │ Eval harness   │         │ Schema indexer     │
  │ NL→SQL graph │    │ (BIRD/Spider)  │         │ (offline pipeline) │
  └──────┬───────┘    └────────┬───────┘         └─────────┬──────────┘
         │                     │                           │
         ▼                     ▼                           ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                   Shared services layer                       │
  ├──────────────┬──────────────┬─────────────┬──────────────────┤
  │ Mistral API  │ Chroma DB    │ Postgres    │ Redis            │
  │ codestral    │ schema chunks│ target DBs  │ result cache     │
  │ large-2      │ few-shot Q→S │ (multi-DB)  │ rate-limit state │
  │ mistral-embed│              │ + traces DB │                  │
  └──────────────┴──────────────┴─────────────┴──────────────────┘
                               │
                               ▼
                  ┌──────────────────────────┐
                  │ Observability             │
                  │ Prometheus + OpenTelemetry│
                  │ Langfuse traces           │
                  └──────────────────────────┘
```

## 2. LangGraph pipeline

Реиспользуем структуру из RAG_Support_Assistant
(`classify → retrieve → rerank → generate → verify → evaluate`),
но узлы заточены под NL→SQL:

```text
       ┌────────────────┐
       │ classify_intent│   intent = aggregation | ranking | filter |
       └────────┬───────┘            time_series | comparison | lookup |
                │                    distribution
                ▼
       ┌────────────────┐
       │ select_database│   если в системе несколько БД — выбрать целевую
       └────────┬───────┘            по интенту + ключевым словам
                │
                ▼
       ┌────────────────┐
       │ retrieve_schema│   Chroma: relevant tables + columns + value samples
       └────────┬───────┘
                │
                ▼
       ┌────────────────┐
       │ retrieve_examples│ Chroma: top-k похожих Q→SQL пар (few-shot)
       └────────┬───────┘
                │
                ▼
       ┌────────────────┐
       │ generate_sql   │   codestral-2501 + structured output (JSON-mode)
       └────────┬───────┘            { "sql": "...", "rationale": "..." }
                │
                ▼
       ┌────────────────┐
       │ static_validate│   sqlglot parse → SELECT-only guard → schema check
       └────────┬───────┘            (table/column existence vs catalog)
                │ FAIL ──────────► retry_loop (max 2)
                │ OK
                ▼
       ┌────────────────┐
       │ explain_plan   │   EXPLAIN на целевой БД, отказ если cost > threshold
       └────────┬───────┘            (защита от full-scan на больших таблицах)
                │
                ▼
       ┌────────────────┐
       │ execute        │   read-only коннект, statement_timeout, LIMIT-guard
       └────────┬───────┘
                │
                ▼
       ┌────────────────┐
       │ verify_result  │   проверки: непустой? типы соответствуют интенту?
       └────────┬───────┘            аномалии? (нулей/null'ов слишком много)
                │ FAIL ──────────► retry_loop
                │ OK
                ▼
       ┌────────────────┐
       │ choose_format  │   intent + result shape →
       └────────┬───────┘            scalar | sentence | table | chart
                │
                ▼
       ┌────────────────┐
       │ render_answer  │   mistral-large-2: NL-объяснение + chart-spec (Vega-Lite)
       └────────┬───────┘
                │
                ▼
       ┌────────────────┐
       │ persist_trace  │   sqlite traces + Langfuse span + Prometheus counter
       └────────────────┘
```

**Retry loop:** при фейле узлов `static_validate`, `execute`, `verify_result`
граф возвращается к `generate_sql` с приклеенным error-context'ом
(текст ошибки + предыдущий SQL + разъяснение что не так). Лимит — 2 попытки,
после чего отдаётся диагностический ответ.

## 3. Schema-RAG: устройство индекса

**Проблема:** в BIRD есть БД с 50+ таблицами. Полная схема в промпт не лезет
и зашумляет генерацию.

**Решение:** offline-пайплайн `Schema indexer` строит несколько коллекций в Chroma:

| Коллекция | Чанк | Эмбеддится |
|---|---|---|
| `schema_tables` | таблица | имя + описание + список колонок + 3 sample строки |
| `schema_columns` | колонка | имя + тип + описание + min/max/nunique + 5 sample значений |
| `fewshot_qsql` | Q→SQL пара | вопрос + аннотация интента (SQL не эмбеддится) |
| `relations` | FK-связь | from_table.col → to_table.col + семантика |

При вопросе `retrieve_schema` делает гибрид BM25 + dense на `schema_tables`,
дотягивает топ-N колонок из `schema_columns` для отобранных таблиц,
добавляет связи между ними. Получается компактный «срез схемы» под вопрос —
обычно 5-15 таблиц вместо 50+.

`retrieve_examples` достаёт из `fewshot_qsql` 3-5 наиболее похожих
вопросов с эталонными SQL — это мощно поднимает качество на сложных диалектах.

## 4. Безопасность исполнения SQL

Read-only — это не «обещание промптом», а реальные гарды на четырёх уровнях:

1. **БД-роль:** отдельный postgres-пользователь с GRANT SELECT ONLY,
   без CREATE/INSERT/UPDATE/DELETE/TRUNCATE/ALTER.
2. **Парсер:** `sqlglot` AST-валидация — отказ при не-SELECT, при множественных
   стейтментах, при наличии CTE с DML, при `pg_*`/`information_schema` без whitelist.
3. **EXPLAIN-gate:** `EXPLAIN (FORMAT JSON)` перед `EXECUTE`,
   отказ если `Total Cost > X` (порог настраивается на БД).
4. **Runtime:** `SET statement_timeout = 30s`, обязательный `LIMIT 10000`
   если в запросе нет агрегации.

## 5. Eval harness

Отдельный модуль `eval/`, не часть онлайн-пайплайна:

```text
eval/
├── datasets/
│   ├── bird_mini.jsonl          # 1500 Q→SQL пар, 11 БД
│   └── stackexchange_gold.jsonl # 20 наших эталонных вопросов
├── runner.py                    # прогон через граф, сравнение
├── metrics/
│   ├── execution_accuracy.py    # сравнение result-set'ов
│   ├── exact_match.py           # SQL string match (слабая метрика)
│   └── component_match.py       # сравнение по AST-компонентам
└── reports/
    └── 2026-05-10-baseline.html # отчёт по прогонам
```

CI прогоняет smoke-eval на 50 примерах при каждом merge в main.
Полный прогон — вручную или nightly.

**Целевое число:** Execution Accuracy ≥ 50% на BIRD-mini dev.
Опубликованные результаты codestral-2501 на BIRD ~57%, так что 50%
своими силами на узком сабсете — реалистично.

## 6. Multi-DB switching

В `config/databases.yml` описаны подключения:

```yaml
databases:
  - id: stackexchange
    dsn: postgresql://nlsql_ro@localhost/stackexchange
    description: "StackOverflow public data — posts, users, votes"
    schema_index: chroma://stackexchange
    sample_questions: ["топ-10 тегов...", "распределение..."]
  - id: bird_california_schools
    dsn: sqlite:///data/bird/california_schools.sqlite
    description: "California schools — performance, demographics"
    schema_index: chroma://bird_california_schools
  - id: chinook
    dsn: sqlite:///data/chinook.sqlite
    description: "Music store — invoices, tracks, customers"
    schema_index: chroma://chinook
```

UI даёт переключатель «target DB», граф читает её из state.

## 7. UI (Next.js + React)

Минимально, но без обрезков:

- **Chat-style вход** с подсветкой SQL в ответе и copy-кнопкой.
- **Multi-format ответ** — компонент сам решает, что рендерить
  (scalar / sentence / DataGrid / Vega-Lite chart).
- **«Show working»**: разворачивающийся блок с retrieved schema, few-shot,
  rationale, EXPLAIN-планом, временем выполнения.
- **History + bookmarks** в localStorage + опционально на бэке.
- **DB switcher** + список sample-вопросов под каждую БД.

Отдельная страница **`/eval`** — таблица результатов eval-прогонов,
графики динамики Execution Accuracy по коммитам.

## 8. Стек целиком

| Слой | Технология | Почему |
|---|---|---|
| LLM | Mistral API: codestral-2501, mistral-large-2, mistral-embed | Жёсткое требование задачи |
| Orchestration | LangGraph | Уже знакома по RAG_SA, retry-loop из коробки |
| API | FastAPI + Pydantic v2 | Стандарт, типобезопасность |
| Vector DB | ChromaDB | Уже знакома, локально без отдельного сервиса |
| SQL parser | sqlglot | Multi-dialect, AST-валидация, dialect translation |
| Target DB | Postgres 16 (StackExchange) + SQLite (BIRD, Chinook) | Реализм + простота |
| Cache | Redis 7 | Кэш результатов SQL, rate-limit |
| Charting | Vega-Lite (через спеку из LLM) + Plotly fallback | LLM хорошо генерит Vega-spec'и |
| Frontend | Next.js 15 + Tailwind + shadcn/ui | Быстрый красивый UI |
| Observability | Prometheus + OpenTelemetry + Langfuse | Стандартный стек, переиспользуется из RAG_SA |
| Tests | pytest + httpx + testcontainers (Postgres) | Реальная БД в CI |
| Lint/Type | ruff + mypy strict (api/, agent/) | Как в DE_project |
| CI | GitHub Actions | smoke-eval + pytest + ruff + mypy |
| Deploy | docker-compose (dev) + Dockerfile multi-stage (prod) | Достаточно для демо |

## 9. Структура репозитория

```
NL_SQL/
├── api/                   # FastAPI app, routers, middleware
├── agent/                 # LangGraph nodes, prompts, state
│   ├── graph.py
│   ├── nodes/
│   │   ├── classify.py
│   │   ├── retrieve_schema.py
│   │   ├── retrieve_examples.py
│   │   ├── generate_sql.py
│   │   ├── validate.py
│   │   ├── execute.py
│   │   ├── verify.py
│   │   ├── render.py
│   │   └── retry.py
│   └── prompts/
├── llm/                   # Mistral provider, retry, cost guard
├── schema_index/          # offline indexer for Chroma
│   ├── extractor.py       # introspect Postgres/SQLite catalog
│   ├── enricher.py        # описания, sample values, stats
│   └── builder.py         # build Chroma collections
├── execution/             # SQL guards, EXPLAIN gate, runner
├── eval/                  # см. раздел 5
├── frontend/              # Next.js UI
├── config/                # databases.yml, prompts.yml
├── data/                  # BIRD dump, Chinook, sample dumps (gitignore)
├── tests/
├── docker-compose.yml
├── Dockerfile
└── docs/
    ├── 00_task.md
    ├── 01_architecture.md       ← вы здесь
    ├── 02_eval_methodology.md   ← TODO
    └── 03_demo_questions.md     ← TODO
```

## 10. Roadmap (этапы)

| # | Этап | DoD |
|---|---|---|
| 1 | **Bootstrap** | poetry/uv проект, FastAPI hello, Mistral provider, тесты на провайдер с моком |
| 2 | **Target DBs ready** | docker-compose поднимает Postgres со StackExchange dump + SQLite Chinook + BIRD dump в `data/` |
| 3 | **Schema indexer** | offline скрипт строит Chroma-коллекции, smoke-тест на retrieval |
| 4 | **Pipeline v1** | LangGraph граф работает на Chinook (простая БД), single-shot без retry |
| 5 | **Guards & verify** | sqlglot guard, EXPLAIN gate, retry-loop, тесты |
| 6 | **Eval harness** | runner + execution_accuracy метрика, baseline на BIRD-mini |
| 7 | **Multi-format render** | scalar/sentence/table/chart с автоопределением + Vega-Lite spec'и |
| 8 | **UI v1** | chat + DB switcher + history, end-to-end на 3 БД |
| 9 | **Polish & deploy** | docker-compose prod-like, README, демо-видео, eval-страница |

Этапы 1-3 — фундамент (~неделя на каждом темпе).
Этапы 4-6 — суть проекта (~2 недели).
Этапы 7-9 — витрина (~неделя).

Итого: ~5-6 рабочих недель в спокойном темпе или 2-3 в плотном.

## 11. Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| codestral-2501 даёт <40% на BIRD | средняя | улучшить few-shot retrieval, добавить chain-of-thought, schema-linking шаг |
| StackExchange dump слишком большой для локалки (≥100GB) | высокая | взять mini-dump (`gaming.stackexchange.com`, ~1GB) — реализм без боли |
| EXPLAIN-gate ломает легитимные тяжёлые запросы | средняя | tune порог на БД, дать override-флаг для админа |
| BIRD dataset лицензия | низкая | CC-BY-SA-4.0, для демо OK |
| Mistral API rate limits на eval-прогоне | средняя | local cache на (prompt → response), батчинг, exponential backoff |

## 12. Что в этой архитектуре «нагруженного»

Если сравнить с минимальным NL→SQL (один промпт + один вызов LLM + execute):

- **+ LangGraph pipeline на 10+ узлов** с retry-loop и error-context.
- **+ Schema-RAG из 4 коллекций** вместо «вся схема в промпт».
- **+ Few-shot retrieval** из эталонных Q→SQL пар.
- **+ Static validate (sqlglot AST) + EXPLAIN-gate + 4-уровневая защита**.
- **+ Multi-DB** с переключателем и per-DB индексами.
- **+ Eval harness на публичном бенчмарке** с измеримой метрикой.
- **+ Multi-format рендер** (4 формата + auto-выбор графика).
- **+ Полноценный observability stack** (Prom + OTel + Langfuse).
- **+ Web-UI** с историей, eval-страницей, «show working».

Это потолок того, что осмысленно делать для демо-проекта без скатывания
в production-overhead (мульти-тенант, RBAC, OIDC, freshness monitor и т.д. —
всё то, что в RAG_SA уместно, а здесь было бы фейк-нагрузкой).
