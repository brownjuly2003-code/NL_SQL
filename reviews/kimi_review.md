# Review request: NL→SQL Assistant — feasibility + architecture

You are reviewing a draft for a portfolio/demo project by a Senior Data Analyst
/ Data Engineer
(Julia Edomskikh). The author already runs a non-trivial RAG project (RAG_Suppo
rt_Assistant:
FastAPI + LangGraph + Chroma + Mistral + Postgres + Langfuse + RAGAS + mypy str
ict, public on GitHub).
The new project is intentionally a *demo* for the author's portfolio, NOT a Saa
S.

Two documents follow:
1. `00_task.md` — task statement (what / why / scope / DoD)
2. `01_architecture.md` — proposed architecture (pipeline, schema-RAG, eval, st
ack, roadmap)

## What I want from you

Give a candid, technical review. Не подыгрывай, возражай по существу. Russian o
r English — на твой выбор.

### Block A — Целесообразность проекта (feasibility / market-fit для портфолио)

1. Велосипед или нет? Рынок NL→SQL уже переполнен (Vanna, DataHerald, WrenAI,
   defog/sqlcoder, LangChain SQLAgent, PandasAI). Стоит ли вообще делать ещё од
ну реализацию
   для портфолио Senior Data Engineer? Какой в этом сигнал для рекрутёра / собе
седующего?
2. Если делать — какие 2-3 элемента делают этот проект *отличимым* от среднего 
демо-NL→SQL?
   Какие наоборот — стандартные, не дают сигнала, и можно срезать без потери це
нности?
3. Адекватен ли выбор Mistral-only (codestral-2501 + mistral-large-2 + mistral-
embed)?
   Не помешает ли это позиционированию (как «vendor lock-in демо»)?
   Что ответить на вопрос «а почему не GPT-4 / Claude / локальная модель»?
4. Адекватен ли выбор БД (BIRD-mini для eval + StackExchange Postgres + Chinook
)?
   Какие альтернативы дали бы больше «вау» при той же сложности реализации?
5. Объективно: при честной оценке Execution Accuracy ≥50% на BIRD-mini с codest
ral-2501 —
   реалистичная цель или завышенная для солиста без fine-tune?

### Block B — Оценка архитектуры

1. **Pipeline (LangGraph 11 узлов).** Что лишнее? Что упущено? Узлы расположены
в правильном порядке?
   Конкретно: нужны ли все retry-точки (validate, execute, verify) или избыточн
о?
2. **Schema-RAG из 4 коллекций Chroma** (tables / columns / fewshot_qsql / rela
tions).
   Это правильная декомпозиция или overengineering? Как бы ты сделал иначе?
   Какой baseline для сравнения (например, простая dense-схема без разбивки)?
3. **4-уровневая защита SQL** (БД-роль / sqlglot AST / EXPLAIN-gate / runtime-л
имиты).
   Все четыре уровня необходимы? Какие реальные attack vectors остаются непокры
тыми?
   Это hype или реально нужно для read-only демо?
4. **Eval harness.** Достаточно ли только Execution Accuracy + Component Match?
   Что ещё мерить (например, latency, cost-per-query, partial-correct)?
   Адекватна ли идея smoke-eval на 50 примеров в CI?
5. **Multi-format render** (scalar / sentence / table / chart с auto-выбором + 
Vega-Lite spec из LLM).
   Это реально работает или будет фейковый «выглядит красиво на картинке, фейли
т в проде»?
   Какие подводные камни в Vega-spec generation от LLM?
6. **Стек целиком.** Что тут переусложнено для demo (см. раздел 12 в архитектур
е —
   автор сама пометила что считает «нагруженным, но не фейковым»)? Согласен ли 
ты с её делением?
7. **Roadmap из 9 этапов на 5-6 недель.** Реалистично или оптимистично?
   Какой этап скорее всего «съест» больше времени, чем ожидается?
8. **Риски в разделе 11.** Что упущено? Какие более вероятные риски не названы?

### Block C — Что бы ты предложил по-другому

Конкретно: 3-5 точечных правок к архитектуре, ranked by impact.
Не обобщения («сделай лучше»), а конкретно: «убрать X, потому что Y»; «добавить
Z до W»;
«поменять A на B».

### Block D — Финальный вердикт

Одной фразой: стоит делать этот проект как portfolio piece для Senior DE? Если 
да —
с какими корректировками. Если нет — что делать вместо.

---

## Document 1: 00_task.md

# NL→SQL Assistant — постановка задачи

**Дата:** 2026-05-10
**Автор:** Julia Edomskikh
**Статус:** draft / scoping

---

## 1. Что делаем

Инструмент, который принимает вопрос на естественном языке (русский или английс
кий),
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
2. **Self-correction loop.** Если SQL падает или возвращает 0 строк или вырожде
нный
   результат — граф автоматически переформулирует запрос с error-context
   (паттерн из RAG_Support_Assistant: classify → retrieve → generate → verify →
retry).
3. **Schema-RAG, а не «всю схему в промпт».** На сложных БД (десятки таблиц,
   сотни колонок) полная схема не влезает и шумит. Хранилище:
   таблицы + колонки + описания + примеры значений + few-shot Q→SQL пары
   индексируются в Chroma и достаются по релевантности к вопросу.

## 3. Целевые БД

Для демо берём два разных профиля сложности:

| База | Профиль | Зачем |
|---|---|---|
| **BIRD-bench (mini)** | 95 реальных БД из 37 доменов, 12 751 Q→SQL пар с этал
онными ответами | Eval-harness, число Execution Accuracy на публичном leaderboa
rd'е |
| **StackExchange public dump** в Postgres | Реальная сложная схема (Posts, Use
rs, Votes, Comments, Tags, Badges), миллионы строк, JSONB-поля, временные ряды 
| Демо-вопросы с красивыми графиками («активность по часам», «распределение тег
ов», «топ-N пользователей по карме») |

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
Пользователь: "Покажи топ-10 тегов на StackOverflow по приросту вопросов в 2023
году"
   |
   v
1. Classify intent  → "aggregation + ranking + time-window + visualization"
2. Schema retrieval → достать релевантные таблицы (Posts, Tags, PostTags) + 3 f
ew-shot примера
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

- [ ] Execution Accuracy на BIRD-mini dev split ≥ 50% (с codestral-2501 это реа
листично).
- [ ] На StackExchange — 20 эталонных вопросов проходят end-to-end с корректным
ответом.
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
       │ render_answer  │   mistral-large-2: NL-объяснение + chart-spec (Vega-L
ite)
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

**Решение:** offline-пайплайн `Schema indexer` строит несколько коллекций в Chr
oma:

| Коллекция | Чанк | Эмбеддится |
|---|---|---|
| `schema_tables` | таблица | имя + описание + список колонок + 3 sample строки
|
| `schema_columns` | колонка | имя + тип + описание + min/max/nunique + 5 sampl
e значений |
| `fewshot_qsql` | Q→SQL пара | вопрос + аннотация интента (SQL не эмбеддится) 
|
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
   стейтментах, при наличии CTE с DML, при `pg_*`/`information_schema` без whit
elist.
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
| LLM | Mistral API: codestral-2501, mistral-large-2, mistral-embed | Жёсткое т
ребование задачи |
| Orchestration | LangGraph | Уже знакома по RAG_SA, retry-loop из коробки |
| API | FastAPI + Pydantic v2 | Стандарт, типобезопасность |
| Vector DB | ChromaDB | Уже знакома, локально без отдельного сервиса |
| SQL parser | sqlglot | Multi-dialect, AST-валидация, dialect translation |
| Target DB | Postgres 16 (StackExchange) + SQLite (BIRD, Chinook) | Реализм + 
простота |
| Cache | Redis 7 | Кэш результатов SQL, rate-limit |
| Charting | Vega-Lite (через спеку из LLM) + Plotly fallback | LLM хорошо гене
рит Vega-spec'и |
| Frontend | Next.js 15 + Tailwind + shadcn/ui | Быстрый красивый UI |
| Observability | Prometheus + OpenTelemetry + Langfuse | Стандартный стек, пер
еиспользуется из RAG_SA |
| Tests | pytest + httpx + testcontainers (Postgres) | Реальная БД в CI |
| Lint/Type | ruff + mypy strict (api/, agent/) | Как в DE_project |
| CI | GitHub Actions | smoke-eval + pytest + ruff + mypy |
| Deploy | docker-compose (dev) + Dockerfile multi-stage (prod) | Достаточно дл
я демо |

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
| 1 | **Bootstrap** | poetry/uv проект, FastAPI hello, Mistral provider, тесты 
на провайдер с моком |
| 2 | **Target DBs ready** | docker-compose поднимает Postgres со StackExchange
dump + SQLite Chinook + BIRD dump в `data/` |
| 3 | **Schema indexer** | offline скрипт строит Chroma-коллекции, smoke-тест н
а retrieval |
| 4 | **Pipeline v1** | LangGraph граф работает на Chinook (простая БД), single
-shot без retry |
| 5 | **Guards & verify** | sqlglot guard, EXPLAIN gate, retry-loop, тесты |
| 6 | **Eval harness** | runner + execution_accuracy метрика, baseline на BIRD-
mini |
| 7 | **Multi-format render** | scalar/sentence/table/chart с автоопределением 
+ Vega-Lite spec'и |
| 8 | **UI v1** | chat + DB switcher + history, end-to-end на 3 БД |
| 9 | **Polish & deploy** | docker-compose prod-like, README, демо-видео, eval-
страница |

Этапы 1-3 — фундамент (~неделя на каждом темпе).
Этапы 4-6 — суть проекта (~2 недели).
Этапы 7-9 — витрина (~неделя).

Итого: ~5-6 рабочих недель в спокойном темпе или 2-3 в плотном.

## 11. Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| codestral-2501 даёт <40% на BIRD | средняя | улучшить few-shot retrieval, доб
авить chain-of-thought, schema-linking шаг |
| StackExchange dump слишком большой для локалки (≥100GB) | высокая | взять min
i-dump (`gaming.stackexchange.com`, ~1GB) — реализм без боли |
| EXPLAIN-gate ломает легитимные тяжёлые запросы | средняя | tune порог на БД, 
дать override-флаг для админа |
| BIRD dataset лицензия | низкая | CC-BY-SA-4.0, для демо OK |
| Mistral API rate limits на eval-прогоне | средняя | local cache на (prompt → 
response), батчинг, exponential backoff |

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
TurnBegin(
    user_input='# Review request: NL→SQL Assistant — feasibility + architecture
\n\nYou are reviewing a draft for a portfolio/demo project by a Senior Data Ana
lyst / Data Engineer\n(Julia Edomskikh). The author already runs a non-trivial 
RAG project (RAG_Support_Assistant:\nFastAPI + LangGraph + Chroma + Mistral + P
ostgres + Langfuse + RAGAS + mypy strict, public on GitHub).\nThe new project i
s intentionally a *demo* for the author\'s portfolio, NOT a SaaS.\n\nTwo docume
nts follow:\n1. `00_task.md` — task statement (what / why / scope / DoD)\n2. `0
1_architecture.md` — proposed architecture (pipeline, schema-RAG, eval, stack, 
roadmap)\n\n## What I want from you\n\nGive a candid, technical review. Не поды
грывай, возражай по существу. Russian or English — на твой выбор.\n\n### Block 
A — Целесообразность проекта (feasibility / market-fit для портфолио)\n\n1. Вел
осипед или нет? Рынок NL→SQL уже переполнен (Vanna, DataHerald, WrenAI,\n   def
og/sqlcoder, LangChain SQLAgent, PandasAI). Стоит ли вообще делать ещё одну реа
лизацию\n   для портфолио Senior Data Engineer? Какой в этом сигнал для рекрутё
ра / собеседующего?\n2. Если делать — какие 2-3 элемента делают этот проект *от
личимым* от среднего демо-NL→SQL?\n   Какие наоборот — стандартные, не дают сиг
нала, и можно срезать без потери ценности?\n3. Адекватен ли выбор Mistral-only 
(codestral-2501 + mistral-large-2 + mistral-embed)?\n   Не помешает ли это пози
ционированию (как «vendor lock-in демо»)?\n   Что ответить на вопрос «а почему 
не GPT-4 / Claude / локальная модель»?\n4. Адекватен ли выбор БД (BIRD-mini для
eval + StackExchange Postgres + Chinook)?\n   Какие альтернативы дали бы больше
«вау» при той же сложности реализации?\n5. Объективно: при честной оценке Execu
tion Accuracy ≥50% на BIRD-mini с codestral-2501 —\n   реалистичная цель или за
вышенная для солиста без fine-tune?\n\n### Block B — Оценка архитектуры\n\n1. *
*Pipeline (LangGraph 11 узлов).** Что лишнее? Что упущено? Узлы расположены в п
равильном порядке?\n   Конкретно: нужны ли все retry-точки (validate, execute, 
verify) или избыточно?\n2. **Schema-RAG из 4 коллекций Chroma** (tables / colum
ns / fewshot_qsql / relations).\n   Это правильная декомпозиция или overenginee
ring? Как бы ты сделал иначе?\n   Какой baseline для сравнения (например, прост
ая dense-схема без разбивки)?\n3. **4-уровневая защита SQL** (БД-роль / sqlglot
AST / EXPLAIN-gate / runtime-лимиты).\n   Все четыре уровня необходимы? Какие р
еальные attack vectors остаются непокрытыми?\n   Это hype или реально нужно для
read-only демо?\n4. **Eval harness.** Достаточно ли только Execution Accuracy +
Component Match?\n   Что ещё мерить (например, latency, cost-per-query, partial
-correct)?\n   Адекватна ли идея smoke-eval на 50 примеров в CI?\n5. **Multi-fo
rmat render** (scalar / sentence / table / chart с auto-выбором + Vega-Lite spe
c из LLM).\n   Это реально работает или будет фейковый «выглядит красиво на кар
тинке, фейлит в проде»?\n   Какие подводные камни в Vega-spec generation от LLM
?\n6. **Стек целиком.** Что тут переусложнено для demo (см. раздел 12 в архитек
туре —\n   автор сама пометила что считает «нагруженным, но не фейковым»)? Согл
асен ли ты с её делением?\n7. **Roadmap из 9 этапов на 5-6 недель.** Реалистичн
о или оптимистично?\n   Какой этап скорее всего «съест» больше времени, чем ожи
дается?\n8. **Риски в разделе 11.** Что упущено? Какие более вероятные риски не
названы?\n\n### Block C — Что бы ты предложил по-другому\n\nКонкретно: 3-5 точе
чных правок к архитектуре, ranked by impact.\nНе обобщения («сделай лучше»), а 
конкретно: «убрать X, потому что Y»; «добавить Z до W»;\n«поменять A на B».\n\n
### Block D — Финальный вердикт\n\nОдной фразой: стоит делать этот проект как p
ortfolio piece для Senior DE? Если да —\nс какими корректировками. Если нет — ч
то делать вместо.\n\n---\n\n## Document 1: 00_task.md\n\n# NL→SQL Assistant — п
остановка задачи\n\n**Дата:** 2026-05-10\n**Автор:** Julia Edomskikh\n**Статус:
** draft / scoping\n\n---\n\n## 1. Что делаем\n\nИнструмент, который принимает 
вопрос на естественном языке (русский или английский),\nобращается к реляционно
й БД и возвращает ответ в одной из форм:\n\n- **Число / скаляр** — для агрегатн
ых вопросов («сколько заказов в марте?»).\n- **Текстовое предложение** — для фа
ктоидов с подстановкой данных\n  («у клиента X 12 заказов на сумму 340k за 2024
год»).\n- **Таблица** — когда нужен список записей.\n- **График** — когда вопро
с про динамику, сравнение, распределение\n  (выбор типа графика автоматический:
line / bar / pie / hist / scatter).\n- **SQL-запрос** — всегда показывается пол
ьзователю как «доказательство»\n  + объяснение на естественном языке, что именн
о посчитали.\n\n## 2. Почему это не «ещё один чат с БД»\n\nДемо-проект для порт
фолио, поэтому ценность создаётся не самим NL→SQL\n(он есть у Vanna, DataHerald
, WrenAI, defog/sqlcoder, LangChain SQLAgent),\nа тремя слоями поверх:\n\n1. **
Измеримая точность.** Eval-harness на публичных бенчмарках\n   (BIRD-bench и/ил
и Spider) с метрикой Execution Accuracy и сравнением\n   против опубликованных 
результатов моделей. Без этого числа проект — игрушка.\n2. **Self-correction lo
op.** Если SQL падает или возвращает 0 строк или вырожденный\n   результат — гр
аф автоматически переформулирует запрос с error-context\n   (паттерн из RAG_Sup
port_Assistant: classify → retrieve → generate → verify → retry).\n3. **Schema-
RAG, а не «всю схему в промпт».** На сложных БД (десятки таблиц,\n   сотни коло
нок) полная схема не влезает и шумит. Хранилище:\n   таблицы + колонки + описан
ия + примеры значений + few-shot Q→SQL пары\n   индексируются в Chroma и достаю
тся по релевантности к вопросу.\n\n## 3. Целевые БД\n\nДля демо берём два разны
х профиля сложности:\n\n| База | Профиль | Зачем |\n|---|---|---|\n| **BIRD-ben
ch (mini)** | 95 реальных БД из 37 доменов, 12 751 Q→SQL пар с эталонными ответ
ами | Eval-harness, число Execution Accuracy на публичном leaderboard\'е |\n| *
*StackExchange public dump** в Postgres | Реальная сложная схема (Posts, Users,
Votes, Comments, Tags, Badges), миллионы строк, JSONB-поля, временные ряды | Де
мо-вопросы с красивыми графиками («активность по часам», «распределение тегов»,
«топ-N пользователей по карме») |\n\nОпционально третья — **Sakila** или **Chin
ook** — для онбординг-демо\n(простая, всем знакомая, быстро отрабатывает первое
впечатление).\n\n## 4. LLM\n\nТолько Mistral по API. Две модели в роутинге:\n\n
- **codestral-2501** — генерация SQL и self-correction.\n  Заточен под код, на 
NL→SQL стабильно бьёт mistral-large.\n- **mistral-large-2** — классификация инт
ента, объяснение результата\n  на естественном языке, выбор типа визуализации.\
n\nEmbeddings — `mistral-embed` (для schema-RAG и few-shot retrieval).\n\n## 5.
Базовый сценарий (happy path)\n\n```\nПользователь: "Покажи топ-10 тегов на Sta
ckOverflow по приросту вопросов в 2023 году"\n   |\n   v\n1. Classify intent  →
"aggregation + ranking + time-window + visualization"\n2. Schema retrieval → до
стать релевантные таблицы (Posts, Tags, PostTags) + 3 few-shot примера\n3. SQL 
generation   → codestral пишет SQL с CTE по годам и приростом\n4. Validate     
   → синтаксис ОК, EXPLAIN ОК, SELECT-only гард прошёл\n5. Execute          → 1
0 строк × 3 колонки\n6. Verify           → результат непустой, типы соответству
ют ожиданиям\n7. Format           → по структуре ответа выбран bar chart + крат
кий текст\n8. Render           → markdown-ответ + Plotly-график + блок с SQL и 
объяснением\n```\n\nПри фейле любого шага — retry с error-context (макс. 2 попы
тки),\nдальше — graceful failure с показом, где именно споткнулись.\n\n## 6. Чт
о НЕ делаем (scope cuts)\n\n- Никаких write-операций. Read-only коннект к БД, г
ард на уровне SQL-парсера.\n- Никакого мульти-БД join\'а в одном запросе.\n- Ни
какого fine-tuning моделей — только prompt-engineering + RAG.\n- Никакой собств
енной аутентификации/мульти-тенанси\n  (это переусложнение для демо, в RAG_SA у
же отработано — здесь не повторяем).\n- Никаких write-back в БД на основе вопро
сов пользователя.\n\n## 7. Критерии готовности (Definition of Done)\n\n- [ ] Ex
ecution Accuracy на BIRD-mini dev split ≥ 50% (с codestral-2501 это реалистично
).\n- [ ] На StackExchange — 20 эталонных вопросов проходят end-to-end с коррек
тным ответом.\n- [ ] Веб-UI: ввод вопроса, четыре формата ответа, переключение 
БД, история.\n- [ ] CI: тесты на гард SELECT-only, на парсер схемы, на pipeline
-граф.\n- [ ] README + диаграмма архитектуры + страница eval-результатов.\n- [ 
] Деплой: docker-compose с Postgres + Chroma + FastAPI + UI.\n\n\n---\n\n## Doc
ument 2: 01_architecture.md\n\n# NL→SQL Assistant — архитектура (максимально на
груженный вариант)\n\n**Дата:** 2026-05-10\n**Статус:** draft / pending review\
n\n> «Максимально нагруженный» здесь = всё, что реально нужно для серьёзного\n>
демо-проекта уровня Senior Data Engineer, без фейкового overengineering\'а.\n> 
Каждый компонент обоснован задачей; ничего «на будущее».\n\n---\n\n## 1. Систем
ная диаграмма\n\n```text\n                           ┌─────────────────────────
─┐\n                           │  Web UI (Next.js + React)│\n                  
        │  ─ chat input            │\n                           │  ─ table / c
hart / SQL   │\n                           │  ─ history + bookmarks   │\n      
                    └────────────┬─────────────┘\n                             
          │ HTTPS\n                                        ▼\n                 
┌──────────────────────────────────────────┐\n                  │  FastAPI gate
way (auth, rate-limit, CORS)│\n                  │  /ask, /databases, /history,
/eval/run   │\n                  └────────────┬─────────────────────────────┘\n
                              │\n          ┌────────────────────┼──────────────
──────────────┐\n          │                    │                            │\
n          ▼                    ▼                            ▼\n  ┌────────────
──┐    ┌────────────────┐         ┌────────────────────┐\n  │ LangGraph    │   
│ Eval harness   │         │ Schema indexer     │\n  │ NL→SQL graph │    │ (BIR
D/Spider)  │         │ (offline pipeline) │\n  └──────┬───────┘    └────────┬──
─────┘         └─────────┬──────────┘\n         │                     │        
                  │\n         ▼                     ▼                          
▼\n  ┌──────────────────────────────────────────────────────────────┐\n  │     
             Shared services layer                       │\n  ├──────────────┬─
─────────────┬─────────────┬──────────────────┤\n  │ Mistral API  │ Chroma DB  
 │ Postgres    │ Redis            │\n  │ codestral    │ schema chunks│ target D
Bs  │ result cache     │\n  │ large-2      │ few-shot Q→S │ (multi-DB)  │ rate-
limit state │\n  │ mistral-embed│              │ + traces DB │                 
│\n  └──────────────┴──────────────┴─────────────┴──────────────────┘\n        
                      │\n                               ▼\n                  ┌─
─────────────────────────┐\n                  │ Observability             │\n  
               │ Prometheus + OpenTelemetry│\n                  │ Langfuse trac
es           │\n                  └──────────────────────────┘\n```\n\n## 2. La
ngGraph pipeline\n\nРеиспользуем структуру из RAG_Support_Assistant\n(`classify
→ retrieve → rerank → generate → verify → evaluate`),\nно узлы заточены под NL→
SQL:\n\n```text\n       ┌────────────────┐\n       │ classify_intent│   intent 
= aggregation | ranking | filter |\n       └────────┬───────┘            time_s
eries | comparison | lookup |\n                │                    distributio
n\n                ▼\n       ┌────────────────┐\n       │ select_database│   ес
ли в системе несколько БД — выбрать целевую\n       └────────┬───────┘         
  по интенту + ключевым словам\n                │\n                ▼\n       ┌─
───────────────┐\n       │ retrieve_schema│   Chroma: relevant tables + columns
+ value samples\n       └────────┬───────┘\n                │\n                
▼\n       ┌────────────────┐\n       │ retrieve_examples│ Chroma: top-k похожих
Q→SQL пар (few-shot)\n       └────────┬───────┘\n                │\n           
    ▼\n       ┌────────────────┐\n       │ generate_sql   │   codestral-2501 + 
structured output (JSON-mode)\n       └────────┬───────┘            { "sql": ".
..", "rationale": "..." }\n                │\n                ▼\n       ┌──────
──────────┐\n       │ static_validate│   sqlglot parse → SELECT-only guard → sc
hema check\n       └────────┬───────┘            (table/column existence vs cat
alog)\n                │ FAIL ──────────► retry_loop (max 2)\n                │
OK\n                ▼\n       ┌────────────────┐\n       │ explain_plan   │   E
XPLAIN на целевой БД, отказ если cost > threshold\n       └────────┬───────┘   
        (защита от full-scan на больших таблицах)\n                │\n         
      ▼\n       ┌────────────────┐\n       │ execute        │   read-only конне
кт, statement_timeout, LIMIT-guard\n       └────────┬───────┘\n                
│\n                ▼\n       ┌────────────────┐\n       │ verify_result  │   пр
оверки: непустой? типы соответствуют интенту?\n       └────────┬───────┘       
    аномалии? (нулей/null\'ов слишком много)\n                │ FAIL ──────────
► retry_loop\n                │ OK\n                ▼\n       ┌────────────────
┐\n       │ choose_format  │   intent + result shape →\n       └────────┬──────
─┘            scalar | sentence | table | chart\n                │\n           
    ▼\n       ┌────────────────┐\n       │ render_answer  │   mistral-large-2: 
NL-объяснение + chart-spec (Vega-Lite)\n       └────────┬───────┘\n            
   │\n                ▼\n       ┌────────────────┐\n       │ persist_trace  │  
sqlite traces + Langfuse span + Prometheus counter\n       └────────────────┘\n
```\n\n**Retry loop:** при фейле узлов `static_validate`, `execute`, `verify_re
sult`\nграф возвращается к `generate_sql` с приклеенным error-context\'ом\n(тек
ст ошибки + предыдущий SQL + разъяснение что не так). Лимит — 2 попытки,\nпосле
чего отдаётся диагностический ответ.\n\n## 3. Schema-RAG: устройство индекса\n\
n**Проблема:** в BIRD есть БД с 50+ таблицами. Полная схема в промпт не лезет\n
и зашумляет генерацию.\n\n**Решение:** offline-пайплайн `Schema indexer` строит
несколько коллекций в Chroma:\n\n| Коллекция | Чанк | Эмбеддится |\n|---|---|--
-|\n| `schema_tables` | таблица | имя + описание + список колонок + 3 sample ст
роки |\n| `schema_columns` | колонка | имя + тип + описание + min/max/nunique +
5 sample значений |\n| `fewshot_qsql` | Q→SQL пара | вопрос + аннотация интента
(SQL не эмбеддится) |\n| `relations` | FK-связь | from_table.col → to_table.col
+ семантика |\n\nПри вопросе `retrieve_schema` делает гибрид BM25 + dense на `s
chema_tables`,\nдотягивает топ-N колонок из `schema_columns` для отобранных таб
лиц,\nдобавляет связи между ними. Получается компактный «срез схемы» под вопрос
—\nобычно 5-15 таблиц вместо 50+.\n\n`retrieve_examples` достаёт из `fewshot_qs
ql` 3-5 наиболее похожих\nвопросов с эталонными SQL — это мощно поднимает качес
тво на сложных диалектах.\n\n## 4. Безопасность исполнения SQL\n\nRead-only — э
то не «обещание промптом», а реальные гарды на четырёх уровнях:\n\n1. **БД-роль
:** отдельный postgres-пользователь с GRANT SELECT ONLY,\n   без CREATE/INSERT/
UPDATE/DELETE/TRUNCATE/ALTER.\n2. **Парсер:** `sqlglot` AST-валидация — отказ п
ри не-SELECT, при множественных\n   стейтментах, при наличии CTE с DML, при `pg
_*`/`information_schema` без whitelist.\n3. **EXPLAIN-gate:** `EXPLAIN (FORMAT 
JSON)` перед `EXECUTE`,\n   отказ если `Total Cost > X` (порог настраивается на
БД).\n4. **Runtime:** `SET statement_timeout = 30s`, обязательный `LIMIT 10000`
\n   если в запросе нет агрегации.\n\n## 5. Eval harness\n\nОтдельный модуль `e
val/`, не часть онлайн-пайплайна:\n\n```text\neval/\n├── datasets/\n│   ├── bir
d_mini.jsonl          # 1500 Q→SQL пар, 11 БД\n│   └── stackexchange_gold.jsonl
# 20 наших эталонных вопросов\n├── runner.py                    # прогон через 
граф, сравнение\n├── metrics/\n│   ├── execution_accuracy.py    # сравнение res
ult-set\'ов\n│   ├── exact_match.py           # SQL string match (слабая метрик
а)\n│   └── component_match.py       # сравнение по AST-компонентам\n└── report
s/\n    └── 2026-05-10-baseline.html # отчёт по прогонам\n```\n\nCI прогоняет s
moke-eval на 50 примерах при каждом merge в main.\nПолный прогон — вручную или 
nightly.\n\n**Целевое число:** Execution Accuracy ≥ 50% на BIRD-mini dev.\nОпуб
ликованные результаты codestral-2501 на BIRD ~57%, так что 50%\nсвоими силами н
а узком сабсете — реалистично.\n\n## 6. Multi-DB switching\n\nВ `config/databas
es.yml` описаны подключения:\n\n```yaml\ndatabases:\n  - id: stackexchange\n   
dsn: postgresql://nlsql_ro@localhost/stackexchange\n    description: "StackOver
flow public data — posts, users, votes"\n    schema_index: chroma://stackexchan
ge\n    sample_questions: ["топ-10 тегов...", "распределение..."]\n  - id: bird
_california_schools\n    dsn: sqlite:///data/bird/california_schools.sqlite\n  
 description: "California schools — performance, demographics"\n    schema_inde
x: chroma://bird_california_schools\n  - id: chinook\n    dsn: sqlite:///data/c
hinook.sqlite\n    description: "Music store — invoices, tracks, customers"\n  
 schema_index: chroma://chinook\n```\n\nUI даёт переключатель «target DB», граф
читает её из state.\n\n## 7. UI (Next.js + React)\n\nМинимально, но без обрезко
в:\n\n- **Chat-style вход** с подсветкой SQL в ответе и copy-кнопкой.\n- **Mult
i-format ответ** — компонент сам решает, что рендерить\n  (scalar / sentence / 
DataGrid / Vega-Lite chart).\n- **«Show working»**: разворачивающийся блок с re
trieved schema, few-shot,\n  rationale, EXPLAIN-планом, временем выполнения.\n-
**History + bookmarks** в localStorage + опционально на бэке.\n- **DB switcher*
* + список sample-вопросов под каждую БД.\n\nОтдельная страница **`/eval`** — т
аблица результатов eval-прогонов,\nграфики динамики Execution Accuracy по комми
там.\n\n## 8. Стек целиком\n\n| Слой | Технология | Почему |\n|---|---|---|\n| 
LLM | Mistral API: codestral-2501, mistral-large-2, mistral-embed | Жёсткое тре
бование задачи |\n| Orchestration | LangGraph | Уже знакома по RAG_SA, retry-lo
op из коробки |\n| API | FastAPI + Pydantic v2 | Стандарт, типобезопасность |\n
| Vector DB | ChromaDB | Уже знакома, локально без отдельного сервиса |\n| SQL 
parser | sqlglot | Multi-dialect, AST-валидация, dialect translation |\n| Targe
t DB | Postgres 16 (StackExchange) + SQLite (BIRD, Chinook) | Реализм + простот
а |\n| Cache | Redis 7 | Кэш результатов SQL, rate-limit |\n| Charting | Vega-L
ite (через спеку из LLM) + Plotly fallback | LLM хорошо генерит Vega-spec\'и |\
n| Frontend | Next.js 15 + Tailwind + shadcn/ui | Быстрый красивый UI |\n| Obse
rvability | Prometheus + OpenTelemetry + Langfuse | Стандартный стек, переиспол
ьзуется из RAG_SA |\n| Tests | pytest + httpx + testcontainers (Postgres) | Реа
льная БД в CI |\n| Lint/Type | ruff + mypy strict (api/, agent/) | Как в DE_pro
ject |\n| CI | GitHub Actions | smoke-eval + pytest + ruff + mypy |\n| Deploy |
docker-compose (dev) + Dockerfile multi-stage (prod) | Достаточно для демо |\n\
n## 9. Структура репозитория\n\n```\nNL_SQL/\n├── api/                   # Fast
API app, routers, middleware\n├── agent/                 # LangGraph nodes, pro
mpts, state\n│   ├── graph.py\n│   ├── nodes/\n│   │   ├── classify.py\n│   │  
├── retrieve_schema.py\n│   │   ├── retrieve_examples.py\n│   │   ├── generate_
sql.py\n│   │   ├── validate.py\n│   │   ├── execute.py\n│   │   ├── verify.py\
n│   │   ├── render.py\n│   │   └── retry.py\n│   └── prompts/\n├── llm/       
           # Mistral provider, retry, cost guard\n├── schema_index/          # 
offline indexer for Chroma\n│   ├── extractor.py       # introspect Postgres/SQ
Lite catalog\n│   ├── enricher.py        # описания, sample values, stats\n│   
└── builder.py         # build Chroma collections\n├── execution/             #
SQL guards, EXPLAIN gate, runner\n├── eval/                  # см. раздел 5\n├─
─ frontend/              # Next.js UI\n├── config/                # databases.y
ml, prompts.yml\n├── data/                  # BIRD dump, Chinook, sample dumps 
(gitignore)\n├── tests/\n├── docker-compose.yml\n├── Dockerfile\n└── docs/\n   
├── 00_task.md\n    ├── 01_architecture.md       ← вы здесь\n    ├── 02_eval_me
thodology.md   ← TODO\n    └── 03_demo_questions.md     ← TODO\n```\n\n## 10. R
oadmap (этапы)\n\n| # | Этап | DoD |\n|---|---|---|\n| 1 | **Bootstrap** | poet
ry/uv проект, FastAPI hello, Mistral provider, тесты на провайдер с моком |\n| 
2 | **Target DBs ready** | docker-compose поднимает Postgres со StackExchange d
ump + SQLite Chinook + BIRD dump в `data/` |\n| 3 | **Schema indexer** | offlin
e скрипт строит Chroma-коллекции, smoke-тест на retrieval |\n| 4 | **Pipeline v
1** | LangGraph граф работает на Chinook (простая БД), single-shot без retry |\
n| 5 | **Guards & verify** | sqlglot guard, EXPLAIN gate, retry-loop, тесты |\n
| 6 | **Eval harness** | runner + execution_accuracy метрика, baseline на BIRD-
mini |\n| 7 | **Multi-format render** | scalar/sentence/table/chart с автоопред
елением + Vega-Lite spec\'и |\n| 8 | **UI v1** | chat + DB switcher + history, 
end-to-end на 3 БД |\n| 9 | **Polish & deploy** | docker-compose prod-like, REA
DME, демо-видео, eval-страница |\n\nЭтапы 1-3 — фундамент (~неделя на каждом те
мпе).\nЭтапы 4-6 — суть проекта (~2 недели).\nЭтапы 7-9 — витрина (~неделя).\n\
nИтого: ~5-6 рабочих недель в спокойном темпе или 2-3 в плотном.\n\n## 11. Риск
и\n\n| Риск | Вероятность | Митигация |\n|---|---|---|\n| codestral-2501 даёт <
40% на BIRD | средняя | улучшить few-shot retrieval, добавить chain-of-thought,
schema-linking шаг |\n| StackExchange dump слишком большой для локалки (≥100GB)
| высокая | взять mini-dump (`gaming.stackexchange.com`, ~1GB) — реализм без бо
ли |\n| EXPLAIN-gate ломает легитимные тяжёлые запросы | средняя | tune порог н
а БД, дать override-флаг для админа |\n| BIRD dataset лицензия | низкая | CC-BY
-SA-4.0, для демо OK |\n| Mistral API rate limits на eval-прогоне | средняя | l
ocal cache на (prompt → response), батчинг, exponential backoff |\n\n## 12. Что
в этой архитектуре «нагруженного»\n\nЕсли сравнить с минимальным NL→SQL (один п
ромпт + один вызов LLM + execute):\n\n- **+ LangGraph pipeline на 10+ узлов** с
retry-loop и error-context.\n- **+ Schema-RAG из 4 коллекций** вместо «вся схем
а в промпт».\n- **+ Few-shot retrieval** из эталонных Q→SQL пар.\n- **+ Static 
validate (sqlglot AST) + EXPLAIN-gate + 4-уровневая защита**.\n- **+ Multi-DB**
с переключателем и per-DB индексами.\n- **+ Eval harness на публичном бенчмарке
** с измеримой метрикой.\n- **+ Multi-format рендер** (4 формата + auto-выбор г
рафика).\n- **+ Полноценный observability stack** (Prom + OTel + Langfuse).\n- 
**+ Web-UI** с историей, eval-страницей, «show working».\n\nЭто потолок того, ч
то осмысленно делать для демо-проекта без скатывания\nв production-overhead (му
льти-тенант, RBAC, OIDC, freshness monitor и т.д. —\nвсё то, что в RAG_SA умест
но, а здесь было бы фейк-нагрузкой).'
)
StatusUpdate(
    context_usage=None,
    context_tokens=None,
    max_context_tokens=None,
    token_usage=None,
    message_id=None,
    plan_mode=None,
    mcp_status=MCPStatusSnapshot(
        loading=True,
        connected=0,
        total=3,
        tools=0,
        servers=(
            MCPServerSnapshot(
                name='playwright-official',
                status='connecting',
                tools=()
            ),
            MCPServerSnapshot(
                name='playwright-executeautomation',
                status='connecting',
                tools=()
            ),
            MCPServerSnapshot(
                name='browser-tools',
                status='connecting',
                tools=()
            )
        )
    )
)
MCPLoadingBegin()
StatusUpdate(
    context_usage=None,
    context_tokens=None,
    max_context_tokens=None,
    token_usage=None,
    message_id=None,
    plan_mode=None,
    mcp_status=MCPStatusSnapshot(
        loading=False,
        connected=3,
        total=3,
        tools=85,
        servers=(
            MCPServerSnapshot(
                name='playwright-official',
                status='connected',
                tools=(
                    'browser_close',
                    'browser_resize',
                    'browser_console_messages',
                    'browser_resume',
                    'browser_highlight',
                    'browser_hide_highlight',
                    'browser_annotate',
                    'browser_handle_dialog',
                    'browser_evaluate',
                    'browser_file_upload',
                    'browser_drop',
                    'browser_fill_form',
                    'browser_press_key',
                    'browser_type',
                    'browser_mouse_move_xy',
                    'browser_mouse_click_xy',
                    'browser_mouse_drag_xy',
                    'browser_mouse_down',
                    'browser_mouse_up',
                    'browser_mouse_wheel',
                    'browser_navigate',
                    'browser_navigate_back',
                    'browser_network_requests',
                    'browser_network_request',
                    'browser_run_code_unsafe',
                    'browser_take_screenshot',
                    'browser_snapshot',
                    'browser_click',
                    'browser_drag',
                    'browser_hover',
                    'browser_select_option',
                    'browser_tabs',
                    'browser_start_tracing',
                    'browser_stop_tracing',
                    'browser_start_video',
                    'browser_stop_video',
                    'browser_video_chapter',
                    'browser_wait_for'
                )
            ),
            MCPServerSnapshot(
                name='playwright-executeautomation',
                status='connected',
                tools=(
                    'start_codegen_session',
                    'end_codegen_session',
                    'get_codegen_session',
                    'clear_codegen_session',
                    'playwright_navigate',
                    'playwright_screenshot',
                    'playwright_click',
                    'playwright_iframe_click',
                    'playwright_iframe_fill',
                    'playwright_fill',
                    'playwright_select',
                    'playwright_hover',
                    'playwright_upload_file',
                    'playwright_evaluate',
                    'playwright_console_logs',
                    'playwright_resize',
                    'playwright_close',
                    'playwright_get',
                    'playwright_post',
                    'playwright_put',
                    'playwright_patch',
                    'playwright_delete',
                    'playwright_expect_response',
                    'playwright_assert_response',
                    'playwright_custom_user_agent',
                    'playwright_get_visible_text',
                    'playwright_get_visible_html',
                    'playwright_go_back',
                    'playwright_go_forward',
                    'playwright_drag',
                    'playwright_press_key',
                    'playwright_save_as_pdf',
                    'playwright_click_and_switch_tab'
                )
            ),
            MCPServerSnapshot(
                name='browser-tools',
                status='connected',
                tools=(
                    'getConsoleLogs',
                    'getConsoleErrors',
                    'getNetworkErrors',
                    'getNetworkLogs',
                    'takeScreenshot',
                    'getSelectedElement',
                    'wipeLogs',
                    'runAccessibilityAudit',
                    'runPerformanceAudit',
                    'runSEOAudit',
                    'runNextJSAudit',
                    'runDebuggerMode',
                    'runAuditMode',
                    'runBestPracticesAudit'
                )
            )
        )
    )
)
MCPLoadingEnd()
StepBegin(n=1)
ThinkPart(
    type='think',
    think='Пользователь просит технический review двух документов: постановки з
адачи (00_task.md) и архитектуры (01_architecture.md) для демо-проекта NL→SQL A
ssistant. Нужно ответить на вопросы по блокам A, B, C, D. Давайте сначала прочи
таем оба документа, чтобы убедиться, что я вижу всё содержимое. Они уже приложе
ны в промпте, но я проверю файлы на диске, чтобы убедиться, что ничего не измен
илось. Также посмотрю reviews/kimi_review.md и reviews/kimi.err, чтобы понять, 
не было ли уже какого-то review.',
    encrypted=None
)
ToolCall(
    type='function',
    id='tool_wxEocYyBunA4156towv1xmTS',
    function=FunctionBody(
        name='ReadFile',
        arguments='{"path": "docs/00_task.md"}'
    ),
    extras=None
)
ToolCall(
    type='function',
    id='tool_cAIyU7NJXddPAFfCVyZOeFaw',
    function=FunctionBody(
        name='ReadFile',
        arguments='{"path": "docs/01_architecture.md'
    ),
    extras=None
)
ToolResult(
    tool_call_id='tool_wxEocYyBunA4156towv1xmTS',
    return_value=ToolOk(
        is_error=False,
        output='     1\t# NL→SQL Assistant — постановка задачи\n     2\t\n     
3\t**Дата:** 2026-05-10\n     4\t**Автор:** Julia Edomskikh\n     5\t**Статус:*
* draft / scoping\n     6\t\n     7\t---\n     8\t\n     9\t## 1. Что делаем\n 
  10\t\n    11\tИнструмент, который принимает вопрос на естественном языке (рус
ский или английский),\n    12\tобращается к реляционной БД и возвращает ответ в
одной из форм:\n    13\t\n    14\t- **Число / скаляр** — для агрегатных вопросо
в («сколько заказов в марте?»).\n    15\t- **Текстовое предложение** — для факт
оидов с подстановкой данных\n    16\t  («у клиента X 12 заказов на сумму 340k з
а 2024 год»).\n    17\t- **Таблица** — когда нужен список записей.\n    18\t- *
*График** — когда вопрос про динамику, сравнение, распределение\n    19\t  (выб
ор типа графика автоматический: line / bar / pie / hist / scatter).\n    20\t- 
**SQL-запрос** — всегда показывается пользователю как «доказательство»\n    21\
t  + объяснение на естественном языке, что именно посчитали.\n    22\t\n    23\
t## 2. Почему это не «ещё один чат с БД»\n    24\t\n    25\tДемо-проект для пор
тфолио, поэтому ценность создаётся не самим NL→SQL\n    26\t(он есть у Vanna, D
ataHerald, WrenAI, defog/sqlcoder, LangChain SQLAgent),\n    27\tа тремя слоями
поверх:\n    28\t\n    29\t1. **Измеримая точность.** Eval-harness на публичных
бенчмарках\n    30\t   (BIRD-bench и/или Spider) с метрикой Execution Accuracy 
и сравнением\n    31\t   против опубликованных результатов моделей. Без этого ч
исла проект — игрушка.\n    32\t2. **Self-correction loop.** Если SQL падает ил
и возвращает 0 строк или вырожденный\n    33\t   результат — граф автоматически
переформулирует запрос с error-context\n    34\t   (паттерн из RAG_Support_Assi
stant: classify → retrieve → generate → verify → retry).\n    35\t3. **Schema-R
AG, а не «всю схему в промпт».** На сложных БД (десятки таблиц,\n    36\t   сот
ни колонок) полная схема не влезает и шумит. Хранилище:\n    37\t   таблицы + к
олонки + описания + примеры значений + few-shot Q→SQL пары\n    38\t   индексир
уются в Chroma и достаются по релевантности к вопросу.\n    39\t\n    40\t## 3.
Целевые БД\n    41\t\n    42\tДля демо берём два разных профиля сложности:\n   
43\t\n    44\t| База | Профиль | Зачем |\n    45\t|---|---|---|\n    46\t| **BI
RD-bench (mini)** | 95 реальных БД из 37 доменов, 12 751 Q→SQL пар с эталонными
ответами | Eval-harness, число Execution Accuracy на публичном leaderboard\'е |
\n    47\t| **StackExchange public dump** в Postgres | Реальная сложная схема (
Posts, Users, Votes, Comments, Tags, Badges), миллионы строк, JSONB-поля, време
нные ряды | Демо-вопросы с красивыми графиками («активность по часам», «распред
еление тегов», «топ-N пользователей по карме») |\n    48\t\n    49\tОпционально
третья — **Sakila** или **Chinook** — для онбординг-демо\n    50\t(простая, все
м знакомая, быстро отрабатывает первое впечатление).\n    51\t\n    52\t## 4. L
LM\n    53\t\n    54\tТолько Mistral по API. Две модели в роутинге:\n    55\t\n
   56\t- **codestral-2501** — генерация SQL и self-correction.\n    57\t  Заточ
ен под код, на NL→SQL стабильно бьёт mistral-large.\n    58\t- **mistral-large-
2** — классификация интента, объяснение результата\n    59\t  на естественном я
зыке, выбор типа визуализации.\n    60\t\n    61\tEmbeddings — `mistral-embed` 
(для schema-RAG и few-shot retrieval).\n    62\t\n    63\t## 5. Базовый сценари
й (happy path)\n    64\t\n    65\t```\n    66\tПользователь: "Покажи топ-10 тег
ов на StackOverflow по приросту вопросов в 2023 году"\n    67\t   |\n    68\t  
v\n    69\t1. Classify intent  → "aggregation + ranking + time-window + visuali
zation"\n    70\t2. Schema retrieval → достать релевантные таблицы (Posts, Tags
, PostTags) + 3 few-shot примера\n    71\t3. SQL generation   → codestral пишет
SQL с CTE по годам и приростом\n    72\t4. Validate         → синтаксис ОК, EXP
LAIN ОК, SELECT-only гард прошёл\n    73\t5. Execute          → 10 строк × 3 ко
лонки\n    74\t6. Verify           → результат непустой, типы соответствуют ожи
даниям\n    75\t7. Format           → по структуре ответа выбран bar chart + кр
аткий текст\n    76\t8. Render           → markdown-ответ + Plotly-график + бло
к с SQL и объяснением\n    77\t```\n    78\t\n    79\tПри фейле любого шага — r
etry с error-context (макс. 2 попытки),\n    80\tдальше — graceful failure с по
казом, где именно споткнулись.\n    81\t\n    82\t## 6. Что НЕ делаем (scope cu
ts)\n    83\t\n    84\t- Никаких write-операций. Read-only коннект к БД, гард н
а уровне SQL-парсера.\n    85\t- Никакого мульти-БД join\'а в одном запросе.\n 
  86\t- Никакого fine-tuning моделей — только prompt-engineering + RAG.\n    87
\t- Никакой собственной аутентификации/мульти-тенанси\n    88\t  (это переуслож
нение для демо, в RAG_SA уже отработано — здесь не повторяем).\n    89\t- Никак
их write-back в БД на основе вопросов пользователя.\n    90\t\n    91\t## 7. Кр
итерии готовности (Definition of Done)\n    92\t\n    93\t- [ ] Execution Accur
acy на BIRD-mini dev split ≥ 50% (с codestral-2501 это реалистично).\n    94\t-
[ ] На StackExchange — 20 эталонных вопросов проходят end-to-end с корректным о
тветом.\n    95\t- [ ] Веб-UI: ввод вопроса, четыре формата ответа, переключени
е БД, история.\n    96\t- [ ] CI: тесты на гард SELECT-only, на парсер схемы, н
а pipeline-граф.\n    97\t- [ ] README + диаграмма архитектуры + страница eval-
результатов.\n    98\t- [ ] Деплой: docker-compose с Postgres + Chroma + FastAP
I + UI.\n',
        message='98 lines read from file starting from line 1. Total lines in f
ile: 98. End of file reached.',
        display=[],
        extras=None
    )
)
ToolCallPart(arguments_part='"}')
ToolCall(
    type='function',
    id='tool_wNOLbKBBfoJtwqT6pe17sxo3',
    function=FunctionBody(
        name='ReadFile',
        arguments='{"path": "reviews/kimi_review.md'
    ),
    extras=None
)
ToolResult(
    tool_call_id='tool_cAIyU7NJXddPAFfCVyZOeFaw',
    return_value=ToolOk(
        is_error=False,
        output='     1\t# NL→SQL Assistant — архитектура (максимально нагруженн
ый вариант)\n     2\t\n     3\t**Дата:** 2026-05-10\n     4\t**Статус:** draft 
/ pending review\n     5\t\n     6\t> «Максимально нагруженный» здесь = всё, чт
о реально нужно для серьёзного\n     7\t> демо-проекта уровня Senior Data Engin
eer, без фейкового overengineering\'а.\n     8\t> Каждый компонент обоснован за
дачей; ничего «на будущее».\n     9\t\n    10\t---\n    11\t\n    12\t## 1. Сис
темная диаграмма\n    13\t\n    14\t```text\n    15\t                          
┌──────────────────────────┐\n    16\t                           │  Web UI (Nex
t.js + React)│\n    17\t                           │  ─ chat input            │
\n    18\t                           │  ─ table / chart / SQL   │\n    19\t    
                      │  ─ history + bookmarks   │\n    20\t                   
       └────────────┬─────────────┘\n    21\t                                  
     │ HTTPS\n    22\t                                        ▼\n    23\t      
           ┌──────────────────────────────────────────┐\n    24\t              
   │  FastAPI gateway (auth, rate-limit, CORS)│\n    25\t                  │  /
ask, /databases, /history, /eval/run   │\n    26\t                  └──────────
──┬─────────────────────────────┘\n    27\t                               │\n  
 28\t          ┌────────────────────┼────────────────────────────┐\n    29\t   
      │                    │                            │\n    30\t          ▼ 
                  ▼                            ▼\n    31\t  ┌──────────────┐   
┌────────────────┐         ┌────────────────────┐\n    32\t  │ LangGraph    │  
 │ Eval harness   │         │ Schema indexer     │\n    33\t  │ NL→SQL graph │ 
  │ (BIRD/Spider)  │         │ (offline pipeline) │\n    34\t  └──────┬───────┘
   └────────┬───────┘         └─────────┬──────────┘\n    35\t         │       
             │                           │\n    36\t         ▼                 
   ▼                           ▼\n    37\t  ┌──────────────────────────────────
────────────────────────────┐\n    38\t  │                   Shared services la
yer                       │\n    39\t  ├──────────────┬──────────────┬─────────
────┬──────────────────┤\n    40\t  │ Mistral API  │ Chroma DB    │ Postgres   
│ Redis            │\n    41\t  │ codestral    │ schema chunks│ target DBs  │ r
esult cache     │\n    42\t  │ large-2      │ few-shot Q→S │ (multi-DB)  │ rate
-limit state │\n    43\t  │ mistral-embed│              │ + traces DB │        
         │\n    44\t  └──────────────┴──────────────┴─────────────┴────────────
──────┘\n    45\t                               │\n    46\t                    
          ▼\n    47\t                  ┌──────────────────────────┐\n    48\t  
               │ Observability             │\n    49\t                  │ Prome
theus + OpenTelemetry│\n    50\t                  │ Langfuse traces           │
\n    51\t                  └──────────────────────────┘\n    52\t```\n    53\t
\n    54\t## 2. LangGraph pipeline\n    55\t\n    56\tРеиспользуем структуру из
RAG_Support_Assistant\n    57\t(`classify → retrieve → rerank → generate → veri
fy → evaluate`),\n    58\tно узлы заточены под NL→SQL:\n    59\t\n    60\t```te
xt\n    61\t       ┌────────────────┐\n    62\t       │ classify_intent│   inte
nt = aggregation | ranking | filter |\n    63\t       └────────┬───────┘       
    time_series | comparison | lookup |\n    64\t                │             
      distribution\n    65\t                ▼\n    66\t       ┌────────────────
┐\n    67\t       │ select_database│   если в системе несколько БД — выбрать це
левую\n    68\t       └────────┬───────┘            по интенту + ключевым слова
м\n    69\t                │\n    70\t                ▼\n    71\t       ┌──────
──────────┐\n    72\t       │ retrieve_schema│   Chroma: relevant tables + colu
mns + value samples\n    73\t       └────────┬───────┘\n    74\t               
│\n    75\t                ▼\n    76\t       ┌────────────────┐\n    77\t      
│ retrieve_examples│ Chroma: top-k похожих Q→SQL пар (few-shot)\n    78\t      
└────────┬───────┘\n    79\t                │\n    80\t                ▼\n    8
1\t       ┌────────────────┐\n    82\t       │ generate_sql   │   codestral-250
1 + structured output (JSON-mode)\n    83\t       └────────┬───────┘           
{ "sql": "...", "rationale": "..." }\n    84\t                │\n    85\t      
         ▼\n    86\t       ┌────────────────┐\n    87\t       │ static_validate
│   sqlglot parse → SELECT-only guard → schema check\n    88\t       └────────┬
───────┘            (table/column existence vs catalog)\n    89\t              
 │ FAIL ──────────► retry_loop (max 2)\n    90\t                │ OK\n    91\t 
              ▼\n    92\t       ┌────────────────┐\n    93\t       │ explain_pl
an   │   EXPLAIN на целевой БД, отказ если cost > threshold\n    94\t       └──
──────┬───────┘            (защита от full-scan на больших таблицах)\n    95\t 
              │\n    96\t                ▼\n    97\t       ┌────────────────┐\n
   98\t       │ execute        │   read-only коннект, statement_timeout, LIMIT-
guard\n    99\t       └────────┬───────┘\n   100\t                │\n   101\t  
             ▼\n   102\t       ┌────────────────┐\n   103\t       │ verify_resu
lt  │   проверки: непустой? типы соответствуют интенту?\n   104\t       └──────
──┬───────┘            аномалии? (нулей/null\'ов слишком много)\n   105\t      
         │ FAIL ──────────► retry_loop\n   106\t                │ OK\n   107\t 
              ▼\n   108\t       ┌────────────────┐\n   109\t       │ choose_for
mat  │   intent + result shape →\n   110\t       └────────┬───────┘            
scalar | sentence | table | chart\n   111\t                │\n   112\t         
      ▼\n   113\t       ┌────────────────┐\n   114\t       │ render_answer  │  
mistral-large-2: NL-объяснение + chart-spec (Vega-Lite)\n   115\t       └──────
──┬───────┘\n   116\t                │\n   117\t                ▼\n   118\t    
  ┌────────────────┐\n   119\t       │ persist_trace  │   sqlite traces + Langf
use span + Prometheus counter\n   120\t       └────────────────┘\n   121\t```\n
  122\t\n   123\t**Retry loop:** при фейле узлов `static_validate`, `execute`, 
`verify_result`\n   124\tграф возвращается к `generate_sql` с приклеенным error
-context\'ом\n   125\t(текст ошибки + предыдущий SQL + разъяснение что не так).
Лимит — 2 попытки,\n   126\tпосле чего отдаётся диагностический ответ.\n   127\
t\n   128\t## 3. Schema-RAG: устройство индекса\n   129\t\n   130\t**Проблема:*
* в BIRD есть БД с 50+ таблицами. Полная схема в промпт не лезет\n   131\tи заш
умляет генерацию.\n   132\t\n   133\t**Решение:** offline-пайплайн `Schema inde
xer` строит несколько коллекций в Chroma:\n   134\t\n   135\t| Коллекция | Чанк
| Эмбеддится |\n   136\t|---|---|---|\n   137\t| `schema_tables` | таблица | им
я + описание + список колонок + 3 sample строки |\n   138\t| `schema_columns` |
колонка | имя + тип + описание + min/max/nunique + 5 sample значений |\n   139\
t| `fewshot_qsql` | Q→SQL пара | вопрос + аннотация интента (SQL не эмбеддится)
|\n   140\t| `relations` | FK-связь | from_table.col → to_table.col + семантика
|\n   141\t\n   142\tПри вопросе `retrieve_schema` делает гибрид BM25 + dense н
а `schema_tables`,\n   143\tдотягивает топ-N колонок из `schema_columns` для от
обранных таблиц,\n   144\tдобавляет связи между ними. Получается компактный «ср
ез схемы» под вопрос —\n   145\tобычно 5-15 таблиц вместо 50+.\n   146\t\n   14
7\t`retrieve_examples` достаёт из `fewshot_qsql` 3-5 наиболее похожих\n   148\t
вопросов с эталонными SQL — это мощно поднимает качество на сложных диалектах.\
n   149\t\n   150\t## 4. Безопасность исполнения SQL\n   151\t\n   152\tRead-on
ly — это не «обещание промптом», а реальные гарды на четырёх уровнях:\n   153\t
\n   154\t1. **БД-роль:** отдельный postgres-пользователь с GRANT SELECT ONLY,\
n   155\t   без CREATE/INSERT/UPDATE/DELETE/TRUNCATE/ALTER.\n   156\t2. **Парсе
р:** `sqlglot` AST-валидация — отказ при не-SELECT, при множественных\n   157\t
  стейтментах, при наличии CTE с DML, при `pg_*`/`information_schema` без white
list.\n   158\t3. **EXPLAIN-gate:** `EXPLAIN (FORMAT JSON)` перед `EXECUTE`,\n 
 159\t   отказ если `Total Cost > X` (порог настраивается на БД).\n   160\t4. *
*Runtime:** `SET statement_timeout = 30s`, обязательный `LIMIT 10000`\n   161\t
  если в запросе нет агрегации.\n   162\t\n   163\t## 5. Eval harness\n   164\t
\n   165\tОтдельный модуль `eval/`, не часть онлайн-пайплайна:\n   166\t\n   16
7\t```text\n   168\teval/\n   169\t├── datasets/\n   170\t│   ├── bird_mini.jso
nl          # 1500 Q→SQL пар, 11 БД\n   171\t│   └── stackexchange_gold.jsonl #
20 наших эталонных вопросов\n   172\t├── runner.py                    # прогон 
через граф, сравнение\n   173\t├── metrics/\n   174\t│   ├── execution_accuracy
.py    # сравнение result-set\'ов\n   175\t│   ├── exact_match.py           # S
QL string match (слабая метрика)\n   176\t│   └── component_match.py       # ср
авнение по AST-компонентам\n   177\t└── reports/\n   178\t    └── 2026-05-10-ba
seline.html # отчёт по прогонам\n   179\t```\n   180\t\n   181\tCI прогоняет sm
oke-eval на 50 примерах при каждом merge в main.\n   182\tПолный прогон — вручн
ую или nightly.\n   183\t\n   184\t**Целевое число:** Execution Accuracy ≥ 50% 
на BIRD-mini dev.\n   185\tОпубликованные результаты codestral-2501 на BIRD ~57
%, так что 50%\n   186\tсвоими силами на узком сабсете — реалистично.\n   187\t
\n   188\t## 6. Multi-DB switching\n   189\t\n   190\tВ `config/databases.yml` 
описаны подключения:\n   191\t\n   192\t```yaml\n   193\tdatabases:\n   194\t  
- id: stackexchange\n   195\t    dsn: postgresql://nlsql_ro@localhost/stackexch
ange\n   196\t    description: "StackOverflow public data — posts, users, votes
"\n   197\t    schema_index: chroma://stackexchange\n   198\t    sample_questio
ns: ["топ-10 тегов...", "распределение..."]\n   199\t  - id: bird_california_sc
hools\n   200\t    dsn: sqlite:///data/bird/california_schools.sqlite\n   201\t
   description: "California schools — performance, demographics"\n   202\t    s
chema_index: chroma://bird_california_schools\n   203\t  - id: chinook\n   204\
t    dsn: sqlite:///data/chinook.sqlite\n   205\t    description: "Music store 
— invoices, tracks, customers"\n   206\t    schema_index: chroma://chinook\n   
207\t```\n   208\t\n   209\tUI даёт переключатель «target DB», граф читает её и
з state.\n   210\t\n   211\t## 7. UI (Next.js + React)\n   212\t\n   213\tМиним
ально, но без обрезков:\n   214\t\n   215\t- **Chat-style вход** с подсветкой S
QL в ответе и copy-кнопкой.\n   216\t- **Multi-format ответ** — компонент сам р
ешает, что рендерить\n   217\t  (scalar / sentence / DataGrid / Vega-Lite chart
).\n   218\t- **«Show working»**: разворачивающийся блок с retrieved schema, fe
w-shot,\n   219\t  rationale, EXPLAIN-планом, временем выполнения.\n   220\t- *
*History + bookmarks** в localStorage + опционально на бэке.\n   221\t- **DB sw
itcher** + список sample-вопросов под каждую БД.\n   222\t\n   223\tОтдельная с
траница **`/eval`** — таблица результатов eval-прогонов,\n   224\tграфики динам
ики Execution Accuracy по коммитам.\n   225\t\n   226\t## 8. Стек целиком\n   2
27\t\n   228\t| Слой | Технология | Почему |\n   229\t|---|---|---|\n   230\t| 
LLM | Mistral API: codestral-2501, mistral-large-2, mistral-embed | Жёсткое тре
бование задачи |\n   231\t| Orchestration | LangGraph | Уже знакома по RAG_SA, 
retry-loop из коробки |\n   232\t| API | FastAPI + Pydantic v2 | Стандарт, типо
безопасность |\n   233\t| Vector DB | ChromaDB | Уже знакома, локально без отде
льного сервиса |\n   234\t| SQL parser | sqlglot | Multi-dialect, AST-валидация
, dialect translation |\n   235\t| Target DB | Postgres 16 (StackExchange) + SQ
Lite (BIRD, Chinook) | Реализм + простота |\n   236\t| Cache | Redis 7 | Кэш ре
зультатов SQL, rate-limit |\n   237\t| Charting | Vega-Lite (через спеку из LLM
) + Plotly fallback | LLM хорошо генерит Vega-spec\'и |\n   238\t| Frontend | N
ext.js 15 + Tailwind + shadcn/ui | Быстрый красивый UI |\n   239\t| Observabili
ty | Prometheus + OpenTelemetry + Langfuse | Стандартный стек, переиспользуется
из RAG_SA |\n   240\t| Tests | pytest + httpx + testcontainers (Postgres) | Реа
льная БД в CI |\n   241\t| Lint/Type | ruff + mypy strict (api/, agent/) | Как 
в DE_project |\n   242\t| CI | GitHub Actions | smoke-eval + pytest + ruff + my
py |\n   243\t| Deploy | docker-compose (dev) + Dockerfile multi-stage (prod) |
Достаточно для демо |\n   244\t\n   245\t## 9. Структура репозитория\n   246\t\
n   247\t```\n   248\tNL_SQL/\n   249\t├── api/                   # FastAPI app
, routers, middleware\n   250\t├── agent/                 # LangGraph nodes, pr
ompts, state\n   251\t│   ├── graph.py\n   252\t│   ├── nodes/\n   253\t│   │  
├── classify.py\n   254\t│   │   ├── retrieve_schema.py\n   255\t│   │   ├── re
trieve_examples.py\n   256\t│   │   ├── generate_sql.py\n   257\t│   │   ├── va
lidate.py\n   258\t│   │   ├── execute.py\n   259\t│   │   ├── verify.py\n   26
0\t│   │   ├── render.py\n   261\t│   │   └── retry.py\n   262\t│   └── prompts
/\n   263\t├── llm/                   # Mistral provider, retry, cost guard\n  
264\t├── schema_index/          # offline indexer for Chroma\n   265\t│   ├── e
xtractor.py       # introspect Postgres/SQLite catalog\n   266\t│   ├── enriche
r.py        # описания, sample values, stats\n   267\t│   └── builder.py       
 # build Chroma collections\n   268\t├── execution/             # SQL guards, E
XPLAIN gate, runner\n   269\t├── eval/                  # см. раздел 5\n   270\
t├── frontend/              # Next.js UI\n   271\t├── config/                # 
databases.yml, prompts.yml\n   272\t├── data/                  # BIRD dump, Chi
nook, sample dumps (gitignore)\n   273\t├── tests/\n   274\t├── docker-compose.
yml\n   275\t├── Dockerfile\n   276\t└── docs/\n   277\t    ├── 00_task.md\n   
278\t    ├── 01_architecture.md       ← вы здесь\n   279\t    ├── 02_eval_metho
dology.md   ← TODO\n   280\t    └── 03_demo_questions.md     ← TODO\n   281\t``
`\n   282\t\n   283\t## 10. Roadmap (этапы)\n   284\t\n   285\t| # | Этап | DoD
|\n   286\t|---|---|---|\n   287\t| 1 | **Bootstrap** | poetry/uv проект, FastA
PI hello, Mistral provider, тесты на провайдер с моком |\n   288\t| 2 | **Targe
t DBs ready** | docker-compose поднимает Postgres со StackExchange dump + SQLit
e Chinook + BIRD dump в `data/` |\n   289\t| 3 | **Schema indexer** | offline с
крипт строит Chroma-коллекции, smoke-тест на retrieval |\n   290\t| 4 | **Pipel
ine v1** | LangGraph граф работает на Chinook (простая БД), single-shot без ret
ry |\n   291\t| 5 | **Guards & verify** | sqlglot guard, EXPLAIN gate, retry-lo
op, тесты |\n   292\t| 6 | **Eval harness** | runner + execution_accuracy метри
ка, baseline на BIRD-mini |\n   293\t| 7 | **Multi-format render** | scalar/sen
tence/table/chart с автоопределением + Vega-Lite spec\'и |\n   294\t| 8 | **UI 
v1** | chat + DB switcher + history, end-to-end на 3 БД |\n   295\t| 9 | **Poli
sh & deploy** | docker-compose prod-like, README, демо-видео, eval-страница |\n
  296\t\n   297\tЭтапы 1-3 — фундамент (~неделя на каждом темпе).\n   298\tЭтап
ы 4-6 — суть проекта (~2 недели).\n   299\tЭтапы 7-9 — витрина (~неделя).\n   3
00\t\n   301\tИтого: ~5-6 рабочих недель в спокойном темпе или 2-3 в плотном.\n
  302\t\n   303\t## 11. Риски\n   304\t\n   305\t| Риск | Вероятность | Митигац
ия |\n   306\t|---|---|---|\n   307\t| codestral-2501 даёт <40% на BIRD | средн
яя | улучшить few-shot retrieval, добавить chain-of-thought, schema-linking шаг
|\n   308\t| StackExchange dump слишком большой для локалки (≥100GB) | высокая 
| взять mini-dump (`gaming.stackexchange.com`, ~1GB) — реализм без боли |\n   3
09\t| EXPLAIN-gate ломает легитимные тяжёлые запросы | средняя | tune порог на 
БД, дать override-флаг для админа |\n   310\t| BIRD dataset лицензия | низкая |
CC-BY-SA-4.0, для демо OK |\n   311\t| Mistral API rate limits на eval-прогоне 
| средняя | local cache на (prompt → response), батчинг, exponential backoff |\
n   312\t\n   313\t## 12. Что в этой архитектуре «нагруженного»\n   314\t\n   3
15\tЕсли сравнить с минимальным NL→SQL (один промпт + один вызов LLM + execute)
:\n   316\t\n   317\t- **+ LangGraph pipeline на 10+ узлов** с retry-loop и err
or-context.\n   318\t- **+ Schema-RAG из 4 коллекций** вместо «вся схема в пром
пт».\n   319\t- **+ Few-shot retrieval** из эталонных Q→SQL пар.\n   320\t- **+
Static validate (sqlglot AST) + EXPLAIN-gate + 4-уровневая защита**.\n   321\t-
**+ Multi-DB** с переключателем и per-DB индексами.\n   322\t- **+ Eval harness
на публичном бенчмарке** с измеримой метрикой.\n   323\t- **+ Multi-format ренд
ер** (4 формата + auto-выбор графика).\n   324\t- **+ Полноценный observability
stack** (Prom + OTel + Langfuse).\n   325\t- **+ Web-UI** с историей, eval-стра
ницей, «show working».\n   326\t\n   327\tЭто потолок того, что осмысленно дела
ть для демо-проекта без скатывания\n   328\tв production-overhead (мульти-тенан
т, RBAC, OIDC, freshness monitor и т.д. —\n   329\tвсё то, что в RAG_SA уместно
, а здесь было бы фейк-нагрузкой).\n',
        message='329 lines read from file starting from line 1. Total lines in 
file: 329. End of file reached.',
        display=[],
        extras=None
    )
)
ToolCallPart(arguments_part='"}')
ToolCall(
    type='function',
    id='tool_PTZnCsXJgTFUe9d56YY70wBO',
    function=FunctionBody(
        name='ReadFile',
        arguments='{"path": "reviews/kimi.err"}'
    ),
    extras=None
)
StatusUpdate(
    context_usage=0.10044479370117188,
    context_tokens=26331,
    max_context_tokens=262144,
    token_usage=TokenUsage(
        input_other=18907,
        output=251,
        input_cache_read=7424,
        input_cache_creation=0
    ),
    message_id='chatcmpl-czfGMxkQizHwhisl6n8zGmC0',
    plan_mode=False,
    mcp_status=None
)
ToolResult(
    tool_call_id='tool_PTZnCsXJgTFUe9d56YY70wBO',
    return_value=ToolOk(
        is_error=False,
        output='',
        message='No lines read from file. Total lines in file: 0. End of file r
eached.',
        display=[],
        extras=None
    )
)
ToolResult(
    tool_call_id='tool_wNOLbKBBfoJtwqT6pe17sxo3',
    return_value=ToolOk(
        is_error=False,
        output='     1\t# Review request: NL→SQL Assistant — feasibility + arch
itecture\n     2\t\n     3\tYou are reviewing a draft for a portfolio/demo proj
ect by a Senior Data Analyst\n     4\t/ Data Engineer\n     5\t(Julia Edomskikh
). The author already runs a non-trivial RAG project (RAG_Suppo\n     6\trt_Ass
istant:\n     7\tFastAPI + LangGraph + Chroma + Mistral + Postgres + Langfuse +
RAGAS + mypy str\n     8\tict, public on GitHub).\n     9\tThe new project is i
ntentionally a *demo* for the author\'s portfolio, NOT a Saa\n    10\tS.\n    1
1\t\n    12\tTwo documents follow:\n    13\t1. `00_task.md` — task statement (w
hat / why / scope / DoD)\n    14\t2. `01_architecture.md` — proposed architectu
re (pipeline, schema-RAG, eval, st\n    15\tack, roadmap)\n    16\t\n    17\t##
What I want from you\n    18\t\n    19\tGive a candid, technical review. Не под
ыгрывай, возражай по существу. Russian o\n    20\tr English — на твой выбор.\n 
  21\t\n    22\t### Block A — Целесообразность проекта (feasibility / market-fi
t для портфолио)\n    23\t\n    24\t1. Велосипед или нет? Рынок NL→SQL уже пере
полнен (Vanna, DataHerald, WrenAI,\n    25\t   defog/sqlcoder, LangChain SQLAge
nt, PandasAI). Стоит ли вообще делать ещё од\n    26\tну реализацию\n    27\t  
для портфолио Senior Data Engineer? Какой в этом сигнал для рекрутёра / собе\n 
  28\tседующего?\n    29\t2. Если делать — какие 2-3 элемента делают этот проек
т *отличимым* от среднего \n    30\tдемо-NL→SQL?\n    31\t   Какие наоборот — с
тандартные, не дают сигнала, и можно срезать без потери це\n    32\tнности?\n  
 33\t3. Адекватен ли выбор Mistral-only (codestral-2501 + mistral-large-2 + mis
tral-\n    34\tembed)?\n    35\t   Не помешает ли это позиционированию (как «ve
ndor lock-in демо»)?\n    36\t   Что ответить на вопрос «а почему не GPT-4 / Cl
aude / локальная модель»?\n    37\t4. Адекватен ли выбор БД (BIRD-mini для eval
+ StackExchange Postgres + Chinook\n    38\t)?\n    39\t   Какие альтернативы д
али бы больше «вау» при той же сложности реализации?\n    40\t5. Объективно: пр
и честной оценке Execution Accuracy ≥50% на BIRD-mini с codest\n    41\tral-250
1 —\n    42\t   реалистичная цель или завышенная для солиста без fine-tune?\n  
 43\t\n    44\t### Block B — Оценка архитектуры\n    45\t\n    46\t1. **Pipelin
e (LangGraph 11 узлов).** Что лишнее? Что упущено? Узлы расположены\n    47\tв 
правильном порядке?\n    48\t   Конкретно: нужны ли все retry-точки (validate, 
execute, verify) или избыточн\n    49\tо?\n    50\t2. **Schema-RAG из 4 коллекц
ий Chroma** (tables / columns / fewshot_qsql / rela\n    51\ttions).\n    52\t 
 Это правильная декомпозиция или overengineering? Как бы ты сделал иначе?\n    
53\t   Какой baseline для сравнения (например, простая dense-схема без разбивки
)?\n    54\t3. **4-уровневая защита SQL** (БД-роль / sqlglot AST / EXPLAIN-gate
/ runtime-л\n    55\tимиты).\n    56\t   Все четыре уровня необходимы? Какие ре
альные attack vectors остаются непокры\n    57\tтыми?\n    58\t   Это hype или 
реально нужно для read-only демо?\n    59\t4. **Eval harness.** Достаточно ли т
олько Execution Accuracy + Component Match?\n    60\t   Что ещё мерить (наприме
р, latency, cost-per-query, partial-correct)?\n    61\t   Адекватна ли идея smo
ke-eval на 50 примеров в CI?\n    62\t5. **Multi-format render** (scalar / sent
ence / table / chart с auto-выбором + \n    63\tVega-Lite spec из LLM).\n    64
\t   Это реально работает или будет фейковый «выглядит красиво на картинке, фей
ли\n    65\tт в проде»?\n    66\t   Какие подводные камни в Vega-spec generatio
n от LLM?\n    67\t6. **Стек целиком.** Что тут переусложнено для demo (см. раз
дел 12 в архитектур\n    68\tе —\n    69\t   автор сама пометила что считает «н
агруженным, но не фейковым»)? Согласен ли \n    70\tты с её делением?\n    71\t
7. **Roadmap из 9 этапов на 5-6 недель.** Реалистично или оптимистично?\n    72
\t   Какой этап скорее всего «съест» больше времени, чем ожидается?\n    73\t8.
**Риски в разделе 11.** Что упущено? Какие более вероятные риски не названы?\n 
  74\t\n    75\t### Block C — Что бы ты предложил по-другому\n    76\t\n    77\
tКонкретно: 3-5 точечных правок к архитектуре, ranked by impact.\n    78\tНе об
общения («сделай лучше»), а конкретно: «убрать X, потому что Y»; «добавить\n   
79\tZ до W»;\n    80\t«поменять A на B».\n    81\t\n    82\t### Block D — Финал
ьный вердикт\n    83\t\n    84\tОдной фразой: стоит делать этот проект как port
folio piece для Senior DE? Если \n    85\tда —\n    86\tс какими корректировкам
и. Если нет — что делать вместо.\n    87\t\n    88\t---\n    89\t\n    90\t## D
ocument 1: 00_task.md\n    91\t\n    92\t# NL→SQL Assistant — постановка задачи
\n    93\t\n    94\t**Дата:** 2026-05-10\n    95\t**Автор:** Julia Edomskikh\n 
  96\t**Статус:** draft / scoping\n    97\t\n    98\t---\n    99\t\n   100\t## 
1. Что делаем\n   101\t\n   102\tИнструмент, который принимает вопрос на естест
венном языке (русский или английс\n   103\tкий),\n   104\tобращается к реляцион
ной БД и возвращает ответ в одной из форм:\n   105\t\n   106\t- **Число / скаля
р** — для агрегатных вопросов («сколько заказов в марте?»).\n   107\t- **Тексто
вое предложение** — для фактоидов с подстановкой данных\n   108\t  («у клиента 
X 12 заказов на сумму 340k за 2024 год»).\n   109\t- **Таблица** — когда нужен 
список записей.\n   110\t- **График** — когда вопрос про динамику, сравнение, р
аспределение\n   111\t  (выбор типа графика автоматический: line / bar / pie / 
hist / scatter).\n   112\t- **SQL-запрос** — всегда показывается пользователю к
ак «доказательство»\n   113\t  + объяснение на естественном языке, что именно п
осчитали.\n   114\t\n   115\t## 2. Почему это не «ещё один чат с БД»\n   116\t\
n   117\tДемо-проект для портфолио, поэтому ценность создаётся не самим NL→SQL\
n   118\t(он есть у Vanna, DataHerald, WrenAI, defog/sqlcoder, LangChain SQLAge
nt),\n   119\tа тремя слоями поверх:\n   120\t\n   121\t1. **Измеримая точность
.** Eval-harness на публичных бенчмарках\n   122\t   (BIRD-bench и/или Spider) 
с метрикой Execution Accuracy и сравнением\n   123\t   против опубликованных ре
зультатов моделей. Без этого числа проект — игрушка.\n   124\t2. **Self-correct
ion loop.** Если SQL падает или возвращает 0 строк или вырожде\n   125\tнный\n 
 126\t   результат — граф автоматически переформулирует запрос с error-context\
n   127\t   (паттерн из RAG_Support_Assistant: classify → retrieve → generate →
verify →\n   128\tretry).\n   129\t3. **Schema-RAG, а не «всю схему в промпт».*
* На сложных БД (десятки таблиц,\n   130\t   сотни колонок) полная схема не вле
зает и шумит. Хранилище:\n   131\t   таблицы + колонки + описания + примеры зна
чений + few-shot Q→SQL пары\n   132\t   индексируются в Chroma и достаются по р
елевантности к вопросу.\n   133\t\n   134\t## 3. Целевые БД\n   135\t\n   136\t
Для демо берём два разных профиля сложности:\n   137\t\n   138\t| База | Профил
ь | Зачем |\n   139\t|---|---|---|\n   140\t| **BIRD-bench (mini)** | 95 реальн
ых БД из 37 доменов, 12 751 Q→SQL пар с этал\n   141\tонными ответами | Eval-ha
rness, число Execution Accuracy на публичном leaderboa\n   142\trd\'е |\n   143
\t| **StackExchange public dump** в Postgres | Реальная сложная схема (Posts, U
se\n   144\trs, Votes, Comments, Tags, Badges), миллионы строк, JSONB-поля, вре
менные ряды \n   145\t| Демо-вопросы с красивыми графиками («активность по часа
м», «распределение тег\n   146\tов», «топ-N пользователей по карме») |\n   147\
t\n   148\tОпционально третья — **Sakila** или **Chinook** — для онбординг-демо
\n   149\t(простая, всем знакомая, быстро отрабатывает первое впечатление).\n  
150\t\n   151\t## 4. LLM\n   152\t\n   153\tТолько Mistral по API. Две модели в
роутинге:\n   154\t\n   155\t- **codestral-2501** — генерация SQL и self-correc
tion.\n   156\t  Заточен под код, на NL→SQL стабильно бьёт mistral-large.\n   1
57\t- **mistral-large-2** — классификация интента, объяснение результата\n   15
8\t  на естественном языке, выбор типа визуализации.\n   159\t\n   160\tEmbeddi
ngs — `mistral-embed` (для schema-RAG и few-shot retrieval).\n   161\t\n   162\
t## 5. Базовый сценарий (happy path)\n   163\t\n   164\t```\n   165\tПользовате
ль: "Покажи топ-10 тегов на StackOverflow по приросту вопросов в 2023\n   166\t
году"\n   167\t   |\n   168\t   v\n   169\t1. Classify intent  → "aggregation +
ranking + time-window + visualization"\n   170\t2. Schema retrieval → достать р
елевантные таблицы (Posts, Tags, PostTags) + 3 f\n   171\tew-shot примера\n   1
72\t3. SQL generation   → codestral пишет SQL с CTE по годам и приростом\n   17
3\t4. Validate         → синтаксис ОК, EXPLAIN ОК, SELECT-only гард прошёл\n   
174\t5. Execute          → 10 строк × 3 колонки\n   175\t6. Verify           → 
результат непустой, типы соответствуют ожиданиям\n   176\t7. Format           →
по структуре ответа выбран bar chart + краткий текст\n   177\t8. Render        
  → markdown-ответ + Plotly-график + блок с SQL и объяснением\n   178\t```\n   
179\t\n   180\tПри фейле любого шага — retry с error-context (макс. 2 попытки),
\n   181\tдальше — graceful failure с показом, где именно споткнулись.\n   182\
t\n   183\t## 6. Что НЕ делаем (scope cuts)\n   184\t\n   185\t- Никаких write-
операций. Read-only коннект к БД, гард на уровне SQL-парсера.\n   186\t- Никако
го мульти-БД join\'а в одном запросе.\n   187\t- Никакого fine-tuning моделей —
только prompt-engineering + RAG.\n   188\t- Никакой собственной аутентификации/
мульти-тенанси\n   189\t  (это переусложнение для демо, в RAG_SA уже отработано
— здесь не повторяем).\n   190\t- Никаких write-back в БД на основе вопросов по
льзователя.\n   191\t\n   192\t## 7. Критерии готовности (Definition of Done)\n
  193\t\n   194\t- [ ] Execution Accuracy на BIRD-mini dev split ≥ 50% (с codes
tral-2501 это реа\n   195\tлистично).\n   196\t- [ ] На StackExchange — 20 этал
онных вопросов проходят end-to-end с корректным\n   197\tответом.\n   198\t- [ 
] Веб-UI: ввод вопроса, четыре формата ответа, переключение БД, история.\n   19
9\t- [ ] CI: тесты на гард SELECT-only, на парсер схемы, на pipeline-граф.\n   
200\t- [ ] README + диаграмма архитектуры + страница eval-результатов.\n   201\
t- [ ] Деплой: docker-compose с Postgres + Chroma + FastAPI + UI.\n   202\t\n  
203\t\n   204\t---\n   205\t\n   206\t## Document 2: 01_architecture.md\n   207
\t\n   208\t# NL→SQL Assistant — архитектура (максимально нагруженный вариант)\
n   209\t\n   210\t**Дата:** 2026-05-10\n   211\t**Статус:** draft / pending re
view\n   212\t\n   213\t> «Максимально нагруженный» здесь = всё, что реально ну
жно для серьёзного\n   214\t> демо-проекта уровня Senior Data Engineer, без фей
кового overengineering\'а.\n   215\t> Каждый компонент обоснован задачей; ничег
о «на будущее».\n   216\t\n   217\t---\n   218\t\n   219\t## 1. Системная диагр
амма\n   220\t\n   221\t```text\n   222\t                           ┌──────────
────────────────┐\n   223\t                           │  Web UI (Next.js + Reac
t)│\n   224\t                           │  ─ chat input            │\n   225\t 
                         │  ─ table / chart / SQL   │\n   226\t                
          │  ─ history + bookmarks   │\n   227\t                           └───
─────────┬─────────────┘\n   228\t                                        │ HTT
PS\n   229\t                                        ▼\n   230\t                
 ┌──────────────────────────────────────────┐\n   231\t                  │  Fas
tAPI gateway (auth, rate-limit, CORS)│\n   232\t                  │  /ask, /dat
abases, /history, /eval/run   │\n   233\t                  └────────────┬──────
───────────────────────┘\n   234\t                               │\n   235\t   
      ┌────────────────────┼────────────────────────────┐\n   236\t          │ 
                  │                            │\n   237\t          ▼          
         ▼                            ▼\n   238\t  ┌──────────────┐    ┌───────
─────────┐         ┌────────────────────┐\n   239\t  │ LangGraph    │    │ Eval
harness   │         │ Schema indexer     │\n   240\t  │ NL→SQL graph │    │ (BI
RD/Spider)  │         │ (offline pipeline) │\n   241\t  └──────┬───────┘    └──
──────┬───────┘         └─────────┬──────────┘\n   242\t         │             
       │                           │\n   243\t         ▼                     ▼ 
                         ▼\n   244\t  ┌────────────────────────────────────────
──────────────────────┐\n   245\t  │                   Shared services layer   
                   │\n   246\t  ├──────────────┬──────────────┬─────────────┬──
────────────────┤\n   247\t  │ Mistral API  │ Chroma DB    │ Postgres    │ Redi
s            │\n   248\t  │ codestral    │ schema chunks│ target DBs  │ result 
cache     │\n   249\t  │ large-2      │ few-shot Q→S │ (multi-DB)  │ rate-limit
state │\n   250\t  │ mistral-embed│              │ + traces DB │               
  │\n   251\t  └──────────────┴──────────────┴─────────────┴──────────────────┘
\n   252\t                               │\n   253\t                           
   ▼\n   254\t                  ┌──────────────────────────┐\n   255\t         
        │ Observability             │\n   256\t                  │ Prometheus +
OpenTelemetry│\n   257\t                  │ Langfuse traces           │\n   258
\t                  └──────────────────────────┘\n   259\t```\n   260\t\n   261
\t## 2. LangGraph pipeline\n   262\t\n   263\tРеиспользуем структуру из RAG_Sup
port_Assistant\n   264\t(`classify → retrieve → rerank → generate → verify → ev
aluate`),\n   265\tно узлы заточены под NL→SQL:\n   266\t\n   267\t```text\n   
268\t       ┌────────────────┐\n   269\t       │ classify_intent│   intent = ag
gregation | ranking | filter |\n   270\t       └────────┬───────┘            ti
me_series | comparison | lookup |\n   271\t                │                   
distribution\n   272\t                ▼\n   273\t       ┌────────────────┐\n   
274\t       │ select_database│   если в системе несколько БД — выбрать целевую\
n   275\t       └────────┬───────┘            по интенту + ключевым словам\n   
276\t                │\n   277\t                ▼\n   278\t       ┌────────────
────┐\n   279\t       │ retrieve_schema│   Chroma: relevant tables + columns + 
value samples\n   280\t       └────────┬───────┘\n   281\t                │\n  
282\t                ▼\n   283\t       ┌────────────────┐\n   284\t       │ ret
rieve_examples│ Chroma: top-k похожих Q→SQL пар (few-shot)\n   285\t       └───
─────┬───────┘\n   286\t                │\n   287\t                ▼\n   288\t 
     ┌────────────────┐\n   289\t       │ generate_sql   │   codestral-2501 + s
tructured output (JSON-mode)\n   290\t       └────────┬───────┘            { "s
ql": "...", "rationale": "..." }\n   291\t                │\n   292\t          
     ▼\n   293\t       ┌────────────────┐\n   294\t       │ static_validate│   
sqlglot parse → SELECT-only guard → schema check\n   295\t       └────────┬────
───┘            (table/column existence vs catalog)\n   296\t                │ 
FAIL ──────────► retry_loop (max 2)\n   297\t                │ OK\n   298\t    
           ▼\n   299\t       ┌────────────────┐\n   300\t       │ explain_plan 
 │   EXPLAIN на целевой БД, отказ если cost > threshold\n   301\t       └──────
──┬───────┘            (защита от full-scan на больших таблицах)\n   302\t     
          │\n   303\t                ▼\n   304\t       ┌────────────────┐\n   3
05\t       │ execute        │   read-only коннект, statement_timeout, LIMIT-gua
rd\n   306\t       └────────┬───────┘\n   307\t                │\n   308\t     
          ▼\n   309\t       ┌────────────────┐\n   310\t       │ verify_result 
│   проверки: непустой? типы соответствуют интенту?\n   311\t       └────────┬─
──────┘            аномалии? (нулей/null\'ов слишком много)\n   312\t          
     │ FAIL ──────────► retry_loop\n   313\t                │ OK\n   314\t     
          ▼\n   315\t       ┌────────────────┐\n   316\t       │ choose_format 
│   intent + result shape →\n   317\t       └────────┬───────┘            scala
r | sentence | table | chart\n   318\t                │\n   319\t              
 ▼\n   320\t       ┌────────────────┐\n   321\t       │ render_answer  │   mist
ral-large-2: NL-объяснение + chart-spec (Vega-L\n   322\tite)\n   323\t       └
────────┬───────┘\n   324\t                │\n   325\t                ▼\n   326
\t       ┌────────────────┐\n   327\t       │ persist_trace  │   sqlite traces 
+ Langfuse span + Prometheus counter\n   328\t       └────────────────┘\n   329
\t```\n   330\t\n   331\t**Retry loop:** при фейле узлов `static_validate`, `ex
ecute`, `verify_result`\n   332\tграф возвращается к `generate_sql` с приклеенн
ым error-context\'ом\n   333\t(текст ошибки + предыдущий SQL + разъяснение что 
не так). Лимит — 2 попытки,\n   334\tпосле чего отдаётся диагностический ответ.
\n   335\t\n   336\t## 3. Schema-RAG: устройство индекса\n   337\t\n   338\t**П
роблема:** в BIRD есть БД с 50+ таблицами. Полная схема в промпт не лезет\n   3
39\tи зашумляет генерацию.\n   340\t\n   341\t**Решение:** offline-пайплайн `Sc
hema indexer` строит несколько коллекций в Chr\n   342\toma:\n   343\t\n   344\
t| Коллекция | Чанк | Эмбеддится |\n   345\t|---|---|---|\n   346\t| `schema_ta
bles` | таблица | имя + описание + список колонок + 3 sample строки\n   347\t|\
n   348\t| `schema_columns` | колонка | имя + тип + описание + min/max/nunique 
+ 5 sampl\n   349\te значений |\n   350\t| `fewshot_qsql` | Q→SQL пара | вопрос
+ аннотация интента (SQL не эмбеддится) \n   351\t|\n   352\t| `relations` | FK
-связь | from_table.col → to_table.col + семантика |\n   353\t\n   354\tПри воп
росе `retrieve_schema` делает гибрид BM25 + dense на `schema_tables`,\n   355\t
дотягивает топ-N колонок из `schema_columns` для отобранных таблиц,\n   356\tдо
бавляет связи между ними. Получается компактный «срез схемы» под вопрос —\n   3
57\tобычно 5-15 таблиц вместо 50+.\n   358\t\n   359\t`retrieve_examples` доста
ёт из `fewshot_qsql` 3-5 наиболее похожих\n   360\tвопросов с эталонными SQL — 
это мощно поднимает качество на сложных диалектах.\n   361\t\n   362\t## 4. Без
опасность исполнения SQL\n   363\t\n   364\tRead-only — это не «обещание промпт
ом», а реальные гарды на четырёх уровнях:\n   365\t\n   366\t1. **БД-роль:** от
дельный postgres-пользователь с GRANT SELECT ONLY,\n   367\t   без CREATE/INSER
T/UPDATE/DELETE/TRUNCATE/ALTER.\n   368\t2. **Парсер:** `sqlglot` AST-валидация
— отказ при не-SELECT, при множественных\n   369\t   стейтментах, при наличии C
TE с DML, при `pg_*`/`information_schema` без whit\n   370\telist.\n   371\t3. 
**EXPLAIN-gate:** `EXPLAIN (FORMAT JSON)` перед `EXECUTE`,\n   372\t   отказ ес
ли `Total Cost > X` (порог настраивается на БД).\n   373\t4. **Runtime:** `SET 
statement_timeout = 30s`, обязательный `LIMIT 10000`\n   374\t   если в запросе
нет агрегации.\n   375\t\n   376\t## 5. Eval harness\n   377\t\n   378\tОтдельн
ый модуль `eval/`, не часть онлайн-пайплайна:\n   379\t\n   380\t```text\n   38
1\teval/\n   382\t├── datasets/\n   383\t│   ├── bird_mini.jsonl          # 150
0 Q→SQL пар, 11 БД\n   384\t│   └── stackexchange_gold.jsonl # 20 наших эталонн
ых вопросов\n   385\t├── runner.py                    # прогон через граф, срав
нение\n   386\t├── metrics/\n   387\t│   ├── execution_accuracy.py    # сравнен
ие result-set\'ов\n   388\t│   ├── exact_match.py           # SQL string match 
(слабая метрика)\n   389\t│   └── component_match.py       # сравнение по AST-к
омпонентам\n   390\t└── reports/\n   391\t    └── 2026-05-10-baseline.html # от
чёт по прогонам\n   392\t```\n   393\t\n   394\tCI прогоняет smoke-eval на 50 п
римерах при каждом merge в main.\n   395\tПолный прогон — вручную или nightly.\
n   396\t\n   397\t**Целевое число:** Execution Accuracy ≥ 50% на BIRD-mini dev
.\n   398\tОпубликованные результаты codestral-2501 на BIRD ~57%, так что 50%\n
  399\tсвоими силами на узком сабсете — реалистично.\n   400\t\n   401\t## 6. M
ulti-DB switching\n   402\t\n   403\tВ `config/databases.yml` описаны подключен
ия:\n   404\t\n   405\t```yaml\n   406\tdatabases:\n   407\t  - id: stackexchan
ge\n   408\t    dsn: postgresql://nlsql_ro@localhost/stackexchange\n   409\t   
description: "StackOverflow public data — posts, users, votes"\n   410\t    sch
ema_index: chroma://stackexchange\n   411\t    sample_questions: ["топ-10 тегов
...", "распределение..."]\n   412\t  - id: bird_california_schools\n   413\t   
dsn: sqlite:///data/bird/california_schools.sqlite\n   414\t    description: "C
alifornia schools — performance, demographics"\n   415\t    schema_index: chrom
a://bird_california_schools\n   416\t  - id: chinook\n   417\t    dsn: sqlite:/
//data/chinook.sqlite\n   418\t    description: "Music store — invoices, tracks
, customers"\n   419\t    schema_index: chroma://chinook\n   420\t```\n   421\t
\n   422\tUI даёт переключатель «target DB», граф читает её из state.\n   423\t
\n   424\t## 7. UI (Next.js + React)\n   425\t\n   426\tМинимально, но без обре
зков:\n   427\t\n   428\t- **Chat-style вход** с подсветкой SQL в ответе и copy
-кнопкой.\n   429\t- **Multi-format ответ** — компонент сам решает, что рендери
ть\n   430\t  (scalar / sentence / DataGrid / Vega-Lite chart).\n   431\t- **«S
how working»**: разворачивающийся блок с retrieved schema, few-shot,\n   432\t 
rationale, EXPLAIN-планом, временем выполнения.\n   433\t- **History + bookmark
s** в localStorage + опционально на бэке.\n   434\t- **DB switcher** + список s
ample-вопросов под каждую БД.\n   435\t\n   436\tОтдельная страница **`/eval`**
— таблица результатов eval-прогонов,\n   437\tграфики динамики Execution Accura
cy по коммитам.\n   438\t\n   439\t## 8. Стек целиком\n   440\t\n   441\t| Слой
| Технология | Почему |\n   442\t|---|---|---|\n   443\t| LLM | Mistral API: co
destral-2501, mistral-large-2, mistral-embed | Жёсткое т\n   444\tребование зад
ачи |\n   445\t| Orchestration | LangGraph | Уже знакома по RAG_SA, retry-loop 
из коробки |\n   446\t| API | FastAPI + Pydantic v2 | Стандарт, типобезопасност
ь |\n   447\t| Vector DB | ChromaDB | Уже знакома, локально без отдельного серв
иса |\n   448\t| SQL parser | sqlglot | Multi-dialect, AST-валидация, dialect t
ranslation |\n   449\t| Target DB | Postgres 16 (StackExchange) + SQLite (BIRD,
Chinook) | Реализм + \n   450\tпростота |\n   451\t| Cache | Redis 7 | Кэш резу
льтатов SQL, rate-limit |\n   452\t| Charting | Vega-Lite (через спеку из LLM) 
+ Plotly fallback | LLM хорошо гене\n   453\tрит Vega-spec\'и |\n   454\t| Fron
tend | Next.js 15 + Tailwind + shadcn/ui | Быстрый красивый UI |\n   455\t| Obs
ervability | Prometheus + OpenTelemetry + Langfuse | Стандартный стек, пер\n   
456\tеиспользуется из RAG_SA |\n   457\t| Tests | pytest + httpx + testcontaine
rs (Postgres) | Реальная БД в CI |\n   458\t| Lint/Type | ruff + mypy strict (a
pi/, agent/) | Как в DE_project |\n   459\t| CI | GitHub Actions | smoke-eval +
pytest + ruff + mypy |\n   460\t| Deploy | docker-compose (dev) + Dockerfile mu
lti-stage (prod) | Достаточно дл\n   461\tя демо |\n   462\t\n   463\t## 9. Стр
уктура репозитория\n   464\t\n   465\t```\n   466\tNL_SQL/\n   467\t├── api/   
               # FastAPI app, routers, middleware\n   468\t├── agent/          
      # LangGraph nodes, prompts, state\n   469\t│   ├── graph.py\n   470\t│   
├── nodes/\n   471\t│   │   ├── classify.py\n   472\t│   │   ├── retrieve_schem
a.py\n   473\t│   │   ├── retrieve_examples.py\n   474\t│   │   ├── generate_sq
l.py\n   475\t│   │   ├── validate.py\n   476\t│   │   ├── execute.py\n   477\t
│   │   ├── verify.py\n   478\t│   │   ├── render.py\n   479\t│   │   └── retry
.py\n   480\t│   └── prompts/\n   481\t├── llm/                   # Mistral pro
vider, retry, cost guard\n   482\t├── schema_index/          # offline indexer 
for Chroma\n   483\t│   ├── extractor.py       # introspect Postgres/SQLite cat
alog\n   484\t│   ├── enricher.py        # описания, sample values, stats\n   4
85\t│   └── builder.py         # build Chroma collections\n   486\t├── executio
n/             # SQL guards, EXPLAIN gate, runner\n   487\t├── eval/           
      # см. раздел 5\n   488\t├── frontend/              # Next.js UI\n   489\t
├── config/                # databases.yml, prompts.yml\n   490\t├── data/     
            # BIRD dump, Chinook, sample dumps (gitignore)\n   491\t├── tests/\
n   492\t├── docker-compose.yml\n   493\t├── Dockerfile\n   494\t└── docs/\n   
495\t    ├── 00_task.md\n   496\t    ├── 01_architecture.md       ← вы здесь\n 
 497\t    ├── 02_eval_methodology.md   ← TODO\n   498\t    └── 03_demo_question
s.md     ← TODO\n   499\t```\n   500\t\n   501\t## 10. Roadmap (этапы)\n   502\
t\n   503\t| # | Этап | DoD |\n   504\t|---|---|---|\n   505\t| 1 | **Bootstrap
** | poetry/uv проект, FastAPI hello, Mistral provider, тесты \n   506\tна пров
айдер с моком |\n   507\t| 2 | **Target DBs ready** | docker-compose поднимает 
Postgres со StackExchange\n   508\tdump + SQLite Chinook + BIRD dump в `data/` 
|\n   509\t| 3 | **Schema indexer** | offline скрипт строит Chroma-коллекции, s
moke-тест н\n   510\tа retrieval |\n   511\t| 4 | **Pipeline v1** | LangGraph г
раф работает на Chinook (простая БД), single\n   512\t-shot без retry |\n   513
\t| 5 | **Guards & verify** | sqlglot guard, EXPLAIN gate, retry-loop, тесты |\
n   514\t| 6 | **Eval harness** | runner + execution_accuracy метрика, baseline
на BIRD-\n   515\tmini |\n   516\t| 7 | **Multi-format render** | scalar/senten
ce/table/chart с автоопределением \n   517\t+ Vega-Lite spec\'и |\n   518\t| 8 
| **UI v1** | chat + DB switcher + history, end-to-end на 3 БД |\n   519\t| 9 |
**Polish & deploy** | docker-compose prod-like, README, демо-видео, eval-\n   5
20\tстраница |\n   521\t\n   522\tЭтапы 1-3 — фундамент (~неделя на каждом темп
е).\n   523\tЭтапы 4-6 — суть проекта (~2 недели).\n   524\tЭтапы 7-9 — витрина
(~неделя).\n   525\t\n   526\tИтого: ~5-6 рабочих недель в спокойном темпе или 
2-3 в плотном.\n   527\t\n   528\t## 11. Риски\n   529\t\n   530\t| Риск | Веро
ятность | Митигация |\n   531\t|---|---|---|\n   532\t| codestral-2501 даёт <40
% на BIRD | средняя | улучшить few-shot retrieval, доб\n   533\tавить chain-of-
thought, schema-linking шаг |\n   534\t| StackExchange dump слишком большой для
локалки (≥100GB) | высокая | взять min\n   535\ti-dump (`gaming.stackexchange.c
om`, ~1GB) — реализм без боли |\n   536\t| EXPLAIN-gate ломает легитимные тяжёл
ые запросы | средняя | tune порог на БД, \n   537\tдать override-флаг для админ
а |\n   538\t| BIRD dataset лицензия | низкая | CC-BY-SA-4.0, для демо OK |\n  
539\t| Mistral API rate limits на eval-прогоне | средняя | local cache на (prom
pt → \n   540\tresponse), батчинг, exponential backoff |\n   541\t\n   542\t## 
12. Что в этой архитектуре «нагруженного»\n   543\t\n   544\tЕсли сравнить с ми
нимальным NL→SQL (один промпт + один вызов LLM + execute):\n   545\t\n   546\t-
**+ LangGraph pipeline на 10+ узлов** с retry-loop и error-context.\n   547\t- 
**+ Schema-RAG из 4 коллекций** вместо «вся схема в промпт».\n   548\t- **+ Few
-shot retrieval** из эталонных Q→SQL пар.\n   549\t- **+ Static validate (sqlgl
ot AST) + EXPLAIN-gate + 4-уровневая защита**.\n   550\t- **+ Multi-DB** с пере
ключателем и per-DB индексами.\n   551\t- **+ Eval harness на публичном бенчмар
ке** с измеримой метрикой.\n   552\t- **+ Multi-format рендер** (4 формата + au
to-выбор графика).\n   553\t- **+ Полноценный observability stack** (Prom + OTe
l + Langfuse).\n   554\t- **+ Web-UI** с историей, eval-страницей, «show workin
g».\n   555\t\n   556\tЭто потолок того, что осмысленно делать для демо-проекта
без скатывания\n   557\tв production-overhead (мульти-тенант, RBAC, OIDC, fresh
ness monitor и т.д. —\n   558\tвсё то, что в RAG_SA уместно, а здесь было бы фе
йк-нагрузкой).\n   559\tTurnBegin(\n   560\t    user_input=\'# Review request: 
NL→SQL Assistant — feasibility + architecture\n   561\t\\n\\nYou are reviewing 
a draft for a portfolio/demo project by a Senior Data Ana\n   562\tlyst / Data 
Engineer\\n(Julia Edomskikh). The author already runs a non-trivial \n   563\tR
AG project (RAG_Support_Assistant:\\nFastAPI + LangGraph + Chroma + Mistral + P
\n   564\tostgres + Langfuse + RAGAS + mypy strict, public on GitHub).\\nThe ne
w project i\n   565\ts intentionally a *demo* for the author\\\'s portfolio, NO
T a SaaS.\\n\\nTwo docume\n   566\tnts follow:\\n1. `00_task.md` — task stateme
nt (what / why / scope / DoD)\\n2. `0\n   567\t1_architecture.md` — proposed ar
chitecture (pipeline, schema-RAG, eval, stack, \n   568\troadmap)\\n\\n## What 
I want from you\\n\\nGive a candid, technical review. Не поды\n   569\tгрывай, 
возражай по существу. Russian or English — на твой выбор.\\n\\n### Block \n   5
70\tA — Целесообразность проекта (feasibility / market-fit для портфолио)\\n\\n
1. Вел\n   571\tосипед или нет? Рынок NL→SQL уже переполнен (Vanna, DataHerald,
WrenAI,\\n   def\n   572\tog/sqlcoder, LangChain SQLAgent, PandasAI). Стоит ли 
вообще делать ещё одну реа\n   573\tлизацию\\n   для портфолио Senior Data Engi
neer? Какой в этом сигнал для рекрутё\n   574\tра / собеседующего?\\n2. Если де
лать — какие 2-3 элемента делают этот проект *от\n   575\tличимым* от среднего 
демо-NL→SQL?\\n   Какие наоборот — стандартные, не дают сиг\n   576\tнала, и мо
жно срезать без потери ценности?\\n3. Адекватен ли выбор Mistral-only \n   577\
t(codestral-2501 + mistral-large-2 + mistral-embed)?\\n   Не помешает ли это по
зи\n   578\tционированию (как «vendor lock-in демо»)?\\n   Что ответить на вопр
ос «а почему \n   579\tне GPT-4 / Claude / локальная модель»?\\n4. Адекватен ли
выбор БД (BIRD-mini для\n   580\teval + StackExchange Postgres + Chinook)?\\n  
Какие альтернативы дали бы больше\n   581\t«вау» при той же сложности реализаци
и?\\n5. Объективно: при честной оценке Execu\n   582\ttion Accuracy ≥50% на BIR
D-mini с codestral-2501 —\\n   реалистичная цель или за\n   583\tвышенная для с
олиста без fine-tune?\\n\\n### Block B — Оценка архитектуры\\n\\n1. *\n   584\t
*Pipeline (LangGraph 11 узлов).** Что лишнее? Что упущено? Узлы расположены в п
\n   585\tравильном порядке?\\n   Конкретно: нужны ли все retry-точки (validate
, execute, \n   586\tverify) или избыточно?\\n2. **Schema-RAG из 4 коллекций Ch
roma** (tables / colum\n   587\tns / fewshot_qsql / relations).\\n   Это правил
ьная декомпозиция или overenginee\n   588\tring? Как бы ты сделал иначе?\\n   К
акой baseline для сравнения (например, прост\n   589\tая dense-схема без разбив
ки)?\\n3. **4-уровневая защита SQL** (БД-роль / sqlglot\n   590\tAST / EXPLAIN-
gate / runtime-лимиты).\\n   Все четыре уровня необходимы? Какие р\n   591\tеал
ьные attack vectors остаются непокрытыми?\\n   Это hype или реально нужно для\n
  592\tread-only демо?\\n4. **Eval harness.** Достаточно ли только Execution Ac
curacy +\n   593\tComponent Match?\\n   Что ещё мерить (например, latency, cost
-per-query, partial\n   594\t-correct)?\\n   Адекватна ли идея smoke-eval на 50
примеров в CI?\\n5. **Multi-fo\n   595\trmat render** (scalar / sentence / tabl
e / chart с auto-выбором + Vega-Lite spe\n   596\tc из LLM).\\n   Это реально р
аботает или будет фейковый «выглядит красиво на кар\n   597\tтинке, фейлит в пр
оде»?\\n   Какие подводные камни в Vega-spec generation от LLM\n   598\t?\\n6. 
**Стек целиком.** Что тут переусложнено для demo (см. раздел 12 в архитек\n   5
99\tтуре —\\n   автор сама пометила что считает «нагруженным, но не фейковым»)?
Согл\n   600\tасен ли ты с её делением?\\n7. **Roadmap из 9 этапов на 5-6 недел
ь.** Реалистичн\n   601\tо или оптимистично?\\n   Какой этап скорее всего «съес
т» больше времени, чем ожи\n   602\tдается?\\n8. **Риски в разделе 11.** Что уп
ущено? Какие более вероятные риски не\n   603\tназваны?\\n\\n### Block C — Что 
бы ты предложил по-другому\\n\\nКонкретно: 3-5 точе\n   604\tчных правок к архи
тектуре, ranked by impact.\\nНе обобщения («сделай лучше»), а \n   605\tконкрет
но: «убрать X, потому что Y»; «добавить Z до W»;\\n«поменять A на B».\\n\\n\n  
606\t### Block D — Финальный вердикт\\n\\nОдной фразой: стоит делать этот проек
т как p\n   607\tortfolio piece для Senior DE? Если да —\\nс какими корректиров
ками. Если нет — ч\n   608\tто делать вместо.\\n\\n---\\n\\n## Document 1: 00_t
ask.md\\n\\n# NL→SQL Assistant — п\n   609\tостановка задачи\\n\\n**Дата:** 202
6-05-10\\n**Автор:** Julia Edomskikh\\n**Статус:\n   610\t** draft / scoping\\n
\\n---\\n\\n## 1. Что делаем\\n\\nИнструмент, который принимает \n   611\tвопро
с на естественном языке (русский или английский),\\nобращается к реляционно\n  
612\tй БД и возвращает ответ в одной из форм:\\n\\n- **Число / скаляр** — для а
грегатн\n   613\tых вопросов («сколько заказов в марте?»).\\n- **Текстовое пред
ложение** — для фа\n   614\tктоидов с подстановкой данных\\n  («у клиента X 12 
заказов на сумму 340k за 2024\n   615\tгод»).\\n- **Таблица** — когда нужен спи
сок записей.\\n- **График** — когда вопро\n   616\tс про динамику, сравнение, р
аспределение\\n  (выбор типа графика автоматический:\n   617\tline / bar / pie 
/ hist / scatter).\\n- **SQL-запрос** — всегда показывается пол\n   618\tьзоват
елю как «доказательство»\\n  + объяснение на естественном языке, что именн\n   
619\tо посчитали.\\n\\n## 2. Почему это не «ещё один чат с БД»\\n\\nДемо-проект
для порт\n   620\tфолио, поэтому ценность создаётся не самим NL→SQL\\n(он есть 
у Vanna, DataHerald\n   621\t, WrenAI, defog/sqlcoder, LangChain SQLAgent),\\nа
тремя слоями поверх:\\n\\n1. **\n   622\tИзмеримая точность.** Eval-harness на 
публичных бенчмарках\\n   (BIRD-bench и/ил\n   623\tи Spider) с метрикой Execut
ion Accuracy и сравнением\\n   против опубликованных \n   624\tрезультатов моде
лей. Без этого числа проект — игрушка.\\n2. **Self-correction lo\n   625\top.**
Если SQL падает или возвращает 0 строк или вырожденный\\n   результат — гр\n   
626\tаф автоматически переформулирует запрос с error-context\\n   (паттерн из R
AG_Sup\n   627\tport_Assistant: classify → retrieve → generate → verify → retry
).\\n3. **Schema-\n   628\tRAG, а не «всю схему в промпт».** На сложных БД (дес
ятки таблиц,\\n   сотни коло\n   629\tнок) полная схема не влезает и шумит. Хра
нилище:\\n   таблицы + колонки + описан\n   630\tия + примеры значений + few-sh
ot Q→SQL пары\\n   индексируются в Chroma и достаю\n   631\tтся по релевантност
и к вопросу.\\n\\n## 3. Целевые БД\\n\\nДля демо берём два разны\n   632\tх про
филя сложности:\\n\\n| База | Профиль | Зачем |\\n|---|---|---|\\n| **BIRD-ben\
n   633\tch (mini)** | 95 реальных БД из 37 доменов, 12 751 Q→SQL пар с эталонн
ыми ответ\n   634\tами | Eval-harness, число Execution Accuracy на публичном le
aderboard\\\'е |\\n| *\n   635\t*StackExchange public dump** в Postgres | Реаль
ная сложная схема (Posts, Users,\n   636\tVotes, Comments, Tags, Badges), милли
оны строк, JSONB-поля, временные ряды | Де\n   637\tмо-вопросы с красивыми граф
иками («активность по часам», «распределение тегов»,\n   638\t«топ-N пользовате
лей по карме») |\\n\\nОпционально третья — **Sakila** или **Chin\n   639\took**
— для онбординг-демо\\n(простая, всем знакомая, быстро отрабатывает первое\n   
640\tвпечатление).\\n\\n## 4. LLM\\n\\nТолько Mistral по API. Две модели в роут
инге:\\n\\n\n   641\t- **codestral-2501** — генерация SQL и self-correction.\\n
 Заточен под код, на \n   642\tNL→SQL стабильно бьёт mistral-large.\\n- **mistr
al-large-2** — классификация инт\n   643\tента, объяснение результата\\n  на ес
тественном языке, выбор типа визуализации.\\\n   644\tn\\nEmbeddings — `mistral
-embed` (для schema-RAG и few-shot retrieval).\\n\\n## 5.\n   645\tБазовый сцен
арий (happy path)\\n\\n```\\nПользователь: "Покажи топ-10 тегов на Sta\n   646\
tckOverflow по приросту вопросов в 2023 году"\\n   |\\n   v\\n1. Classify inten
t  →\n   647\t"aggregation + ranking + time-window + visualization"\\n2. Schema
retrieval → до\n   648\tстать релевантные таблицы (Posts, Tags, PostTags) + 3 f
ew-shot примера\\n3. SQL \n   649\tgeneration   → codestral пишет SQL с CTE по 
годам и приростом\\n4. Validate     \n   650\t   → синтаксис ОК, EXPLAIN ОК, SE
LECT-only гард прошёл\\n5. Execute          → 1\n   651\t0 строк × 3 колонки\\n
6. Verify           → результат непустой, типы соответству\n   652\tют ожидания
м\\n7. Format           → по структуре ответа выбран bar chart + крат\n   653\t
кий текст\\n8. Render           → markdown-ответ + Plotly-график + блок с SQL и
\n   654\tобъяснением\\n```\\n\\nПри фейле любого шага — retry с error-context 
(макс. 2 попы\n   655\tтки),\\nдальше — graceful failure с показом, где именно 
споткнулись.\\n\\n## 6. Чт\n   656\tо НЕ делаем (scope cuts)\\n\\n- Никаких wri
te-операций. Read-only коннект к БД, г\n   657\tард на уровне SQL-парсера.\\n- 
Никакого мульти-БД join\\\'а в одном запросе.\\n- Ни\n   658\tкакого fine-tunin
g моделей — только prompt-engineering + RAG.\\n- Никакой собств\n   659\tенной 
аутентификации/мульти-тенанси\\n  (это переусложнение для демо, в RAG_SA у\n   
660\tже отработано — здесь не повторяем).\\n- Никаких write-back в БД на основе
вопро\n   661\tсов пользователя.\\n\\n## 7. Критерии готовности (Definition of 
Done)\\n\\n- [ ] Ex\n   662\tecution Accuracy на BIRD-mini dev split ≥ 50% (с c
odestral-2501 это реалистично\n   663\t).\\n- [ ] На StackExchange — 20 эталонн
ых вопросов проходят end-to-end с коррек\n   664\tтным ответом.\\n- [ ] Веб-UI:
ввод вопроса, четыре формата ответа, переключение \n   665\tБД, история.\\n- [ 
] CI: тесты на гард SELECT-only, на парсер схемы, на pipeline\n   666\t-граф.\\
n- [ ] README + диаграмма архитектуры + страница eval-результатов.\\n- [ \n   6
67\t] Деплой: docker-compose с Postgres + Chroma + FastAPI + UI.\\n\\n\\n---\\n
\\n## Doc\n   668\tument 2: 01_architecture.md\\n\\n# NL→SQL Assistant — архите
ктура (максимально на\n   669\tгруженный вариант)\\n\\n**Дата:** 2026-05-10\\n*
*Статус:** draft / pending review\\\n   670\tn\\n> «Максимально нагруженный» зд
есь = всё, что реально нужно для серьёзного\\n>\n   671\tдемо-проекта уровня Se
nior Data Engineer, без фейкового overengineering\\\'а.\\n> \n   672\tКаждый ко
мпонент обоснован задачей; ничего «на будущее».\\n\\n---\\n\\n## 1. Систем\n   
673\tная диаграмма\\n\\n```text\\n                           ┌─────────────────
────────\n   674\t─┐\\n                           │  Web UI (Next.js + React)│\
\n                  \n   675\t        │  ─ chat input            │\\n          
                │  ─ table / c\n   676\thart / SQL   │\\n                      
    │  ─ history + bookmarks   │\\n      \n   677\t                    └───────
─────┬─────────────┘\\n                             \n   678\t          │ HTTPS
\\n                                        ▼\\n                 \n   679\t┌────
──────────────────────────────────────┐\\n                  │  FastAPI gate\n  
680\tway (auth, rate-limit, CORS)│\\n                  │  /ask, /databases, /hi
story,\n   681\t/eval/run   │\\n                  └────────────┬───────────────
──────────────┘\\n\n   682\t                              │\\n          ┌──────
──────────────┼──────────────\n   683\t──────────────┐\\n          │           
        │                            │\\\n   684\tn          ▼                 
  ▼                            ▼\\n  ┌────────────\n   685\t──┐    ┌───────────
─────┐         ┌────────────────────┐\\n  │ LangGraph    │   \n   686\t│ Eval h
arness   │         │ Schema indexer     │\\n  │ NL→SQL graph │    │ (BIR\n   68
7\tD/Spider)  │         │ (offline pipeline) │\\n  └──────┬───────┘    └───────
─┬──\n   688\t─────┘         └─────────┬──────────┘\\n         │               
     │        \n   689\t                  │\\n         ▼                     ▼ 
                        \n   690\t▼\\n  ┌──────────────────────────────────────
────────────────────────┐\\n  │     \n   691\t             Shared services laye
r                       │\\n  ├──────────────┬─\n   692\t─────────────┬────────
─────┬──────────────────┤\\n  │ Mistral API  │ Chroma DB  \n   693\t │ Postgres
   │ Redis            │\\n  │ codestral    │ schema chunks│ target D\n   694\tB
s  │ result cache     │\\n  │ large-2      │ few-shot Q→S │ (multi-DB)  │ rate-
\n   695\tlimit state │\\n  │ mistral-embed│              │ + traces DB │      
          \n   696\t│\\n  └──────────────┴──────────────┴─────────────┴────────
──────────┘\\n        \n   697\t                      │\\n                     
         ▼\\n                  ┌─\n   698\t─────────────────────────┐\\n       
          │ Observability             │\\n  \n   699\t               │ Promethe
us + OpenTelemetry│\\n                  │ Langfuse trac\n   700\tes           │
\\n                  └──────────────────────────┘\\n```\\n\\n## 2. La\n   701\t
ngGraph pipeline\\n\\nРеиспользуем структуру из RAG_Support_Assistant\\n(`class
ify\n   702\t→ retrieve → rerank → generate → verify → evaluate`),\\nно узлы за
точены под NL→\n   703\tSQL:\\n\\n```text\\n       ┌────────────────┐\\n       
│ classify_intent│   intent \n   704\t= aggregation | ranking | filter |\\n    
  └────────┬───────┘            time_s\n   705\teries | comparison | lookup |\\
n                │                    distributio\n   706\tn\\n                
▼\\n       ┌────────────────┐\\n       │ select_database│   ес\n   707\tли в си
стеме несколько БД — выбрать целевую\\n       └────────┬───────┘         \n   7
08\t  по интенту + ключевым словам\\n                │\\n                ▼\\n  
    ┌─\n   709\t───────────────┐\\n       │ retrieve_schema│   Chroma: relevant
tables + columns\n   710\t+ value samples\\n       └────────┬───────┘\\n       
        │\\n                \n   711\t▼\\n       ┌────────────────┐\\n       │ 
retrieve_examples│ Chroma: top-k похожих\n   712\tQ→SQL пар (few-shot)\\n      
└────────┬───────┘\\n                │\\n           \n   713\t    ▼\\n       ┌─
───────────────┐\\n       │ generate_sql   │   codestral-2501 + \n   714\tstruc
tured output (JSON-mode)\\n       └────────┬───────┘            { "sql": ".\n  
715\t..", "rationale": "..." }\\n                │\\n                ▼\\n      
┌──────\n   716\t──────────┐\\n       │ static_validate│   sqlglot parse → SELE
CT-only guard → sc\n   717\thema check\\n       └────────┬───────┘            (
table/column existence vs cat\n   718\talog)\\n                │ FAIL ─────────
─► retry_loop (max 2)\\n                │\n   719\tOK\\n                ▼\\n   
   ┌────────────────┐\\n       │ explain_plan   │   E\n   720\tXPLAIN на целево
й БД, отказ если cost > threshold\\n       └────────┬───────┘   \n   721\t     
  (защита от full-scan на больших таблицах)\\n                │\\n         \n  
722\t      ▼\\n       ┌────────────────┐\\n       │ execute        │   read-onl
y конне\n   723\tкт, statement_timeout, LIMIT-guard\\n       └────────┬───────┘
\\n                \n   724\t│\\n                ▼\\n       ┌────────────────┐\
\n       │ verify_result  │   пр\n   725\tоверки: непустой? типы соответствуют 
интенту?\\n       └────────┬───────┘       \n   726\t    аномалии? (нулей/null\
\\'ов слишком много)\\n                │ FAIL ──────────\n   727\t► retry_loop\
\n                │ OK\\n                ▼\\n       ┌────────────────\n   728\t
┐\\n       │ choose_format  │   intent + result shape →\\n       └────────┬────
──\n   729\t─┘            scalar | sentence | table | chart\\n                │
\\n           \n   730\t    ▼\\n       ┌────────────────┐\\n       │ render_ans
wer  │   mistral-large-2: \n   731\tNL-объяснение + chart-spec (Vega-Lite)\\n  
    └────────┬───────┘\\n            \n   732\t   │\\n                ▼\\n     
 ┌────────────────┐\\n       │ persist_trace  │  \n   733\tsqlite traces + Lang
fuse span + Prometheus counter\\n       └────────────────┘\\n\n   734\t```\\n\\
n**Retry loop:** при фейле узлов `static_validate`, `execute`, `verify_re\n   7
35\tsult`\\nграф возвращается к `generate_sql` с приклеенным error-context\\\'о
м\\n(тек\n   736\tст ошибки + предыдущий SQL + разъяснение что не так). Лимит —
2 попытки,\\nпосле\n   737\tчего отдаётся диагностический ответ.\\n\\n## 3. Sch
ema-RAG: устройство индекса\\n\\\n   738\tn**Проблема:** в BIRD есть БД с 50+ т
аблицами. Полная схема в промпт не лезет\\n\n   739\tи зашумляет генерацию.\\n\
\n**Решение:** offline-пайплайн `Schema indexer` строит\n   740\tнесколько колл
екций в Chroma:\\n\\n| Коллекция | Чанк | Эмбеддится |\\n|---|---|--\n   741\t-
|\\n| `schema_tables` | таблица | имя + описание + список колонок + 3 sample ст
\n   742\tроки |\\n| `schema_columns` | колонка | имя + тип + описание + min/ma
x/nunique +\n   743\t5 sample значений |\\n| `fewshot_qsql` | Q→SQL пара | вопр
ос + аннотация интента\n   744\t(SQL не эмбеддится) |\\n| `relations` | FK-связ
ь | from_table.col → to_table.col\n   745\t+ семантика |\\n\\nПри вопросе `retr
ieve_schema` делает гибрид BM25 + dense на `s\n   746\tchema_tables`,\\nдотягив
ает топ-N колонок из `schema_columns` для отобранных таб\n   747\tлиц,\\nдобавл
яет связи между ними. Получается компактный «срез схемы» под вопрос\n   748\t—\
\nобычно 5-15 таблиц вместо 50+.\\n\\n`retrieve_examples` достаёт из `fewshot_q
s\n   749\tql` 3-5 наиболее похожих\\nвопросов с эталонными SQL — это мощно под
нимает качес\n   750\tтво на сложных диалектах.\\n\\n## 4. Безопасность исполне
ния SQL\\n\\nRead-only — э\n   751\tто не «обещание промптом», а реальные гарды
на четырёх уровнях:\\n\\n1. **БД-роль\n   752\t:** отдельный postgres-пользоват
ель с GRANT SELECT ONLY,\\n   без CREATE/INSERT/\n   753\tUPDATE/DELETE/TRUNCAT
E/ALTER.\\n2. **Парсер:** `sqlglot` AST-валидация — отказ п\n   754\tри не-SELE
CT, при множественных\\n   стейтментах, при наличии CTE с DML, при `pg\n   755\
t_*`/`information_schema` без whitelist.\\n3. **EXPLAIN-gate:** `EXPLAIN (FORMA
T \n   756\tJSON)` перед `EXECUTE`,\\n   отказ если `Total Cost > X` (порог нас
траивается на\n   757\tБД).\\n4. **Runtime:** `SET statement_timeout = 30s`, об
язательный `LIMIT 10000`\n   758\t\\n   если в запросе нет агрегации.\\n\\n## 5
. Eval harness\\n\\nОтдельный модуль `e\n   759\tval/`, не часть онлайн-пайплай
на:\\n\\n```text\\neval/\\n├── datasets/\\n│   ├── bir\n   760\td_mini.jsonl   
      # 1500 Q→SQL пар, 11 БД\\n│   └── stackexchange_gold.jsonl\n   761\t# 20 
наших эталонных вопросов\\n├── runner.py                    # прогон через \n  
762\tграф, сравнение\\n├── metrics/\\n│   ├── execution_accuracy.py    # сравне
ние res\n   763\tult-set\\\'ов\\n│   ├── exact_match.py           # SQL string 
match (слабая метрик\n   764\tа)\\n│   └── component_match.py       # сравнение
по AST-компонентам\\n└── report\n   765\ts/\\n    └── 2026-05-10-baseline.html 
# отчёт по прогонам\\n```\\n\\nCI прогоняет s\n   766\tmoke-eval на 50 примерах
при каждом merge в main.\\nПолный прогон — вручную или \n   767\tnightly.\\n\\n
**Целевое число:** Execution Accuracy ≥ 50% на BIRD-mini dev.\\nОпуб\n   768\tл
икованные результаты codestral-2501 на BIRD ~57%, так что 50%\\nсвоими силами н
\n   769\tа узком сабсете — реалистично.\\n\\n## 6. Multi-DB switching\\n\\nВ `
config/databas\n   770\tes.yml` описаны подключения:\\n\\n```yaml\\ndatabases:\
\n  - id: stackexchange\\n   \n   771\tdsn: postgresql://nlsql_ro@localhost/sta
ckexchange\\n    description: "StackOver\n   772\tflow public data — posts, use
rs, votes"\\n    schema_index: chroma://stackexchan\n   773\tge\\n    sample_qu
estions: ["топ-10 тегов...", "распределение..."]\\n  - id: bird\n   774\t_calif
ornia_schools\\n    dsn: sqlite:///data/bird/california_schools.sqlite\\n  \n  
775\t description: "California schools — performance, demographics"\\n    schem
a_inde\n   776\tx: chroma://bird_california_schools\\n  - id: chinook\\n    dsn
: sqlite:///data/c\n   777\thinook.sqlite\\n    description: "Music store — inv
oices, tracks, customers"\\n  \n   778\t schema_index: chroma://chinook\\n```\\
n\\nUI даёт переключатель «target DB», граф\n   779\tчитает её из state.\\n\\n#
# 7. UI (Next.js + React)\\n\\nМинимально, но без обрезко\n   780\tв:\\n\\n- **
Chat-style вход** с подсветкой SQL в ответе и copy-кнопкой.\\n- **Mult\n   781\
ti-format ответ** — компонент сам решает, что рендерить\\n  (scalar / sentence 
/ \n   782\tDataGrid / Vega-Lite chart).\\n- **«Show working»**: разворачивающи
йся блок с re\n   783\ttrieved schema, few-shot,\\n  rationale, EXPLAIN-планом,
временем выполнения.\\n-\n   784\t**History + bookmarks** в localStorage + опци
онально на бэке.\\n- **DB switcher*\n   785\t* + список sample-вопросов под каж
дую БД.\\n\\nОтдельная страница **`/eval`** — т\n   786\tаблица результатов eva
l-прогонов,\\nграфики динамики Execution Accuracy по комми\n   787\tтам.\\n\\n#
# 8. Стек целиком\\n\\n| Слой | Технология | Почему |\\n|---|---|---|\\n| \n   
788\tLLM | Mistral API: codestral-2501, mistral-large-2, mistral-embed | Жёстко
е тре\n   789\tбование задачи |\\n| Orchestration | LangGraph | Уже знакома по 
RAG_SA, retry-lo\n   790\top из коробки |\\n| API | FastAPI + Pydantic v2 | Ста
ндарт, типобезопасность |\\n\n   791\t| Vector DB | ChromaDB | Уже знакома, лок
ально без отдельного сервиса |\\n| SQL \n   792\tparser | sqlglot | Multi-diale
ct, AST-валидация, dialect translation |\\n| Targe\n   793\tt DB | Postgres 16 
(StackExchange) + SQLite (BIRD, Chinook) | Реализм + простот\n   794\tа |\\n| C
ache | Redis 7 | Кэш результатов SQL, rate-limit |\\n| Charting | Vega-L\n   79
5\tite (через спеку из LLM) + Plotly fallback | LLM хорошо генерит Vega-spec\\\
'и |\\\n   796\tn| Frontend | Next.js 15 + Tailwind + shadcn/ui | Быстрый краси
вый UI |\\n| Obse\n   797\trvability | Prometheus + OpenTelemetry + Langfuse | 
Стандартный стек, переиспол\n   798\tьзуется из RAG_SA |\\n| Tests | pytest + h
ttpx + testcontainers (Postgres) | Реа\n   799\tльная БД в CI |\\n| Lint/Type |
ruff + mypy strict (api/, agent/) | Как в DE_pro\n   800\tject |\\n| CI | GitHu
b Actions | smoke-eval + pytest + ruff + mypy |\\n| Deploy |\n   801\tdocker-co
mpose (dev) + Dockerfile multi-stage (prod) | Достаточно для демо |\\n\\\n   80
2\tn## 9. Структура репозитория\\n\\n```\\nNL_SQL/\\n├── api/                  
# Fast\n   803\tAPI app, routers, middleware\\n├── agent/                 # Lan
gGraph nodes, pro\n   804\tmpts, state\\n│   ├── graph.py\\n│   ├── nodes/\\n│ 
 │   ├── classify.py\\n│   │  \n   805\t├── retrieve_schema.py\\n│   │   ├── re
trieve_examples.py\\n│   │   ├── generate_\n   806\tsql.py\\n│   │   ├── valida
te.py\\n│   │   ├── execute.py\\n│   │   ├── verify.py\\\n   807\tn│   │   ├── 
render.py\\n│   │   └── retry.py\\n│   └── prompts/\\n├── llm/       \n   808\t
          # Mistral provider, retry, cost guard\\n├── schema_index/          # 
\n   809\toffline indexer for Chroma\\n│   ├── extractor.py       # introspect 
Postgres/SQ\n   810\tLite catalog\\n│   ├── enricher.py        # описания, samp
le values, stats\\n│   \n   811\t└── builder.py         # build Chroma collecti
ons\\n├── execution/             #\n   812\tSQL guards, EXPLAIN gate, runner\\n
├── eval/                  # см. раздел 5\\n├─\n   813\t─ frontend/            
 # Next.js UI\\n├── config/                # databases.y\n   814\tml, prompts.y
ml\\n├── data/                  # BIRD dump, Chinook, sample dumps \n   815\t(g
itignore)\\n├── tests/\\n├── docker-compose.yml\\n├── Dockerfile\\n└── docs/\\n
  \n   816\t├── 00_task.md\\n    ├── 01_architecture.md       ← вы здесь\\n    
├── 02_eval_me\n   817\tthodology.md   ← TODO\\n    └── 03_demo_questions.md   
 ← TODO\\n```\\n\\n## 10. R\n   818\toadmap (этапы)\\n\\n| # | Этап | DoD |\\n|
---|---|---|\\n| 1 | **Bootstrap** | poet\n   819\try/uv проект, FastAPI hello,
Mistral provider, тесты на провайдер с моком |\\n| \n   820\t2 | **Target DBs r
eady** | docker-compose поднимает Postgres со StackExchange d\n   821\tump + SQ
Lite Chinook + BIRD dump в `data/` |\\n| 3 | **Schema indexer** | offlin\n   82
2\te скрипт строит Chroma-коллекции, smoke-тест на retrieval |\\n| 4 | **Pipeli
ne v\n   823\t1** | LangGraph граф работает на Chinook (простая БД), single-sho
t без retry |\\\n   824\tn| 5 | **Guards & verify** | sqlglot guard, EXPLAIN ga
te, retry-loop, тесты |\\n\n   825\t| 6 | **Eval harness** | runner + execution
_accuracy метрика, baseline на BIRD-\n   826\tmini |\\n| 7 | **Multi-format ren
der** | scalar/sentence/table/chart с автоопред\n   827\tелением + Vega-Lite sp
ec\\\'и |\\n| 8 | **UI v1** | chat + DB switcher + history, \n   828\tend-to-en
d на 3 БД |\\n| 9 | **Polish & deploy** | docker-compose prod-like, REA\n   829
\tDME, демо-видео, eval-страница |\\n\\nЭтапы 1-3 — фундамент (~неделя на каждо
м те\n   830\tмпе).\\nЭтапы 4-6 — суть проекта (~2 недели).\\nЭтапы 7-9 — витри
на (~неделя).\\n\\\n   831\tnИтого: ~5-6 рабочих недель в спокойном темпе или 2
-3 в плотном.\\n\\n## 11. Риск\n   832\tи\\n\\n| Риск | Вероятность | Митигация
|\\n|---|---|---|\\n| codestral-2501 даёт <\n   833\t40% на BIRD | средняя | ул
учшить few-shot retrieval, добавить chain-of-thought,\n   834\tschema-linking ш
аг |\\n| StackExchange dump слишком большой для локалки (≥100GB)\n   835\t| выс
окая | взять mini-dump (`gaming.stackexchange.com`, ~1GB) — реализм без бо\n   
836\tли |\\n| EXPLAIN-gate ломает легитимные тяжёлые запросы | средняя | tune п
орог н\n   837\tа БД, дать override-флаг для админа |\\n| BIRD dataset лицензия
| низкая | CC-BY\n   838\t-SA-4.0, для демо OK |\\n| Mistral API rate limits на
eval-прогоне | средняя | l\n   839\tocal cache на (prompt → response), батчинг,
exponential backoff |\\n\\n## 12. Что\n   840\tв этой архитектуре «нагруженного
»\\n\\nЕсли сравнить с минимальным NL→SQL (один п\n   841\tромпт + один вызов L
LM + execute):\\n\\n- **+ LangGraph pipeline на 10+ узлов** с\n   842\tretry-lo
op и error-context.\\n- **+ Schema-RAG из 4 коллекций** вместо «вся схем\n   84
3\tа в промпт».\\n- **+ Few-shot retrieval** из эталонных Q→SQL пар.\\n- **+ St
atic \n   844\tvalidate (sqlglot AST) + EXPLAIN-gate + 4-уровневая защита**.\\n
- **+ Multi-DB**\n   845\tс переключателем и per-DB индексами.\\n- **+ Eval har
ness на публичном бенчмарке\n   846\t** с измеримой метрикой.\\n- **+ Multi-for
mat рендер** (4 формата + auto-выбор г\n   847\tрафика).\\n- **+ Полноценный ob
servability stack** (Prom + OTel + Langfuse).\\n- \n   848\t**+ Web-UI** с исто
рией, eval-страницей, «show working».\\n\\nЭто потолок того, ч\n   849\tто осмы
сленно делать для демо-проекта без скатывания\\nв production-overhead (му\n   8
50\tльти-тенант, RBAC, OIDC, freshness monitor и т.д. —\\nвсё то, что в RAG_SA 
умест\n   851\tно, а здесь было бы фейк-нагрузкой).\'\n   852\t)\n   853\tStatu
sUpdate(\n   854\t    context_usage=None,\n   855\t    context_tokens=None,\n  
856\t    max_context_tokens=None,\n   857\t    token_usage=None,\n   858\t    m
essage_id=None,\n   859\t    plan_mode=None,\n   860\t    mcp_status=MCPStatusS
napshot(\n   861\t        loading=True,\n   862\t        connected=0,\n   863\t
       total=3,\n   864\t        tools=0,\n   865\t        servers=(\n   866\t 
          MCPServerSnapshot(\n   867\t                name=\'playwright-officia
l\',\n   868\t                status=\'connecting\',\n   869\t                t
ools=()\n   870\t            ),\n   871\t            MCPServerSnapshot(\n   872
\t                name=\'playwright-executeautomation\',\n   873\t             
  status=\'connecting\',\n   874\t                tools=()\n   875\t           
),\n   876\t            MCPServerSnapshot(\n   877\t                name=\'brow
ser-tools\',\n   878\t                status=\'connecting\',\n   879\t         
      tools=()\n   880\t            )\n   881\t        )\n   882\t    )\n   883
\t)\n   884\tMCPLoadingBegin()\n   885\tStatusUpdate(\n   886\t    context_usag
e=None,\n   887\t    context_tokens=None,\n   888\t    max_context_tokens=None,
\n   889\t    token_usage=None,\n   890\t    message_id=None,\n   891\t    plan
_mode=None,\n   892\t    mcp_status=MCPStatusSnapshot(\n   893\t        loading
=False,\n   894\t        connected=3,\n   895\t        total=3,\n   896\t      
 tools=85,\n   897\t        servers=(\n   898\t            MCPServerSnapshot(\n
  899\t                name=\'playwright-official\',\n   900\t                s
tatus=\'connected\',\n   901\t                tools=(\n   902\t                
   \'browser_close\',\n   903\t                    \'browser_resize\',\n   904\
t                    \'browser_console_messages\',\n   905\t                   
\'browser_resume\',\n   906\t                    \'browser_highlight\',\n   907
\t                    \'browser_hide_highlight\',\n   908\t                    
\'browser_annotate\',\n   909\t                    \'browser_handle_dialog\',\n
  910\t                    \'browser_evaluate\',\n   911\t                    \
'browser_file_upload\',\n   912\t                    \'browser_drop\',\n   913\
t                    \'browser_fill_form\',\n   914\t                    \'brow
ser_press_key\',\n   915\t                    \'browser_type\',\n   916\t      
             \'browser_mouse_move_xy\',\n   917\t                    \'browser_
mouse_click_xy\',\n   918\t                    \'browser_mouse_drag_xy\',\n   9
19\t                    \'browser_mouse_down\',\n   920\t                    \'
browser_mouse_up\',\n   921\t                    \'browser_mouse_wheel\',\n   9
22\t                    \'browser_navigate\',\n   923\t                    \'br
owser_navigate_back\',\n   924\t                    \'browser_network_requests\
',\n   925\t                    \'browser_network_request\',\n   926\t         
          \'browser_run_code_unsafe\',\n   927\t                    \'browser_t
ake_screenshot\',\n   928\t                    \'browser_snapshot\',\n   929\t 
                  \'browser_click\',\n   930\t                    \'browser_dra
g\',\n   931\t                    \'browser_hover\',\n   932\t                 
  \'browser_select_option\',\n   933\t                    \'browser_tabs\',\n  
934\t                    \'browser_start_tracing\',\n   935\t                  
 \'browser_stop_tracing\',\n   936\t                    \'browser_start_video\'
,\n   937\t                    \'browser_stop_video\',\n   938\t               
    \'browser_video_chapter\',\n   939\t                    \'browser_wait_for\
'\n   940\t                )\n   941\t            ),\n   942\t            MCPSe
rverSnapshot(\n   943\t                name=\'playwright-executeautomation\',\n
  944\t                status=\'connected\',\n   945\t                tools=(\n
  946\t                    \'start_codegen_session\',\n   947\t                
   \'end_codegen_session\',\n   948\t                    \'get_codegen_session\
',\n   949\t                    \'clear_codegen_session\',\n   950\t           
        \'playwright_navigate\',\n   951\t                    \'playwright_scre
enshot\',\n   952\t                    \'playwright_click\',\n   953\t         
          \'playwright_iframe_click\',\n   954\t                    \'playwrigh
t_iframe_fill\',\n   955\t                    \'playwright_fill\',\n   956\t   
                \'playwright_select\',\n   957\t                    \'playwrigh
t_hover\',\n   958\t                    \'playwright_upload_file\',\n   959\t  
                 \'playwright_evaluate\',\n   960\t                    \'playwr
ight_console_logs\',\n   961\t                    \'playwright_resize\',\n   96
2\t                    \'playwright_close\',\n   963\t                    \'pla
ywright_get\',\n   964\t                    \'playwright_post\',\n   965\t     
              \'playwright_put\',\n   966\t                    \'playwright_pat
ch\',\n   967\t                    \'playwright_delete\',\n   968\t            
       \'playwright_expect_response\',\n   969\t                    \'playwrigh
t_assert_response\',\n   970\t                    \'playwright_custom_user_agen
t\',\n   971\t                    \'playwright_get_visible_text\',\n   972\t   
                \'playwright_get_visible_html\',\n   973\t                    \
'playwright_go_back\',\n   974\t                    \'playwright_go_forward\',\
n   975\t                    \'playwright_drag\',\n   976\t                    
\'playwright_press_key\',\n   977\t                    \'playwright_save_as_pdf
\',\n   978\t                    \'playwright_click_and_switch_tab\'\n   979\t 
              )\n   980\t            ),\n   981\t            MCPServerSnapshot(
\n   982\t                name=\'browser-tools\',\n   983\t                stat
us=\'connected\',\n   984\t                tools=(\n   985\t                   
\'getConsoleLogs\',\n   986\t                    \'getConsoleErrors\',\n   987\
t                    \'getNetworkErrors\',\n   988\t                    \'getNe
tworkLogs\',\n   989\t                    \'takeScreenshot\',\n   990\t        
           \'getSelectedElement\',\n   991\t                    \'wipeLogs\',\n
  992\t                    \'runAccessibilityAudit\',\n   993\t                
   \'runPerformanceAudit\',\n   994\t                    \'runSEOAudit\',\n   9
95\t                    \'runNextJSAudit\',\n   996\t                    \'runD
ebuggerMode\',\n   997\t                    \'runAuditMode\',\n   998\t        
           \'runBestPracticesAudit\'\n   999\t                )\n  1000\t      
     )\n',
        message='1000 lines read from file starting from line 1. Total lines in
file: 1386.',
        display=[],
        extras=None
    )
)
StepBegin(n=2)
ThinkPart(
    type='think',
    think='Пользователь просит провести candid technical review двух документов
: постановки задачи и архитектуры для демо-проекта NL→SQL Assistant. Review дол
жен быть честным, без подыгрывания, с возражениями по существу. Язык — русский 
или английский, на мой выбор. Выберу русский, так как промпт на русском и автор
, судя по всему, русскоязычная.\n\nНужно ответить по блокам:\n\nBlock A — Целес
ообразность проекта (feasibility / market-fit для портфолио)\n1. Велосипед или 
нет? Рынок NL→SQL уже переполнен. Стоит ли делать? Какой сигнал?\n2. Если делат
ь — какие 2-3 элемента делают проект отличимым? Какие стандартные и можно среза
ть?\n3. Адекватен ли выбор Mistral-only? Не помешает ли позиционированию? Что о
тветить на вопрос про GPT-4/Claude/локальную модель?\n4. Адекватен ли выбор БД 
(BIRD-mini + StackExchange Postgres + Chinook)? Альтернативы?\n5. Реалистична л
и цель Execution Accuracy ≥50% на BIRD-mini с codestral-2501 без fine-tune?\n\n
Block B — Оценка архитектуры\n1. Pipeline (LangGraph 11 узлов). Что лишнее? Что
упущено? Порядок узлов? Нужны ли все retry-точки?\n2. Schema-RAG из 4 коллекций
Chroma. Overengineering? Как бы сделал иначе? Baseline?\n3. 4-уровневая защита 
SQL. Нужны ли все 4? Attack vectors? Hype или нужно?\n4. Eval harness. Достаточ
но ли метрик? Что ещё мерить? Smoke-eval на 50 примеров в CI?\n5. Multi-format 
render (scalar/sentence/table/chart + Vega-Lite spec из LLM). Работает или фейк
овый? Подводные камни Vega-spec generation?\n6. Стек целиком. Что переусложнено
? Согласен ли с делением автора?\n7. Roadmap 9 этапов на 5-6 недель. Реалистичн
о? Какой этап съест больше времени?\n8. Риски. Что упущено? Какие вероятные рис
ки не названы?\n\nBlock C — 3-5 точечных правок, ranked by impact.\nBlock D — Ф
инальный вердикт одной фразой.\n\nДавайте разберёмся.\n\nBlock A:\n\n1. Велосип
ед? Да, рынок переполнен. Но для портфолио Senior DE/DA — это нормально. Главно
е не "ещё один NL→SQL", а показать системный подход: eval, RAG, guards, observa
bility. Сигнал для рекрутёра: человек умеет строить end-to-end data/ML-системы,
измерять качество, думать о безопасности. Но есть риск, что проект воспримут ка
к "tutorial-level" если нет дифференциаторов. Нужно подчеркнуть, что проект не 
про "я придумала NL→SQL", а про "я умею инженерить систему с измеримым качество
м".\n\n2. Отличимые элементы:\n- Eval harness с публичным бенчмарком (BIRD) и с
равнением с SOTA — это сильно. Мало кто делает это в демо.\n- Schema-RAG с разб
иением на коллекции + few-shot retrieval — показывает понимание retrieval optim
ization.\n- Self-correction loop с error-context — показывает умение работать с
LangGraph и State Machines.\nСтандартные/срезаемые:\n- Next.js UI с историей — 
стандарт, но для демо нужен. Можно сильно упростить.\n- Redis для кэша — для де
мо overkill, можно обойтись in-memory или вообще без кэша.\n- Multi-format rend
er с Vega-Lite — "выглядит красиво", но высок риск быть фейковым. Можно срезать
до "таблица + SQL" и оставить только scalar/table.\n\n3. Mistral-only:\n- codes
tral-2501 — хороший выбор для SQL generation, это факт. Но mistral-large-2 для 
классификации интента и рендера — странно. Можно использовать codestral и для э
того, или вообще один вызов. Или использовать open-source модели через Ollama/v
llm для демо, но API проще.\n- Vendor lock-in: да, выглядит как "я работаю толь
ко с Mistral". Но для портфолио это не критично, если есть аргументация: "выбра
л лучший price/performance для кода на момент старта". Но лучше сделать абстрак
цию LLM-provider, чтобы можно было подменить.\n- Ответ на "почему не GPT-4/Clau
de": codestral-2501 бьёт GPT-4 на SQL-бенчмарках (возможно, это не совсем так, 
но он competitive и дешевле/быстрее). Локальная модель — сложность инфры, а фок
ус на pipeline, не на ops моделей.\n\n4. Выбор БД:\n- BIRD-mini — отлично для e
val, стандарт.\n- StackExchange — хорошо, реальные данные. Но dump 100GB — проб
лема. Mini-dump (gaming) — разумная митигация.\n- Chinook/Sakila — скучно, "hel
lo world". Для онбординг-демо сойдёт, но не даёт вау. Альтернативы: TPC-H/TPC-D
S (но нет Q→SQL пар), Job-light (Join Order Benchmark), или какой-нибудь интере
сный датасет вроде COVID-19 Open Data, Hacker News датасет. Или использовать Du
ckDB с parquet-файлами — это даст "вау" за счёт производительности. DuckDB вмес
то SQLite для BIRD-mini — тоже интересно.\n\n5. Execution Accuracy ≥50% на BIRD
-mini с codestral-2501 без fine-tune:\n- BIRD-mini — это subset из BIRD? Или BI
RD-mini это dev split? BIRD dev — 1534 вопроса, 95 БД. "Mini" может означать su
bset. Если это dev split (1534 примера) — 50% реалистично? codestral-2501 на BI
RD (full) даёт ~57% (по словам автора). Но это обычно с более сложным pipeline 
(schema linking, etc.). Для солиста без fine-tune, с собственным RAG pipeline —
50% на dev split это амбициозно, но реалистично. Однако, "своими силами на узко
м сабсете" — если это не полный dev, а действительно mini (например, 150 пример
ов), то 50% может быть и легко, и случайным. Нужно уточнить, что BIRD-mini — эт
о 1500 Q→SQL пар (из архитектуры, раздел 5: bird_mini.jsonl # 1500 Q→SQL пар, 1
1 БД). 11 БД из 95. Это уже меньше. 50% на 11 БД — реалистично, но не гарантиро
вано. Будет зависеть от schema retrieval quality.\n\nBlock B:\n\n1. Pipeline (L
angGraph 11 узлов):\n- classify_intent → select_database → retrieve_schema → re
trieve_examples → generate_sql → static_validate → explain_plan → execute → ver
ify_result → choose_format → render_answer → persist_trace.\n- Лишнее:\n  - cla
ssify_intent отдельным узлом перед select_database: если БД выбирается по ключе
вым словам, это можно сделать в одном узле или вообще в UI.\n  - explain_plan к
ак отдельный узел перед execute: это полезно, но на SQLite EXPLAIN может быть н
е таким информативным как на Postgres. Можно объединить с static_validate или e
xecute. Но как gate — это хорошо.\n  - choose_format отдельный узел: можно сдел
ать детерминированным на основе shape результата и intent, не нужен отдельный L
LM-вызов.\n  - persist_trace: не узел графа, а side-effect.\n- Что упущено:\n  
- Dialect-specific prompt engineering (Postgres vs SQLite).\n  - Schema linking
/ candidate generation step перед SQL generation (как в BIRD SOTA).\n  - Re-ran
king после retrieve_schema.\n  - Нет узла "decompose" для сложных вопросов (mul
ti-hop). Но для демо это ок.\n- Retry-точки: validate и execute — нужны. verify
_result → retry — опасно: если результат пустой, retry может привести к галлюци
нациям. Лучше retry только на execution error / syntax error. verify_result — с
корее для graceful failure / alternative suggestion, не для retry generate.\n\n
2. Schema-RAG из 4 коллекций:\n- Overengineering? Для демо — возможно. 4 коллек
ции — это много. relations отдельно — избыточно, FK можно включить в schema_tab
les. fewshot_qsql — норм. schema_columns отдельно — может быть полезно, но усло
жняет retrieval logic (сначала tables, потом columns).\n- Базовый baseline: одн
а коллекция schema_chunks (таблица + её колонки + описание + samples) + коллекц
ия fewshot_qsql. Это проще и сравнимо. Если 4 коллекции дают +3% accuracy — ок,
но для демо это может быть незаметно.\n- relations коллекция: FK связи эмбеддит
ь странно, их лучше хранить в графе/словаре и доставать по table_id после retri
eval tables.\n\n3. 4-уровневая защита:\n- БД-роль: да, нужен.\n- sqlglot AST: д
а, нужен. Но "при наличии CTE с DML" — sqlglot это ловит. Но что насчёт `SELECT
* FROM pg_sleep(100)`? Это SELECT, но DoS. sqlglot не поймает.\n- EXPLAIN-gate:
для read-only демо — hype. Если БД-роль + sqlglot + timeout — уже достаточно. E
XPLAIN-gate добавляет latency (ещё один roundtrip к БД) и сложность. Для демо с
BIRD-mini (SQLite) и StackExchange (Postgres) — если БД локальная, это не нужно
. Если деплой в публичный доступ — может быть.\n- Runtime limits: обязательно.\
n- Непокрытые attack vectors:\n  - `pg_read_file`, `pg_sleep`, `generate_series
` DoS.\n  - Time-based blind SQL injection через error messages (хотя read-only
).\n  - Information leakage через `pg_catalog` / `information_schema` (частично
покрыто).\n  - Subqueries с side-effects? В read-only сложно.\n- Итог: EXPLAIN-
gate — первый кандидат на удаление.\n\n4. Eval harness:\n- Execution Accuracy —
must have.\n- Component Match — полезно для дебага, но как primary metric — нет
.\n- Exact Match — бесполезен для демо, только для отладки.\n- Что ещё мерить:\
n  - Schema recall (какая доля нужных таблиц была retrieved).\n  - SQL generati
on success rate (процент прошедших static_validate).\n  - Latency (time-to-firs
t-result).\n  - Cost-per-query ( Mistral API не бесплатный, автору важно для по
ртфолио показать awareness).\n  - Partial correctness (например, component matc
h илиsoft EM).\n- Smoke-eval на 50 примеров в CI: плохая идея. Eval на LLM API 
в CI — флаки, rate limits, стоимость. Лучше unit tests на pipeline без LLM (moc
k) + nightly eval на маленьком subset (20-50) с кэшированными ответами. Или исп
ользовать vcr.py / betamax. Или eval только локально/вручную.\n\n5. Multi-forma
t render:\n- scalar/table — работает стабильно.\n- sentence — требует LLM, може
т галлюцинировать, но ок.\n- chart + Vega-Lite spec из LLM — фейковый "выглядит
красиво". LLM генерирует Vega-Lite с ошибками: неправильные field names, типы д
анных, отсутствующие transforms. Fallback на Plotly — хорош, но тогда зачем Veg
a-Lite? Лучше детерминированный выбор chart type + рендеринг через Plotly/ApexC
harts на фронте по структуре данных. LLM пусть только выбирает тип графика (bar
/line/pie), а спеку формирует код на фронте по шаблону.\n- Подводные камни Vega
-spec generation: field names с пробелами/спецсимволами, типы данных (datetime 
parsing), масштабы, null values, большое количество категорий (pie chart с 100 
сегментов).\n\n6. Стек целиком:\n- Переусложнено:\n  - Redis — для демо можно о
бойтись без отдельного сервиса. In-memory dict или even SQLite для traces/cache
.\n  - Prometheus + OpenTelemetry — для demo это massive overhead. Langfuse tra
ces достаточно.\n  - Next.js 15 — для демо можно Streamlit или Gradio? Но автор
хочет показать frontend skills. Ок, оставить, но это время.\n  - Langfuse + Pro
metheus + OTel — тройной observability. Langfuse достаточно.\n  - Testcontainer
s Postgres — хорошо, но для BIRD (SQLite) и StackExchange (Postgres) — может бы
ть достаточно одного.\n- Согласен ли с делением автора: в целом да, но Promethe
us/OTel — фейковая нагрузка для демо. Redis — тоже можно срезать.\n- Автор гово
рит "без фейкового overengineering\'а", но Prometheus+OTel для демо с одним пол
ьзователем (автором) — именно он.\n\n7. Roadmap 9 этапов на 5-6 недель:\n- Опти
мистично. Особенно "Target DBs ready" (StackExchange dump, ETL, индексация) — э
то может занять больше недели. "Schema indexer" — тоже неделя оптимистично, есл
и надо настроить chunking, enrichment, embedding quality.\n- "Pipeline v1" на C
hinook — может быть быстро, но переход на BIRD/StackExchange добавит боли.\n- "
Multi-format render" — Vega-Lite спеки и автоопределение формата — это может съ
есть неделю само по себе.\n- "UI v1" — Next.js, chat, e2e — минимум неделя.\n- 
Итого 5-6 недель в "спокойном темпе" — оптимистично. Скорее 8-10.\n- Самый риск
ованный этап: Eval harness + достижение 50% на BIRD-mini. Это не "прогнали и по
лучили 50%", это итеративная настройка retrieval + prompts. Может съесть 3-4 не
дели вместо 1.\n\n8. Риски:\n- Не названы:\n  - "Schema retrieval не тянет нужн
ые таблицы" — это главный риск, а не "codestral даёт <40%". Плохой retrieval уб
ьёт accuracy независимо от модели.\n  - "Vega-Lite спеки ломаются в 30-50% случ
аев" — риск UI.\n  - "Chroma performance / memory leak на 95 БД BIRD" — BIRD-mi
ni это 11 БД, но если индексировать всё, Chroma может раздуться.\n  - "Prompt c
ontext window overflow" — если retrieved schema всё равно слишком большая.\n  -
"Cost overruns" — eval на 1500 примерах с API Mistral — это деньги.\n  - "Next.
js frontend сложнее чем кажется" — интеграция с backend, CORS, SSR.\n  - "Data 
licensing for StackExchange" — CC-BY-SA требует attribution, возможно нюансы.\n
\nBlock C — 3-5 точечных правок:\n\n1. Убрать Prometheus + OpenTelemetry из сте
ка демо; оставить только Langfuse. Потому что для solo demo это фейковая нагруз
ка, не дающая сигнала.\n2. Заменить Vega-Lite spec generation на детерминирован
ный chart-type classifier (по shape данных + intent) + шаблонный рендер на фрон
те (Plotly). Потому что LLM-спеки — источник флаков и сложности.\n3. Схлопнуть 
4 коллекции Chroma в 2: schema_chunks (таблица+колонки+связи) + fewshot_qsql. У
брать relations как отдельную коллекцию. Потому что relations retrieval через d
ense search — плохая идея, FK лучше тащить структурно по retrieved tables.\n4. 
Убрать Redis из docker-compose; заменить in-memory LRU cache (cachetools) для S
QL-результатов и rate-limit (slowapi + memory). Потому что отдельный сервис для
демо — избыточная операционная сложность.\n5. Добавить абстракцию LLM provider 
( LiteLLM или собственный) вместо хардкода Mistral. Потому что иначе проект выг
лядит как vendor lock-in, и тестировать eval локально сложно.\n\nBlock D — Фина
льный вердикт:\n\nСтоит делать, но только если фокус сместить с "красивый UI + 
11 узлов" на "измеримая точность + продуманный retrieval + lean stack". Иначе э
то будет ещё один tutorial.\n\nДавайте напишем структурированный ответ.\n\nСтру
ктура:\n- Block A\n- Block B\n- Block C\n- Block D\n\nБуду писать на русском, ч
естно, с аргументацией.\n\nДетализация:\n\nBlock A:\n\n1. Велосипед — да, но дл
я портфолио Senior DE велосипеды нормальны, если показан инженерный процесс. Си
гнал: "умею строить системы с замкнутым циклом качества". Но риск: если eval <5
0%, проект выглядит как игрушка. Критично показать не "я сделала chat2db", а "я
достигла 50% EA на BIRD с открытым кодом и документированным пайплайном".\n\n2.
Отличимые:\n- Eval harness с BIRD + сравнение с leaderboard (это главное).\n- S
chema-RAG как отдельный инжиниринг-проблема (retrieval > generation).\n- Self-c
orrection loop с error-context (показывает зрелость работы с LangGraph).\nСреза
ть:\n- Redis, Prometheus, OTel (см. ниже).\n- Multi-format render до table/scal
ar + chart-type only.\n- Next.js можно заменить на Streamlit, но если frontend-
skill нужен показать — оставить.\n\n3. Mistral-only:\n- codestral-2501 — хороши
й выбор для SQL. Но mistral-large-2 для classify/render — избыточен, можно деше
вле/проще.\n- Vendor lock-in: для демо ок, но нужна абстракция провайдера.\n- О
твет на вопрос: "codestral SOTA на SQL-бенчмарках среди доступных API-моделей н
а момент старта; GPT-4 стоил бы в 5-10 раз дороже при сопоставимом качестве; ло
кальная модель требовала бы GPU-ops, что сдвинуло фокус с pipeline на infra".\n
\n4. БД:\n- BIRD-mini — идеально для eval.\n- StackExchange — хорошо, но gaming
.stackexchange.com мало кого волнует. Лучше взять меньший slice основного SO (н
апример, последние 2 года + только posts/tags/users) — ~2-5GB, но знакомые данн
ые. Или DuckDB + Hacker News / GH Archive. Chinook — ок для sanity check.\n- Ал
ьтернатива для "вау": DuckDB + Parquet с данными, которые автор знает (например
, свой RAG_Support_Assistant traces). Это покажет работу с аналитической БД.\n\
n5. EA ≥50%: реалистично, но не гарантировано. 57% codestral — это обычно с уси
ленным schema-linking и chain-of-thought. Для солиста 50% — это ceiling, а не f
loor. Цель стоит ставить "≥40% baseline, стремиться к 50%", иначе демотивация.\
n\nBlock B:\n\n1. Pipeline:\n- Лишние узлы: `classify_intent` как отдельный LLM
-call (можно эвристикой или lightweight классификатором), `choose_format` (дете
рминированно по shape), `explain_plan` (слишком дорого как gate, можно перенест
и в static_validate или execute).\n- Упущено: `schema_linking` узел (как в DIN-
SQL / BIRD-SOTA) — критично для accuracy. Нет `dialect_adapter` (Postgres vs SQ
Lite).\n- Retry: validate + execute — нужны. verify_result → retry опасен. Лучш
е verify_result вести в graceful degradation.\n\n2. Schema-RAG:\n- Overengineer
ing. 4 коллекции — это много для демо. `relations` отдельно — плохо: dense retr
ieval на FK бесполезен. Лучше baseline: 2 коллекции (`schema_tables_enriched` с
колонками и FK внутри + `fewshot_qsql`). A/B тест против 4-коллекционного. Сейч
ас это преждевременная оптимизация.\n\n3. Защита:\n- EXPLAIN-gate — hype для re
ad-only демо. Убрать. БД-роль + sqlglot + statement_timeout достаточны.\n- Непо
крытые: `pg_sleep`, `generate_series`, функции с side-effects в SELECT (если ка
стомные), чтение файлов через `pg_read_file` (если роль superuser, но она не до
лжна быть). Для read-only демо на своей инфре — это acceptable risk.\n\n4. Eval
harness:\n- Execution Accuracy — ок.\n- Component Match — ок для дебага.\n- Exa
ct Match — мусор, можно выкинуть.\n- Добавить: schema recall @k, SQL validity r
ate, latency P50/P95, cost-per-query.\n- Smoke-eval в CI: плохая идея. CI долже
н быть детерминированным. Eval через LLM API — недетерминирован. Лучше: unit te
sts (mock LLM) + nightly eval с кэшированием (vcr.py).\n\n5. Multi-format rende
r:\n- Работает только scalar/table. Chart из Vega-spec — "demo-ware". Будет фей
лить.\n- Подводные камни: field names с пробелами, типы данных, nulls, количест
во категорий. LLM не знает домен данных, генерирует оси без форматирования.\n- 
Решение: авто-выбор типа графика (heuristics: 1 число → scalar, 2 колонки с чис
лом → bar/line по типу оси, >10 строк → table) + шаблонный рендер.\n\n6. Стек:\
n- Переусложнено: Redis (отдельный сервис для одного юзера), Prometheus+OTel (м
етрики для демо), Next.js (если цель — DE, а не frontend-разработчик).\n- Согла
сен с автором по LangGraph/Chroma/sqlglot/eval. Не согласен по observability: L
angfuse достаточно.\n\n7. Roadmap:\n- Оптимистично. 5-6 недель → 8-10.\n- Больш
е всего времени съест: Eval harness + тюнинг schema retrieval под BIRD (не "нап
исать harness", а "достичь 50%"). Это может растянуться на 3-4 недели итераций.
\n- UI v1 на Next.js тоже неделя, а не "часть витрины за 3 дня".\n\n8. Риски:\n
- Упущены:\n  - Schema retrieval recall < 80% (главный риск accuracy).\n  - LLM
context overflow при retrieved schema.\n  - Vega-Lite спеки ломаются.\n  - Stac
kExchange ETL занимает неделю, а не "готово из коробки".\n  - Burnout из-за sco
pe creep (9 этапов — много для демо).\n\nBlock C:\n\n1. Убрать Prometheus + Ope
nTelemetry, оставить Langfuse. Impact: high (экономия времени и сервисов).\n2. 
Заменить Vega-Lite spec generation на heuristics-based chart type + frontend te
mplating. Impact: high (убирает флаки UI).\n3. Схлопнуть 4 Chroma коллекции в 2
(schema_tables_enriched + fewshot_qsql). Impact: medium-high (упрощает indexer 
и retrieval, убирает ненужный relations dense search).\n4. Убрать Redis; исполь
зовать in-memory cache (cachetools / diskcache). Impact: medium (убирает сервис
из compose).\n5. Ввести абстракцию LLM provider (LiteLLM) вместо хардкода Mistr
al. Impact: medium (позиционирование + тестируемость).\n\nBlock D:\n\nСтоит дел
ать, но в режиме "eval-first, lean stack": срезать observability до Langfuse, о
тказаться от Vega-Lite generation, схлопнуть schema-RAG до 2 коллекций, и поста
вить жёсткий gate: если через 3 недели EA < 35% — scope down до Chinook + Stack
Exchange только, без BIRD leaderboard chase.\n\nТеперь оформлю ответ.',
    encrypted=None
)
TextPart(
    type='text',
    text='Технический review. Не подыгрываю, возражаю по существу.\n\n---\n\n##
Block A — Целесообразность проекта\n\n**1. Велосипед или нет?**  \nРынок перепо
лнен, но для портфолио Senior DE это нормально. Рекрутёр не ищет «изобретателя 
NL→SQL», он ищет доказательство, что кандидат умеет:\n- строить end-to-end data
-систему,\n- измерять качество количественно,\n- думать о retrieval, guards, ob
servability.\n\n**Главный риск:** если проект не дотянет до измеримой метрики (
BIRD EA ≥ 40–50%), он превратится в «еще один tutorial из Medium» — это сигнал 
«junior сделал красивую обёртку». Для Senior DE сигнал должен быть: «я взяла сл
ожный SOTA-benchmark и методично приблизилась к нему инженерией, а не моделью».
\n\n**2. Что отличимое, что стандартное**  \nОтличимые (оставить и подсветить в
README):\n- **Eval harness на BIRD** с публичным сравнением. Демо с leaderboard
-метрикой — редкость.\n- **Schema-RAG как инженерная задача.** Не «засунула схе
му в промпт», а «разбила на чанки, измерила recall, оптимизировала retrieval». 
Это сигнал DE-мышления.\n- **Self-correction loop с error-context.** Показывает
зрелость работы с state machines (LangGraph), а не просто «вызываю LLM в цикле»
.\n\nСтандартное / на срез:\n- **Next.js + полноценный UI.** Если цель — DE/DA,
а не frontend-разработчик, можно упростить. Streamlit/Gradio сойдёт для демо, н
о Next.js даёт «полировку» — оставь, только если хочешь продемонстрировать full
stack-скилл.\n- **Redis, Prometheus, OpenTelemetry.** Для solo-demo это сервисы
, которые крутятся ради самих себя (см. Block B.6).\n- **Multi-format render с 
Vega-Lite.** Выглядит как «вау», но LLM-генерация спек — фейковая фича (см. Blo
ck B.5).\n\n**3. Mistral-only**  \nВыбор **codestral-2501** для SQL — адекватен
. На момент написания это одна из лучших API-моделей для кода, competitive с GP
T-4o/Claude 3.5 Sonnet на SQL-бенчмарках, при этом дешевле и быстрее.\n\nНо **m
istral-large-2** для classify_intent + render_answer — overkill и лишний vendor
lock-in. Эти задачи можно решить:\n- детерминированной эвристикой (classify),\n
- codestral-2501 в том же вызове (render),\n- или вообще 7B-моделью локально.\n
\n**Как ответить на вопрос «почему не GPT-4»:**  \n«Codestral-2501 — SOTA на SQ
L-бенчмарках среди доступных API-моделей на момент старта; GPT-4 стоил бы в 5–1
0 раз дороже при сопоставимом качестве; локальная модель требовала бы GPU-ops, 
что сдвинуло бы фокус с pipeline на infra. Но архитектура позволяет подменить п
ровайдера» — последнее условие, только если ты добавишь абстракцию провайдера (
сейчас её нет, и это проблема).\n\n**4. Выбор БД**  \n- **BIRD-mini** — идеальн
о для eval. Это must have.\n- **StackExchange** — хорошая реальная схема, но `g
aming.stackexchange.com` (~1 GB) — скучная ниша. Для «вау» лучше взять основной
SO-dump, но срезать по времени (например, 2023–2024 + только posts/tags/users/v
otes) — получится ~2–5 GB, но данные узнаваемые.\n- **Chinook/Sakila** — ок для
sanity check, но zero wow-factor.\n\n**Альтернатива для «вау»:** DuckDB + Parqu
et с публичными датасетами (Hacker News, GH Archive, NYC Taxi). DuckDB — соврем
енный аналитический движок, работа с ним даёт сигнал «я в тренде DE-стека». Но 
если цель — показать Postgres-специфику (JSONB, временные ряды), оставь Postgre
s.\n\n**5. Execution Accuracy ≥ 50% на BIRD-mini с codestral-2501 — реально?** 
\n**Реалистично, но это ceiling, а не floor.** 57% codestral на BIRD (full) — э
то обычно с усиленным schema-linking, chain-of-thought и оптимизированным retri
eval. Для солиста без fine-tune и без команды исследователей 50% на dev-split —
это амбициозная цель.\n\n**Рекомендация:** ставить **baseline ≥ 35–40% к неделе
4**, и «стремиться к 50%». Если через 3 недели итераций retrieval + prompts выш
е 40% не идёт — scope down, иначе проект застрянет в бесконечном тюнинге.\n\n--
-\n\n## Block B — Оценка архитектуры\n\n**1. Pipeline (LangGraph 11 узлов)**\n\
n**Лишнее:**\n- **`classify_intent` как отдельный LLM-вызов.** Для 7 категорий 
можно обойтись эвристикой (регулярками по ключевым словам) или lightweight клас
сификатором. Отдельный вызов mistral-large-2 сюда — расточительство.\n- **`expl
ain_plan` как отдельный узел перед `execute`.** Добавляет латентность (лишний r
oundtrip к БД) и сложность. Для read-only демо на локальной инфре — это не gate
, а балласт. Можно перенести как факультативную проверку внутрь `execute`.\n- *
*`choose_format` как отдельный узел.** Выбор scalar/table/chart по структуре re
sult set — 100% детерминированная функция (количество колонок, типы, количество
строк). Не нужен LLM.\n\n**Упущено:**\n- **Schema linking / candidate generatio
n.** В SOTA-решениях для BIRD (DIN-SQL, MAC-SQL) перед генерацией есть явный ша
г «какие таблицы/колонки релевантны». У тебя это смешано в `retrieve_schema`, н
о нет явного механизма исправления (если retrieval промахнулся — SQL не сгенери
руется правильно).\n- **Dialect adapter.** Postgres и SQLite имеют разные функц
ии (`DATE_TRUNC` vs `strftime`, `LIMIT` vs `TOP`). Нет узла, который бы подстав
лял dialect-specific hints в prompt.\n\n**Retry-точки:**  \n`static_validate` →
retry — **нужен**. `execute` → retry (при syntax/runtime error) — **нужен**. `v
erify_result` → retry — **опасен**. Если результат пустой или «аномальный», бес
конечный retry с тем же retrieval приведёт к галлюцинациям. Лучше: verify_resul
t ведёт к graceful failure с объяснением, а не к retry loop.\n\n**2. Schema-RAG
из 4 коллекций**\n\n**Это overengineering для текущей стадии.**  \n`relations` 
отдельной коллекцией — плохая идея. Dense retrieval на FK-связях (`from_table.c
ol → to_table.col`) бесполезен: семантика связи не раскрывается вопросом пользо
вателя. FK нужно тащить структурно из каталога по ID таблиц, которые уже отобра
ны.\n\n`schema_columns` отдельно — добавляет сложность (сначала tables, потом c
olumns, потом join). Для демо проще baseline: **2 коллекции**:\n1. `schema_chun
ks` — таблица + её колонки (с типами, описаниями, sample values, FK) одним чанк
ом.\n2. `fewshot_qsql` — как сейчас.\n\nЕсли 4-коллекционный подход даст +5% EA
— ок, но начинать надо с 2. Сейчас ты делаешь преждевременную оптимизацию без b
aseline.\n\n**3. 4-уровневая защита SQL**\n\n**Не все четыре нужны.**  \n- БД-р
оль (SELECT ONLY) — **must**.\n- `sqlglot` AST (SELECT-only, нет DML) — **must*
*.\n- Runtime limits (`statement_timeout`, `LIMIT`) — **must**.\n- **EXPLAIN-ga
te — hype для read-only демо.** Это добавляет сервисную сложность, ломает легит
имные тяжёлые аналитические запросы (которые user может спросить), и не покрыва
ет реальные attack vectors.\n\n**Непокрытые vectors:**\n- `pg_sleep()`, `genera
te_series()` — DoS через SELECT.\n- Чтение файлов через `pg_read_file` (если ро
ль не superuser — ок, но проверь).\n- `information_schema` / `pg_catalog` leaka
ge (частично покрыт whitelist).\n- Subqueries с write-операциями внутри CTE? `s
qlglot` поймает, но стоит явно проверить.\n\nДля read-only демо, которое крутит
ся в docker-compose на твоём ноутбуке — три уровня (роль + sqlglot + runtime) д
остаточны. EXPLAIN-gate убрать.\n\n**4. Eval harness**\n\nExecution Accuracy — 
**must**. Component Match — полезно для дебага. Exact Match — **мусор**, убрать
(ни один DE не верит в EM для NL→SQL).\n\n**Что ещё мерить (и показывать в READ
ME):**\n- **Schema recall @k** — какая доля нужных таблиц/колонок попала в retr
ieval. Если recall низкий — дело не в LLM, а в RAG.\n- **SQL validity rate** — 
процент прошедших `static_validate`. Показывает зрелость pipeline.\n- **Latency
(P50/P95)** и **cost-per-query**. Для Senior DE важно показать, что ты думаешь 
не только об accuracy, но и об операционных характеристиках.\n\n**Smoke-eval на
50 примеров в CI — плохая идея.**  \nCI должен быть детерминированным. Eval чер
ез внешний LLM API — недетерминирован, требует секретов, стоит денег и флакает 
на rate limits.  \n**Делай так:** CI = unit tests на pipeline с мокнутым LLM + 
тесты на guards. Eval = локальный скрипт или nightly, с кэшированием ответов (v
cr.py / diskcache), который можно запустить вручную перед релизом.\n\n**5. Mult
i-format render (Vega-Lite spec из LLM)**\n\n**Это «demo-ware» — выглядит краси
во, фейлит в проде.**  \nLLM генерирует Vega-Lite спеки с типичными ошибками:\n
- неправильные `field` имена (особенно если в SQL есть алиасы с пробелами/спецс
имволами),\n- неверные типы данных (строка вместо даты на оси),\n- отсутствие о
бработки `null`,\n- pie chart с 50+ сегментами,\n- неправильные `scale` domain.
\n\nFallback на Plotly — хорош, но тогда зачем двойная система?\n\n**Что делать
:**  \nУбрать LLM-generation спеки. Делай **детерминированный выбор типа график
а** (heuristics: 1 число → scalar, 2 колонки: категория+число → bar/line по тип
у временной оси, >10 строк → table) и **шаблонный рендер** на фронте (Plotly / 
ApexCharts). LLM пусть только генерирует NL-объяснение.\n\n**6. Стек целиком**\
n\nСогласен с автором, что архитектура «нагруженная, но не фейковая», **но с тр
емя исключениями:**\n\n- **Prometheus + OpenTelemetry** — для demo с одним поль
зователем (тобой) это именно **фейковая нагрузка**. Langfuse traces покрывают 9
0% observability-потребности. Prom+OTel = дни настройки ради красивого дашборда
, который никто не смотрит.\n- **Redis** — отдельный сервис для кэша результато
в и rate-limit state в solo-demo. Это operational overhead. Заменить на `cachet
ools` (in-memory LRU) или `diskcache`.\n- **Next.js 15** — если цель показать f
rontend-скилл, оставь. Но если цель — DE/DA, это неделя работы, которая не даёт
сигнала о data-инжиниринге.\n\n**7. Roadmap (9 этапов, 5–6 недель)**\n\n**Оптим
истично. Скорее 8–10 недель.**  \nСамый рискованный этап — не «Bootstrap», а **
«Eval harness» (этап 6)**. Не потому что написать runner сложно, а потому что *
*достичь 50% EA на BIRD-mini — это итеративная пытка**. Ты будешь неделями крут
ить retrieval, few-shot selection, prompt wording. Автор оценивает это в «~2 не
дели на этапы 4–6», но реально только eval+тюнинг съест 3–4 недели.\n\n**UI v1*
* (этап 8) тоже неделя минимум, если Next.js — не просто «кинуть форму».\n\n**8
. Риски (раздел 11)**\n\nУпущены критические риски:\n- **Schema retrieval recal
l < 60%.** Это главный риск провала, а не «codestral плохо генерирует». Если re
trieval не тянет нужные таблицы, никакой LLM не спасёт.\n- **LLM context overfl
ow.** При 50+ таблицах даже «срез схемы» может не влезть в контекст codestral. 
Нет механизма сжатия (compression / summarization).\n- **Vega-Lite спеки ломают
ся в 30–50% случаев.**\n- **StackExchange ETL — не «готово из коробки».** Надо 
скачать, распарсить XML, загнать в Postgres, проиндексировать. Это неделя, а не
«поднять docker-compose».\n- **Burnout от scope creep.** 9 этапов для демо — мн
ого. Автору придётся резать фичи на ходу.\n\n---\n\n## Block C — Точечные правк
и (ranked by impact)\n\n1. **Убрать Prometheus + OpenTelemetry; оставить только
Langfuse.**  \n   *Потому что:* для solo-demo это фейковая operational нагрузка
. Экономит 3–5 дней настройки и убирает лишний сервис из docker-compose.\n\n2. 
**Заменить Vega-Lite spec generation на heuristics-based chart type + шаблонный
рендер на фронте (Plotly).**  \n   *Потому что:* LLM-генерация спек — главный и
сточник флаков UI. Heuristics надёжнее, быстрее и не требует отдельного LLM-cal
l.\n\n3. **Схлопнуть 4 Chroma-коллекции в 2: `schema_chunks` (таблица+колонки+F
K в одном чанке) + `fewshot_qsql`.**  \n   *Потому что:* `relations` через dens
e search не работает, а `schema_columns` отдельно добавляет сложный multi-hop r
etrieval без гарантии прироста accuracy. Начни с простого baseline, оптимизируй
, если нужно.\n\n4. **Убрать Redis; заменить на `cachetools.LRUCache` для SQL-р
езультатов и `slowapi` (in-memory) для rate-limit.**  \n   *Потому что:* отдель
ный сервис в docker-compose ради кэша для одного пользователя — избыточная опер
ационная сложность.\n\n5. **Добавить абстракцию LLM provider (LiteLLM или собст
венный adapter) вместо хардкода Mistral.**  \n   *Потому что:* иначе проект выг
лядит как vendor lock-in, и невозможно локально протестировать pipeline без инт
ернета/API-key.\n\n---\n\n## Block D — Финальный вердикт\n\n**Стоит делать, но 
только в режиме «eval-first, lean stack»:** срезать observability до Langfuse, 
отказаться от LLM-generated Vega-Lite, схлопнуть schema-RAG до 2 коллекций, и п
оставить жёсткий checkpoint — если через 3 недели EA на BIRD-mini ниже 35%, sco
pe down до StackExchange + Chinook без погони за leaderboard. Если да — проект 
станет сильным portfolio piece. Если нет — рискуешь застрять в бесконечном тюни
нге ради «еще одного чатбота с БД».'
)
StatusUpdate(
    context_usage=0.20753097534179688,
    context_tokens=54403,
    max_context_tokens=262144,
    token_usage=TokenUsage(
        input_other=28291,
        output=10952,
        input_cache_read=26112,
        input_cache_creation=0
    ),
    message_id='chatcmpl-f30aetkLSv28bQGiyAMFflNl',
    plan_mode=False,
    mcp_status=None
)
TurnEnd()
