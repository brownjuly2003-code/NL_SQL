# NL→SQL Assistant — архитектура v2 (lean baseline)

**Дата:** 2026-05-10
**Статус:** active baseline (после CX + KM review v1)
**Заменяет:** `01_architecture.md`
**Сопровождает:** `00_task.md`, `03_eval_methodology.md`

> «Lean» здесь = ровно столько компонентов, сколько даёт измеримый сигнал в портфолио
> Senior DE. Всё, что не даёт сигнала или дублирует RAG_Support_Assistant, удалено.
> Каждое решение — следствие конкретной правки CX/KM, см. раздел 13.

---

## 1. Главный сдвиг от v1

**v1 фокус:** «нагруженный pipeline + красивый UI».
**v2 фокус:** «измеримая точность + продуманный retrieval + lean stack».

Сигнал для рекрутёра / собеседующего создаётся:

1. **Ablation-таблицей в README** (см. `03_eval_methodology.md`) — публичные числа,
   которые нельзя получить «скопировав туториал».
2. **Schema retrieval recall как самостоятельной метрикой** — это инженерный
   subproblem, не «прикрутил RAG, посмотрел красивые проценты».
3. **Provider-bakeoff** на 30 вопросах между 3 моделями — превращает «почему Mistral»
   из вкусовщины в *измеримый trade-off*.
4. **Безопасным execution layer** на трёх уровнях, с явным error taxonomy.

Всё остальное (UI, observability, кэш, мульти-БД) — *поддержка*, не *суть*.

## 2. Системная диаграмма (lean)

```text
                        ┌─────────────────────────────────┐
                        │  Web UI (Streamlit или Next.js) │  ← решение в §8
                        │   ─ chat input                  │
                        │   ─ scalar/sentence/table/chart │
                        │   ─ show working                │
                        └────────────┬────────────────────┘
                                     │ HTTPS
                                     ▼
                  ┌──────────────────────────────────────┐
                  │  FastAPI gateway (rate-limit, CORS)  │
                  │  /ask, /databases, /eval/report      │
                  └────────────┬─────────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
       ▼                       ▼                       ▼
 ┌──────────────┐      ┌────────────────┐     ┌───────────────────┐
 │ LangGraph    │      │ Eval harness   │     │ Schema indexer    │
 │ NL→SQL graph │      │ (BIRD Mini-Dev)│     │ (offline pipeline)│
 │ 6 nodes      │      │ + ablation     │     └────────┬──────────┘
 └──────┬───────┘      └────────┬───────┘              │
        │                       │                      │
        ▼                       ▼                      ▼
 ┌─────────────────────────────────────────────────────────────┐
 │              Shared services layer (lean)                    │
 ├──────────────┬──────────────┬─────────────┬────────────────┤
 │ Provider     │ Chroma       │ Postgres /  │ in-memory       │
 │ adapter:     │ schema_chunks│ SQLite      │ LRU cache       │
 │ Mistral /    │ fewshot_qsql │ target DBs  │ (cachetools)    │
 │ frontier /   │              │             │ slowapi rate-lim│
 │ local        │              │             │                 │
 └──────────────┴──────────────┴─────────────┴────────────────┘
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  Langfuse traces only    │
                  └──────────────────────────┘
```

**Удалено vs v1:** Redis (отдельный сервис), Prometheus, OpenTelemetry,
backend history, multi-DB auto-switching как фича, Live `/eval` страница.

**Перенесено:** автогенерация Vega-spec из LLM → детерминированный chart picker.

## 3. LangGraph pipeline (6 узлов)

```text
       ┌─────────────────┐
       │ context_builder │   объединённый retrieve_schema + retrieve_examples
       └────────┬────────┘   + dialect adapter; единый context budget
                │            и единый trace
                ▼
       ┌─────────────────┐
       │ generate_sql    │   codestral-latest, structured output:
       └────────┬────────┘   { "sql": "...", "rationale": "...",
                │              "tables_used": [...], "confidence": 0..1 }
                ▼
       ┌─────────────────┐
       │ validate /      │   sqlglot AST guard (SELECT-only, no DML, whitelist)
       │ repair_once     │   FAIL → ОДИН repair с error-context → fail-fast
       └────────┬────────┘
                │
                ▼
       ┌─────────────────┐
       │ execute         │   read-only role, statement_timeout, LIMIT-cap
       └────────┬────────┘   no EXPLAIN-gate (см. §5)
                │
                ▼
       ┌─────────────────┐
       │ deterministic_  │   100% Python: shape result → scalar/sentence/table/chart
       │ format          │   chart type по heuristics, НЕ LLM
       └────────┬────────┘
                │
                ▼
       ┌─────────────────┐
       │ explain_trace   │   mistral-large-latest: NL caption (≤2 предложения)
       └─────────────────┘   + Langfuse span; persistence — middleware, не node
```

### Изменения от v1 (11 узлов → 6)

| Удалён узел | Почему |
|---|---|
| `classify_intent` | Эвристика по ключевым словам справится; LLM-call расточителен |
| `select_database` | UI даёт explicit DB, auto-select — optional, не часть графа |
| `retrieve_schema` + `retrieve_examples` (отдельные) | Объединены в `context_builder` с единым budget — упрощает trace и instrumentation |
| `static_validate` отдельно | Слит с `repair_once` (один retry-узел) |
| `explain_plan` | Brittle между БД, ломает легитимные тяжёлые запросы; перенесён в optional health-check внутри `execute` |
| `verify_result` retry | Empty result часто *корректен* (e.g. «есть ли заказы у клиента X?»). Retry → wrong-but-executable SQL. Заменено на graceful-degradation (показать результат + diagnostic) |
| `choose_format` отдельно | Детерминированно от result shape, не нужен граф-узел |
| `render_answer` | Слит с `explain_trace`: только NL-caption, рендер — на фронте |
| `persist_trace` | Middleware/span (Langfuse), не node |

### Что добавлено

- **dialect adapter** в `context_builder`: подмешивает Postgres/SQLite-specific
  hints в prompt (DATE_TRUNC vs strftime, JSONB vs JSON1, и т.д.).
- **schema-linking confidence** в structured output `generate_sql` — если
  `confidence < 0.5` или `tables_used` пересекается с retrieved schema <50%,
  поднять флаг для report (не для retry).
- **error taxonomy**: `NoRetrieval`, `InvalidSQL`, `ExecutionTimeout`,
  `EmptyResult`, `LowConfidence`, `RepairFailed` — фиксированное множество для метрик.

### Retry policy

- `validate` → ровно **один** repair pass с error-context. Если второй раз FAIL → fail-fast с diagnostic.
- `execute` syntax/runtime error → тот же repair pass (если ещё не использован).
- **Никаких retry на verify_result.** Empty / sparse result — это валидный исход,
  репортится как `EmptyResult` в error taxonomy.

## 4. Schema-RAG: 2 коллекции (вместо 4)

**Удалено:** `schema_columns` (отдельная коллекция), `relations` (FK через dense search — бесполезно).

**Оставлено:**

| Коллекция | Что в чанке |
|---|---|
| `schema_chunks` | Один чанк = одна таблица: имя + описание + полный список колонок (имена, типы, описания, top-5 sample values, NULL%, nunique) + список FK от/к этой таблице + 1-2 ключевых business-term hints |
| `fewshot_qsql` | Q→SQL пара: вопрос + аннотация интента (SQL не эмбеддится). **Только из train split** — никогда из dev/test (см. `03_eval_methodology.md` §5). |

**FK** хранятся как **deterministic catalog graph** (Python dict в памяти, обновляется при индексации) — после retrieve top-N таблиц делается graph traversal на FK для добавления связных таблиц до budget.

### Почему 2, а не 4

CX обоснование: dense retrieval на FK-связях `from.col → to.col` бесполезен — семантика связи не раскрывается user-вопросом, FK — это структурные метаданные.
KM обоснование: separate `schema_columns` добавляет multi-hop retrieval (table → columns → join) без доказанного прироста; начни с baseline, оптимизируй после ablation.

**Если ablation покажет (см. §6 03_eval_methodology), что 2-коллекционный baseline даёт ≥+5% schema recall@5 при отдельных колонках** — добавим как опцию, но не до измерения.

## 5. Безопасность execution: 3 уровня (без EXPLAIN-gate)

| Уровень | Что | Покрывает |
|---|---|---|
| **DB role** | Postgres user с `SELECT ONLY`, `default_transaction_read_only=on`, `temp_file_limit`, fixed `search_path` | DML, DDL, schema escalation |
| **AST guard (sqlglot)** | SELECT-only, no multi-statement, no DML in CTE, function allowlist (запрет `pg_sleep`, `pg_read_file`, `generate_series` свыше N, `ATTACH` для SQLite, extension load) | Function-level abuse, DoS via SELECT |
| **Runtime** | `statement_timeout=30s`, `idle_in_transaction_session_timeout=10s`, hard `LIMIT 10000` если в SQL нет агрегации, result payload cap 5MB | Long scans, huge payloads |

**Удалён EXPLAIN-gate** (cost > X). Brittle между БД, зависит от планировщика и stats, ломает легитимные тяжёлые аналитические запросы. Заменён на runtime `statement_timeout` (фактический предел) + result-payload cap.

### Acceptable-risk vectors (документированы, не закрыты)

Для read-only solo-demo:
- prompt injection через sample values (включаются в schema chunks из БД)
- `information_schema` / `pg_catalog` чтение (частично whitelist)
- recursive CTE с разумным timeout

Это не SaaS — для портфолио важно показать осознанные trade-off, не максимальную защиту.

## 6. LLM роутинг + provider abstraction

### Модели (переименованы из v1)

| Роль | Модель | Замечание |
|---|---|---|
| SQL generation + repair | `codestral-latest` (Codestral v25.08) | codestral-2501 был deprecated с ноября 2025 |
| NL caption / explain | `mistral-large-latest` | Только в `explain_trace`, не в pipeline |
| Embeddings | `mistral-embed` | Schema chunks + fewshot |
| Intent / format selection | **— (детерминировано Python)** | Ни одной LLM-call для этих задач |

### Provider abstraction (обязательно)

Слой `llm/providers/`:

```python
class LLMProvider(Protocol):
    def complete(self, prompt: str, schema: dict) -> SQLOutput: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def explain(self, sql: str, result: pd.DataFrame) -> str: ...
```

Реализации: `MistralProvider` (default), `OpenAIProvider`, `OllamaProvider`.
Конфиг — env var `LLM_PROVIDER=mistral|openai|ollama`.

### Bakeoff (артефакт портфолио) — конкретные модели, $0 budget

`eval/bakeoff/` содержит 30 курированных вопросов с эталонными SQL,
прогон через **3 фиксированных провайдера** (зафиксировано 2026-05-10).
**Жёсткое ограничение проекта: $0 external cost.** Только бесплатные тиры.

| Слот | Модель | Где | Стоимость 30 вопросов | Примечание |
|---|---|---|---|---|
| Code-specialized API | `codestral-latest` (Mistral v25.08) | La Plateforme free tier + диск-кэш | $0 (rate-limit-aware + caching) | Default provider |
| Frontier API | `gpt-4o-mini` (или `gpt-4.1-mini`) **через GitHub Models** | `models.inference.ai.azure.com` через GitHub Personal Access Token | $0 (free tier для personal GitHub аккаунтов) | См. §6.6 |
| Local code-specialized | `qwen2.5-coder:7b-instruct` (Ollama, default Q4_K_M ≈ 4.7 GB) | Локально через Ollama | $0 (электричество) | Подходит к 16 GB RAM (комфортный fit с запущенным Postgres+Chroma) |

**Сравнительная таблица в README** — это и есть ответ на «почему не GPT-4». Не идеологический, а измерительный.

**Backup для frontier slot** (если GitHub Models упрётся в daily rate limit или сервис будет недоступен):
- **Google Gemini 2.0 Flash** через Google AI Studio free tier (~1500 req/day, 15 RPM). Truly free, фронтир-class. Ключ создаётся в `aistudio.google.com`.
- Включается через тот же provider adapter, env var `LLM_FRONTIER_PROVIDER=gemini`.

**Опциональные расширения** (для опытов, не в default bakeoff):
- `qwen2.5-coder:14b-instruct` (9.0 GB) — лучше качество, но на 16 GB RAM **тесно**. Включается только при выключенных Postgres/Chroma во время локального прогона. Не годится для combined eval workflow на 16 GB.
- `qwen2.5-coder:32b-instruct` (20 GB) — **не помещается в 16 GB RAM**, не использовать.
- `sqlcoder-7b-2` (defog) — SQL-specialized альтернатива qwen2.5-coder; добавляется одной строкой в `config/providers.yml`. Полезно как secondary local point.

### 6.6 Frontier slot через GitHub Models (детали)

**GitHub Models** (`models.inference.ai.azure.com`) — Microsoft-managed бесплатный API-доступ к premium моделям для personal GitHub аккаунтов.

| Параметр | Значение |
|---|---|
| Endpoint | `https://models.inference.ai.azure.com/chat/completions` |
| Auth | GitHub Personal Access Token (без специальных scope, `read:user` достаточно) |
| Доступные модели (на 2026-05) | `gpt-4o-mini`, `gpt-4o`, `gpt-4.1-mini`, `o1-mini`, `claude-3-5-sonnet`, `meta-llama-3.1-405b-instruct`, и др. |
| SDK | OpenAI-compatible (`openai-python` с `base_url`), либо Azure AI Inference SDK |
| Rate limits | Daily quota per token + per-model RPM (точные числа меняются; на момент фиксации хватало для bakeoff с большим запасом) |

**Provider adapter implementation:**
```python
class GitHubModelsProvider(LLMProvider):
    def __init__(self):
        self.client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=os.getenv("GITHUB_TOKEN"),  # PAT
        )
        self.model = os.getenv("GH_MODELS_FRONTIER_MODEL", "gpt-4o-mini")
```

**Преимущество для портфолио:** anyone with a GitHub account может воспроизвести bakeoff бесплатно. Это сильнее «GPT-4 за $20» с точки зрения reproducibility.

**Когда переключаться на Gemini backup:** если GitHub Models показывает 429 или сервис недоступен — переключение через env var, без перезапуска кода. См. §11 risks.

## 6.5. Cost / quota strategy (no account rotation)

**Принципиальная позиция:** ротация Mistral free-tier аккаунтов **не делается**.

Причины:
1. Нарушение Mistral ToS; детекция по payment fingerprint + IP + browser fingerprint + email → бан всей цепочки и flagged email/card на будущее.
2. Negative signal в портфолио: на собеседовании honest-ответ «ротировал аккаунты» = disqualifier для Senior DE.
3. Premise неверный: с aggressive caching и rate-limit-aware throughput free tier покрывает весь dev-цикл.

### Стратегия экономии (вместо ротации)

| Слой | Механизм | Эффект |
|---|---|---|
| Generation cache | `diskcache` на ключ `(provider, model, prompt_hash)` → response | Каждый уникальный prompt идёт в API один раз; повтор тот же запрос → 0 latency, 0 quota. Покрывает повторные ablation-прогонки той же конфигурации. |
| Embedding cache | `diskcache` на `(model, text_hash)` → vector | Schema indexer и fewshot indexer переиндексируют без повторных API-вызовов. |
| CI smoke | `vcr.py` cassette в репо | 5-10 cached examples в CI, 0 live API calls, детерминированный CI. |
| Eval batch throttling | `tenacity` retry + `asyncio.Semaphore(N)` где N = 0.8 × free-tier RPS | Чтобы не упираться в rate-limit на массовом прогоне. |
| Daily quota check | Pre-flight `eval/check_quota.py` | Если приближаемся к daily limit — батч откладывается на следующий день. |

### Реальные цифры расхода

Расчёт для одного полного eval-прогона (BIRD Mini-Dev = 500 примеров, 5 ablation конфигураций):

```
Уникальных generation calls:
  - A (full_schema):  500 (схема одна на БД, prompt уникален per-вопрос)
  - B (BM25 cards):   500
  - C (Chroma cards): 500
  - D (+ fewshot):    500
  - E (+ repair):     500 + ~50-100 repair retries
Total uniq:          ~2600 generation calls

С diskcache при повторных прогонах:
  - Первый прогон конфигурации:  500 calls (full miss)
  - Повторный того же config:    0 calls (full hit)
  - Прогон новой конфигурации:   500 calls (промпт меняется → cache miss)

Embedding calls (one-time индексация):
  - Schema chunks для BIRD ~11 БД: ~200-400 chunks
  - Fewshot pool из BIRD train:    ~9k embeddings (one-time)
```

**Итог:** ~2600 generation + ~9.5k embedding **за весь dev-цикл**. На Mistral free tier с throttling = 1-2 ночные batch-сессии. После cache warm-up любой повторный ablation-прогон = 0 API calls.

### Bakeoff cost (one-time)

30 questions × 3 providers × ~3 000 tokens (prompt+completion, average) ≈ 270 K tokens total.
- Mistral: covered by free tier (La Plateforme).
- Frontier slot via **GitHub Models** (`gpt-4o-mini`): covered by free tier (personal GitHub PAT).
- Local Ollama: $0 (электричество).

Итого external cost проекта: **$0** за весь жизненный цикл portfolio-демо. Это hard constraint.

---

## 7. Целевые БД (реранжированы)

| База | Размер | Роль |
|---|---|---|
| **BIRD Mini-Dev** | 500 Q→SQL, ~11 БД | **Primary eval** — публичный leaderboard, ablation matrix |
| **StackExchange (curated mini)** | gaming.stackexchange.com OR SO 2023-2024 trimmed (~2-5 GB) | **Real-world demo** — 20-30 курированных gold questions с manual review |
| **Chinook** | <10MB | Только smoke / sanity check, не «портфолио-сигнал» |

### Изменения от v1

- BIRD: было «mini, ~1500 Q-SQL, 11 БД» → факт **500 Q-SQL** (см. `WebFetch` подтверждение от bird-bench.github.io).
- StackExchange: «full dump» → curated mini c явным набором gold-вопросов. Full dump = неделя ETL, не нужно.
- Chinook понижен до smoke-only.

### Optional альтернатива (если хочется «вау»)

DuckDB + Parquet с публичным датасетом (HN dump / GH Archive / NYC Taxi) — современный аналитический стек, сильнее сигнал «в тренде DE». Решение откладываем до недели 2; сейчас baseline = Postgres+SQLite.

## 8. UI (узкое решение)

**Решение:** Streamlit для v1 demo, Next.js — *opt-in* если останется неделя в roadmap.

Обоснование:
- Цель проекта = NL→SQL и eval, не frontend.
- Streamlit за 2-3 дня даёт chat + DB switcher + table/chart/scalar/sentence + show-working.
- Next.js — неделя, и сигнал об этом — *frontend skill*, не *DE*.
- Если хочешь именно fullstack-сигнал — Next.js включается на неделе 7+, после того как eval-цифра достигнута.

UI обязан показывать:
- сам ответ (один из 4 форматов),
- SQL с подсветкой и copy-кнопкой,
- блок «show working»: retrieved schema chunks, few-shot, rationale, time, model used,
- error taxonomy при failure: какой именно узел упал.

**Charts:** детерминированный picker на фронте (Plotly или ApexCharts), НИКАКИХ Vega-Lite спек от LLM.

```python
def pick_chart(df: pd.DataFrame, intent_hint: str) -> ChartSpec:
    if df.shape == (1, 1): return ScalarSpec(value=df.iat[0, 0])
    if len(df) > 50:        return TableSpec()
    if has_temporal(df):    return LineSpec(x=temporal_col, y=numeric_cols)
    if 2 <= len(df) <= 12 and is_categorical(df.iloc[:, 0]):
                            return BarSpec(...)
    return TableSpec()
```

LLM генерирует только `intent_hint` (одно слово из enum) + caption.

## 9. Eval — vendored из 03_eval_methodology.md

Полностью описан в `03_eval_methodology.md`. Краткая сводка:

- **Целевые метрики:** Execution Accuracy (primary), Schema Recall@k, SQL Validity Rate, Repair Success Rate, Latency P50/P95, Cost-per-query.
- **Ablation matrix** (5 точек): `full_schema → BM25 cards → Chroma cards → +fewshot → +repair`.
- **Slicing:** by difficulty (BIRD provides), by dialect, by join count, by aggregation type.
- **Train/dev hygiene:** few-shot pool ТОЛЬКО из train; dev запрещён к использованию в few-shot.
- **CI:** unit tests + 5-10 кэшированных smoke-примеров (vcr.py / diskcache). НЕ live API.
- **Nightly/manual:** полный 50/100/500-example прогон с отчётом.
- **Hard checkpoint неделя 3:** EA <35% → scope down (см. roadmap §11).

## 10. Стек (lean)

| Слой | Технология | Замечание |
|---|---|---|
| LLM API | Mistral + OpenAI + Ollama (через provider adapter) | Bakeoff артефакт |
| Orchestration | LangGraph | Тот же что в RAG_SA |
| API | FastAPI + Pydantic v2 | Standard |
| Vector DB | Chroma | 2 коллекции |
| SQL parser | sqlglot | AST guard, dialect translation |
| Target DB | Postgres 16 + SQLite | StackExchange + BIRD/Chinook |
| Cache | `cachetools.LRUCache` (in-memory) + `slowapi` (rate-limit) + `diskcache` для LLM API replay | **БЕЗ Redis** |
| Charting | Plotly + heuristics picker | **БЕЗ Vega-Lite от LLM** |
| Frontend | Streamlit (v1) → Next.js (opt-in) | См. §8 |
| Observability | Langfuse only | **БЕЗ Prometheus + OTel** |
| Eval cache | vcr.py / diskcache | Для CI smoke |
| Tests | pytest + httpx + testcontainers (Postgres) | Без mock в integration tests |
| Lint/Type | ruff + mypy strict (api/, agent/, llm/) | Как в DE_project |
| CI | GitHub Actions | Unit + 5-10 cached smoke + lint |
| Deploy | docker-compose (dev) + single Dockerfile | StackExchange dump в named volume |

## 11. Roadmap (8-10 недель — реалистично)

| # | Этап | Длительность | DoD |
|---|---|---|---|
| 1 | Bootstrap + provider adapter | 0.5 нед | FastAPI hello, Mistral/OpenAI/Ollama providers, тесты на adapter с моком |
| 2 | Target DBs ready | 0.5 нед | Postgres+StackExchange-mini, SQLite+Chinook, BIRD Mini-Dev в `data/` |
| 3 | Schema indexer (2 collections) | 0.5-1 нед | Offline скрипт строит Chroma; smoke-test schema recall@5 |
| 4 | Pipeline v1 (6 узлов) | 1 нед | Граф работает на Chinook + BIRD subset, single-shot |
| 5 | Guards + repair_once | 0.5 нед | sqlglot AST + 3-уровневая защита + error taxonomy |
| 6 | Eval harness + first ablation | 1.5-2 нед | Runner, EA метрика, baseline ablation 5 точек, schema recall |
| 7 | **Hard checkpoint** | gate | EA ≥35% on BIRD Mini-Dev → continue; <35% → scope down (см. §12) |
| 8 | Tuning loop (retrieval + few-shot + prompts) | 2-3 нед | Итеративный — где будет основная боль |
| 9 | Multi-format render + chart picker | 0.5 нед | Heuristics-based, Plotly templates, 4 формата |
| 10 | UI (Streamlit) | 0.5 нед | chat + DB switcher + show-working + history (localStorage) |
| 11 | Bakeoff (3 providers × 30 questions) | 0.5 нед | Сравнительная таблица в README |
| 12 | Polish + deploy + README + demo video | 1 нед | docker-compose, README c ablation+bakeoff, видео 3 мин |

**Итого:** 8.5-11 недель в спокойном темпе или 5-6 в плотном (с риском burnout, см. §13).

## 12. Scope-down protocol (если EA <35% на неделе 3)

Если eval упирается:

1. **Drop BIRD as primary metric** — оставить только StackExchange-mini c 20-30 курированными вопросами + manual review accuracy.
2. **Cut bakeoff** — оставить только Mistral.
3. **Cut Next.js даже если был план** — Streamlit-only.
4. **Сместить фокус** в README с «BIRD execution accuracy» на «безопасное execution + schema retrieval» как core competency.

Это не «провал» — это honest scoping. Senior DE сигнал даёт *показ зрелости в принятии решений*, не «достиг 50% любой ценой».

## 13. Риски (расширенный список после CX/KM)

| Риск | Вероятность | Митигация |
|---|---|---|
| Schema retrieval recall <60% | **высокая** (главный риск accuracy) | Ablation matrix покажет рано; компенсация — расширенные table cards, schema linking узел |
| LLM context overflow на широких БД | средняя | Hard limit retrieved tables + table card compression |
| Benchmark leakage (dev → few-shot) | высокая если не следить | Hard split в indexer: few-shot pool строится **только** из train, тесты на pollution |
| Business semantics gap («active user», «top», «growth») | высокая | Mini-glossary в schema_chunks (1-2 business-term hints на таблицу), документировано в `03_eval_methodology` §7 |
| codestral-latest версия меняется (alias drift) | средняя | Pin конкретный snapshot в bakeoff отчёте, alias — для prod-default |
| Repair-loop делает wrong-but-executable SQL | средняя | Один repair max + confidence flag; metrics: repair success rate vs first-pass accuracy |
| StackExchange ETL — неделя | высокая | Curated mini вместо full dump; gaming.stackexchange как fallback |
| Vega-spec ломается | **N/A в v2** | Удалено |
| Mistral API rate limits на eval | средняя | diskcache на (prompt_hash → response); throttle до 0.8×free-tier RPS; nightly батчем. **Ротация аккаунтов запрещена** (см. §6.5) |
| Local model RAM exhaustion (16 GB OS) | средняя | qwen2.5-coder:7b (4.7 GB) как default; 14b опциально только при выключенных Postgres/Chroma; 32b исключён |
| GitHub Models rate-limit hit на bakeoff | низкая | 30 вопросов под daily limit с большим запасом; backup — Gemini 2.0 Flash через `LLM_FRONTIER_PROVIDER=gemini` (см. §6.6) |
| GitHub Models меняет model availability | низкая-средняя | provider adapter изолирует; смена модели — env var; bakeoff фиксирует snapshot в отчёте |
| Burnout / scope creep | **средняя-высокая** | Hard checkpoint неделя 3; scope-down protocol §12 |

## 14. Что в этой архитектуре «нагруженного» (vs «фейковая нагрузка»)

«Нагруженно, но не фейк» (даёт сигнал):
- LangGraph 6 узлов с error taxonomy + repair loop
- Schema-RAG 2 коллекции с FK graph + dialect adapter
- 3-уровневая защита SQL execution
- Eval harness c ablation matrix + slicing + leakage prevention
- Provider adapter + 30-question bakeoff
- Schema recall@k как самостоятельная метрика

«Фейковая нагрузка для solo-demo» (вырезано в v2):
- Prometheus + OpenTelemetry (Langfuse достаточно)
- Redis (cachetools хватает)
- 4 коллекции Chroma вместо 2
- Vega-Lite spec generation от LLM
- 11-узловой граф с тремя retry-точками
- EXPLAIN-gate
- Backend history + bookmarks
- Multi-DB auto-switching как фича
- Live `/eval` page
- testcontainers everywhere

## 15. Карта решений: какая правка откуда

| v2 решение | Источник | Confidence |
|---|---|---|
| Pipeline 11 → 6 узлов | CX + KM convergent | high |
| Schema-RAG 4 → 2 коллекции | CX + KM convergent | high |
| Drop EXPLAIN-gate | CX + KM convergent | high |
| Drop Prom + OTel + Redis | CX + KM convergent | high |
| Vega-Lite от LLM → детерминированный picker | CX + KM convergent | high |
| Mistral-only → provider adapter + bakeoff | CX + KM convergent | high |
| BIRD Mini-Dev = 500 (factual fix) | CX (verified WebFetch) | factual |
| codestral-2501 → codestral-latest | CX (verified WebFetch) | factual |
| Eval target 50% → 35-40% baseline / 50% stretch | CX (BIRD Mini-Dev leaderboard numbers: GPT-4 = 47.8/40.8/35.8% EX) | high |
| Ablation matrix как central artifact | CX | high |
| Hard checkpoint неделя 3 + scope-down protocol | KM | medium-high |
| Streamlit вместо Next.js (default) | CX + KM | medium |
| Business semantics mini-glossary | CX | medium |
| Benchmark leakage prevention | CX | high |
| Roadmap 5-6 → 8-10 недель | CX + KM convergent | high |
| DuckDB + Parquet альтернатива | KM (optional) | low (на будущее) |
