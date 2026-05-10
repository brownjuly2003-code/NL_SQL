# NL→SQL Assistant — архитектура (максимально нагруженный вариант)

**Дата:** 2026-05-10
**Статус:** v1 — superseded after CX/KM review (2026-05-10). Документ оставлен как исторический. Действующая baseline: `02_architecture_v2.md`.

> ⚠️ **Известные ошибки v1**, исправлены в v2:
> - **BIRD Mini-Dev = 500 примеров** (не 1500/11 БД, как ниже в разделе 5)
> - **codestral-2501 deprecated** с ноября 2025 → переход на `codestral-latest` (v25.08)
> - 11-узловой pipeline → 6 узлов
> - 4 коллекции Chroma → 2
> - стек: убраны Prometheus + OTel + Redis (избыточно для solo-demo)
> - Vega-Lite от LLM → детерминированный chart picker + Plotly шаблоны
> - Mistral-only → provider abstraction + 30-question bakeoff
> - eval target: 50% EA → baseline 35-40%, stretch 50%, hard checkpoint неделя 3

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
