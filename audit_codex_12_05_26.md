# NL_SQL - полный аудит проекта

Дата аудита: 12.05.2026  
Аудитор: Codex  
Проект: `D:\NL_SQL`  
HEAD на старте: `ba68c68`  

## 1. Baseline и методика

Локальный baseline перед аудитом:

| Метрика | Значение |
|---|---:|
| Bundle assets | 0 B |
| i18n leaf keys | 0 |
| Tracked files | 181 |
| Git HEAD | `ba68c68` |
| Chroma `schema_chunks` | 86 |
| Chroma `fewshot_qsql` | 9428 |
| Локальные данные `data/` | 102 файла, ~4.34 GB |
| `chroma_data/` | 14 файлов, ~58 MB |
| LLM cache `.cache/llm` | 6 файлов, ~99 MB |

Рабочее дерево уже было грязным до записи аудита: изменены бинарные файлы `chroma_data/*`, `eval/reports/2026-05-11/index.html`, есть новый JSON-отчет `G_dense_fewshot_verify_retry-sonnet-moderate.json`. Я их не менял намеренно.

Проверки:

| Проверка | Результат |
|---|---|
| `uv run ruff check src tests scripts app` | passed |
| `uv run mypy src` | passed, 52 source files |
| `uv run pytest` | первый запуск упал из-за `PermissionError` к `C:\Users\uedom\AppData\Local\Temp\pytest-of-uedom` |
| `TMP/TEMP=D:\NL_SQL\.tmp\pytest-codex-audit; uv run pytest` | 230 passed, 1 warning |
| `uv run pytest --cov=src/nl_sql --cov-report=term-missing` | 230 passed, coverage 94%, 1 warning |
| `uv pip list --outdated` | есть мелкие обновления, критичного отставания не видно |
| Streamlit локально на `http://localhost:8501` | UI загрузился, sample-flow отработал |
| Playwright browser check | консоль: 0 errors, 0 warnings |

Скриншоты визуального аудита сохранены в `D:\.playwright-mcp\`: `nl_sql_desktop_top.png`, `nl_sql_mobile_top.png`, `nl_sql_mobile_answer.png`, `nl_sql_desktop_answer.png`, `nl_sql_desktop_expander.png`.

## 2. Executive Summary

NL_SQL выглядит как сильный portfolio/research проект по NL-to-SQL, а не как очередной "чат к базе". Самая сильная часть - измеримый engineering loop: BIRD Mini-Dev, Chinook demo benchmark, ablations, schema recall, first-pass/final EA, cache для воспроизводимых LLM-прогонов, provider bakeoff. Это дает реальный senior-level сигнал.

Главный продуктовый вывод: проект уже убедителен как демо инженерной зрелости, но пока не готов как self-service BI-продукт. Основной пользовательский продукт - Streamlit UI, а FastAPI пока содержит только `/healthz`. Публичный Streamlit Cloud deploy в документации отмечен как заблокированный OAuth/login, поэтому "live demo" фактически не завершен.

Главный технический вывод: стек современный и хорошо подобран. Python 3.13, uv, Pydantic v2, FastAPI, LangGraph, ChromaDB, sqlglot, diskcache, ruff, mypy strict, pytest и coverage 94% - все это актуально и инженерно оправдано. Есть сильная дисциплина тестов и eval-артефактов.

Главный визуальный вывод: UI функциональный, но визуально скорее "исследовательская Streamlit-панель", чем polished portfolio demo. Он умеет главное: DB switcher, sample questions, SQL, scalar/table/chart rendering, show-working. Но есть сырость: технические knob labels, raw dict trace, смешение RU/EN, длинный SQL не адаптирован к mobile, Streamlit auto-scroll может скрыть hero при первом открытии.

Общая оценка:

| Область | Оценка | Комментарий |
|---|---:|---|
| Продуктовая идея | 8.5/10 | Сильное позиционирование через измеримую точность и безопасность |
| Исследовательская ценность | 9/10 | Реальные ablations и отчеты, не игрушечные метрики |
| Backend/ML implementation | 8.5/10 | Современно, тестируемо, хорошо декомпозировано |
| API product readiness | 4/10 | FastAPI пока health-only |
| Visual/UI polish | 5.5/10 | Рабочий Streamlit, но мало продуктовой отделки |
| Современность технологий | 8.5/10 | Стек свежий; минусы - Streamlit как UI-компромисс и широкие dependency ranges |
| Production readiness | 6/10 | Для портфолио хорошо; для продукта нужны auth, API, deploy, observability, docs sync |

## 3. Продуктовый аудит

### 3.1 Что продукт делает

Проект принимает вопрос на естественном языке, строит SQL, валидирует его, исполняет read-only запрос к SQLite/Postgres-целям и возвращает ответ в одном из форматов: scalar, sentence, table, chart. Всегда показывает SQL, rationale и trace.

Ключевые подтвержденные продуктовые метрики:

| Workload | Результат |
|---|---:|
| Chinook demo benchmark | 60/60, 100% EA |
| Chinook split | dev 30/30, held-out 30/30 |
| Chinook categories | 10/10 категорий на 100% |
| BIRD A full schema, codestral | 47.0% EA, n=200 |
| BIRD C dense cards, Sonnet via Perplexity | 51.0% EA, n=200 |
| BIRD D fewshot, codestral | 55.5% EA, n=200 |
| BIRD G verify-retry, codestral | 56.5% EA, n=200 |
| BIRD hybrid G codestral + Sonnet challenging | 57.0% EA, n=200 |

По продуктовой истории это сильная конструкция:

- Chinook = "показываем надежный пользовательский сценарий".
- BIRD = "показываем research difficulty и честные пределы".
- Ablation = "показываем, какие компоненты реально дают lift".
- Provider abstraction = "показываем, что модель можно менять без переписывания pipeline".
- $0 budget = "показываем cost discipline".

### 3.2 Чем проект отличается от generic NL-to-SQL

Сильные отличия:

- Есть публичная метрика Execution Accuracy, а не ручное "работает на моем примере".
- Есть schema retrieval recall как отдельный диагностический слой.
- Есть first-pass vs final EA, repair success rate, empty-result rate, latency P50/P95, token metrics.
- Есть hard split hygiene: few-shot pool строится из BIRD train, не из dev.
- SQL execution защищен не промптом, а AST guard + read-only engine + runtime caps.
- Chart selection детерминированный, а не LLM-generated Vega/Plotly specs.

Это отличает проект от tutorial-level LangChain SQL agent.

### 3.3 Где продуктовая история пока слабая

1. README и UI не догнали свежий headline.
   - README говорит про 100% Chinook и 51.0% BIRD Sonnet/codestral, но свежий handoff и JSON-артефакт показывают 57.0% hybrid.
   - UI welcome card показывает 50.0%/51.0%, но не показывает текущий 57.0% hybrid.

2. "Live demo" фактически не закрыт.
   - README содержит Streamlit Cloud URL, но сам README говорит, что он редиректит на OAuth/login.
   - `docs/SESSION_HANDOFF.md` прямо говорит: Streamlit Cloud app NOT yet deployed, OAuth login required.

3. Product UI не использует лучший pipeline.
   - В `app/streamlit_app.py` pipeline создается с `fewshot_top_k=0` и комментарием `config D not yet shipped`.
   - При этом `src/nl_sql/eval/runner.py` уже содержит `run_config_d` и `run_config_g`, а Chroma содержит 9428 few-shot примеров.
   - Итог: demo UI показывает не лучший исследовательский результат.

4. Пользовательская ценность для реального analyst persona пока узкая.
   - Нет сохраненных dashboards/bookmarks.
   - Нет данных о freshness/source lineage кроме source link.
   - Нет персистентной истории вне `st.session_state`.
   - Нет понятного "confidence explanation" для бизнес-пользователя.

5. Продуктовая терминология смешана.
   - UI и docs смешивают русский и английский.
   - Для портфолио это терпимо, но для внешнего демо лучше выбрать один primary language и оставить второй как поддерживаемый input.

## 4. Технический аудит

### 4.1 Архитектура

Текущая архитектура в целом соответствует `docs/02_architecture_v2.md`:

- LangGraph pipeline: `context_builder -> generate_sql -> validate/repair_once -> execute -> deterministic_format -> explain_trace`.
- ChromaDB: две коллекции, `schema_chunks` и `fewshot_qsql`.
- Provider abstraction: Mistral, GitHub Models, Groq, Ollama, Perplexity browser bridge.
- Execution safety: `sqlglot` AST guard, read-only DB connection, timeout, row cap.
- Eval harness: A/C/D/E/F/G configurations, JSON/HTML reports.
- UI: Streamlit v1, Next.js отложен как opt-in.

Это хорошая lean-архитектура: нет лишнего Redis/Prometheus/OTel, которые были бы фейковой нагрузкой для solo portfolio demo.

### 4.2 Стек и современность

Фактические версии в окружении:

| Компонент | Версия |
|---|---:|
| Python | 3.13.7 |
| FastAPI | 0.136.1 |
| Pydantic | 2.13.4 |
| sqlglot | 30.7.0 |
| LangGraph | 1.1.10 |
| ChromaDB | 1.5.9 |
| Streamlit | 1.57.0 |
| Plotly | 6.7.0 |
| pandas | 3.0.2 |
| ruff | 0.15.12 |
| mypy | 2.0.0 |
| pytest | 9.0.3 |

Вывод: технологии современные. Особенно сильные решения:

- `uv` вместо pip/poetry как быстрый dependency manager.
- Python 3.13 и строгий mypy.
- Pydantic v2 и FastAPI.
- LangGraph для управляемого graph pipeline.
- `sqlglot` для AST-level SQL guard.
- ChromaDB для локального vector store.
- `diskcache` для воспроизводимости LLM eval.
- Plotly + deterministic chart picker вместо LLM-generated chart specs.

Слабые места современности:

- `pyproject.toml` и `requirements.txt` используют широкие `>=`, а не pinned versions. Для локального `uv.lock` это ок, но Streamlit Cloud читает `requirements.txt` и может получить future drift.
- CI не запускает `ruff check scripts app`, хотя Makefile это делает. В аудите `scripts app` проходят, но CI покрывает только `src tests`.
- Streamlit как frontend - прагматично, но визуально и архитектурно уступает современному React/Next.js UI. Для DE portfolio это допустимый компромисс, для full-stack продукта - нет.
- Provider typing слегка расходится: `ProviderName` в settings не включает `perplexity`, хотя factory и CLI его поддерживают.

### 4.3 Качество кода

Сильные стороны:

- Хорошая модульность: `agent`, `db`, `execution`, `eval`, `llm`, `render`, `schema_index`.
- Runtime dependencies инжектятся через `PipelineConfig`, тесты легко подставляют fakes.
- SQL safety вынесена отдельно и тестируется.
- Eval runner хранит достаточно информации для анализа ошибок.
- Caching wrapper аккуратно отделяет live API latency от cache hits.
- `render` слой не зависит от LLM.

Слабые стороны:

- `src/nl_sql/eval/runner.py` верхним docstring все еще говорит, что B-E не реализованы, хотя C/D/E/F/G уже есть. Это вводит в заблуждение.
- `run_config_b` все еще `NotImplementedError`, хотя методология обещает BM25 step в ablation matrix.
- `scripts/build_index.py` default `--sample-size` равен 5, а runtime `PipelineConfig.primary_sample_size` и UI используют 3. В handoff это уже признано как footgun.
- Streamlit UI содержит много product copy и HTML прямо в `app/streamlit_app.py`; для текущего размера терпимо, но файл уже стал смешением bootstrap, rendering, content, sample questions и UX logic.
- Show-working выводит raw Python dicts. Для debug хорошо, для portfolio demo выглядит сыро.

### 4.4 Безопасность

Сильные стороны:

- SQLite открывается через `mode=ro` и `PRAGMA query_only=ON`.
- Postgres path включает `default_transaction_read_only=on`.
- AST guard запрещает DML/DDL/multi-statement, опасные функции, `ATTACH`, `PRAGMA`, часть системных таблиц.
- Runtime layer добавляет timeout и row cap.
- `.env` игнорируется, `.env.example` не содержит секретов.

Остаточные риски:

- Нет полноценной table/column allowlist validation до execution. Missing table/column ловится уже на execution.
- Prompt injection через sample values явно принят как acceptable risk в документах, но UI не объясняет это пользователю.
- Public demo без auth/rate limiting может быстро упереться в Mistral quota, если станет реально публичным.
- `docker-compose.yml` содержит default dev secrets для Langfuse/Postgres. Это нормально для dev, но нельзя выдавать как prod-ready.

### 4.5 API

FastAPI сейчас содержит только:

- `/healthz`
- `/docs`
- `/openapi.json`
- `/redoc`

Нет `/ask`, `/databases`, `/eval/report`, хотя они описаны в архитектуре. Поэтому backend API пока не является продуктовым API. Он годится как bootstrap и health surface, но реальный продуктовый путь идет напрямую через Streamlit.

### 4.6 Eval и ML pipeline

Это самая сильная часть проекта.

Подтверждено кодом и артефактами:

- `eval/reports/2026-05-11/demo-v8-n60.json`: 60/60 Chinook.
- `eval/reports/2026-05-11/D_dense_fewshot-bird-train-fewshot.json`: 55.5% BIRD.
- `eval/reports/2026-05-11/G_dense_fewshot_verify_retry-verify-retry.json`: 56.5% BIRD.
- `eval/reports/2026-05-11/G_dense_fewshot_verify_retry-hybrid-codestral-sonnet.json`: 57.0% BIRD.
- Chroma `fewshot_qsql`: 9428 examples.

Хорошая инженерная практика:

- `first_pass_ea` отделена от final EA.
- Repair success rate измеряется отдельно.
- Empty result rate измеряется отдельно.
- Schema recall измеряется отдельно.
- Hybrid merge вынесен в отдельный script.
- Все отчеты воспроизводимы как JSON и HTML.

Главный пробел:

- Methodology все еще описывает 5-step A-E matrix с BM25, но фактический сильный путь уже A/C/D/G/hybrid. Нужно переписать reporting narrative под фактический pipeline либо реализовать B.

## 5. Визуальный аудит

### 5.1 Что проверено

Запущено:

```powershell
uv run streamlit run app/streamlit_app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
```

Проверено в Playwright:

- Desktop `1280x720`.
- Mobile `390x844`.
- Initial load.
- Manual scroll top.
- Sample question click.
- Answer rendering.
- SQL block.
- Show-working expander.
- Browser console warnings/errors.

Sample-flow:

- Вопрос: "How many schools with an average score in Math greater than 400 in the SAT test are exclusively virtual?"
- Ответ: scalar `4`.
- Caption: "The query found 4 schools..."
- SQL показан.
- Wall: 3120 ms.
- Model: `codestral-latest`.
- Console: 0 errors, 0 warnings.

### 5.2 Сильные стороны UI

- Первый экран при ручном top-scroll ясно показывает название, позиционирование и метрику 60/60.
- Есть DB switcher.
- Есть source link на BIRD/Chinook.
- Есть schema explorer.
- Есть retrieval knobs, полезные для технического демо.
- Sample questions ускоряют первое впечатление.
- Ответ показывает scalar, caption, SQL, latency и модель.
- Show-working доступен в expander.
- Mobile layout в целом не ломается, sample cards становятся вертикальными.

### 5.3 Визуальные и UX-проблемы

1. Streamlit auto-scroll.
   - После загрузки основной контейнер был автоматически проскроллен к chat input (`scrollTop=311` на desktop), из-за чего heading и intro оказались выше viewport.
   - При ручном `scrollTop=0` экран выглядит нормально, но первый автоматический вид может быть хуже.

2. UI выглядит как Streamlit dashboard, не как polished product.
   - Много дефолтных Streamlit элементов.
   - Цвета и типографика почти не имеют собственной визуальной системы.
   - Иконки chat messages дефолтные и выглядят случайно.

3. Слишком технический sidebar для demo user.
   - `schema_top_k`, `fk_hops`, `table_budget`, `sort_schema_block`, `extended_sample_size` понятны автору/интервьюеру, но не бизнес-пользователю.
   - Для внешнего демо лучше режимы: "Fast", "Accurate", "Debug", а raw knobs спрятать в Advanced.

4. Show-working сырой.
   - Trace выводится как raw dict: `{'model': ..., 'confidence': ..., 'input_tokens': ...}`.
   - Для портфолио лучше таблица node/status/latency/tokens плюс collapsible raw JSON.

5. SQL block на mobile горизонтально обрезается.
   - `st.code` дает горизонтальный scroll. Это приемлемо для кода, но на mobile выглядит как обрезанный текст.
   - Нужна copy-кнопка и, возможно, отдельный "Open SQL" expander.

6. Смешение языков.
   - Заголовки и метрики на английском, input placeholder на русском, expander смешанный: "Показать работу (schema, SQL, latency, errors)".
   - Лучше выбрать primary language для demo и локализовать вторую версию отдельно.

7. Metric label для scalar слишком технический.
   - В sample-flow label был `COUNT(DISTINCT s.CDSCode)`.
   - Для пользователя лучше label "Schools" или "Result"; SQL expression оставить в details.

8. Hero card переполнен по высоте на desktop 720.
   - На desktop top screenshot правый metric card частично уходит ниже видимой зоны, chat input фиксирован снизу.
   - Нужно больше vertical rhythm или compact metric summary.

## 6. Документация

Сильные стороны:

- README хорошо объясняет value proposition.
- `docs/02_architecture_v2.md` качественно фиксирует архитектурные trade-offs.
- `docs/03_eval_methodology.md` дает зрелую методологию evaluation.
- `docs/SESSION_HANDOFF.md` содержит богатый audit trail экспериментов.
- DEPLOY описывает Streamlit Cloud путь и ограничения.

Проблемы:

- README устарел по тестам: указано 216 tests, фактически 230 tests.
- README и UI не отражают свежий 57.0% hybrid headline.
- Handoff содержит взаимоисключающие исторические блоки: в начале fewshot готов и дает 55.5%, ниже есть старые секции "fewshot_qsql collection has zero records" и "config D blocked".
- `docs/03_eval_methodology.md` все еще содержит `XX.X%` placeholders в reporting section.
- `DEPLOY.md` говорит, что `chroma_data/` около 3 MB, фактически текущий `chroma_data/` около 58 MB.
- `src/nl_sql/eval/runner.py` docstring устарел относительно реализации.

Документация качественная, но сейчас требует синхронизации после быстрого research loop.

## 7. CI, тесты и качество gates

Сильные стороны:

- 230 тестов проходят.
- Coverage 94%.
- Ruff clean.
- Mypy strict clean.
- CI использует uv, Python 3.13, ruff format check, mypy, pytest with coverage.

Недочеты:

- CI `ruff check` проверяет только `src tests`, а локальный Makefile lint проверяет `src tests scripts app`.
- CI не запускает Streamlit smoke.
- CI не проверяет, что README headline metrics соответствуют latest JSON reports.
- CI не проверяет, что `build_index.py --sample-size` согласован с `PipelineConfig.primary_sample_size`.
- Первый локальный pytest без TMP override упал на Windows temp permission. Это окруженческая проблема, но ее стоит учесть в Windows docs.

## 8. Современность технологий

Оценка: высокая.

Что современно и уместно:

- Python 3.13 и uv.
- FastAPI + Pydantic v2.
- LangGraph вместо ad-hoc retry chain.
- ChromaDB для локального vector store.
- `sqlglot` AST validation.
- Provider abstraction под Mistral/Groq/GitHub/Ollama/Perplexity.
- Disk-backed LLM cache.
- pytest + respx + strict mypy + ruff.
- Plotly deterministic rendering.
- JSON/HTML eval reports.

Что не является "latest shiny", но оправдано:

- Streamlit вместо Next.js. Для DE portfolio это рациональный компромисс: быстрее показать NL-to-SQL и eval. Для продукта с большим UX-сигналом надо переходить на React/Next.js или хотя бы сильно кастомизировать Streamlit.
- ChromaDB committed в репозиторий. Это не идеально для чистоты repo, но прагматично для cold-start demo без embedding quota burn.
- Langfuse в docker-compose, но не полноценный observability stack. Для solo demo это правильный scope cut.

Что стоит модернизировать:

- Зафиксировать Streamlit Cloud dependencies точнее, не только `>=`.
- Перевести product API из health-only в настоящий `/ask`.
- Добавить lightweight Playwright/Streamlit smoke test.
- Добавить doc-sync checks для metrics.

## 9. Приоритетные риски

| Риск | Severity | Почему важно |
|---|---:|---|
| UI не использует fewshot/G best pipeline | High | Демонстрация показывает слабее, чем research artefacts |
| Public demo не завершен | High | Portfolio value падает без кликабельного live demo |
| README/UI устарели относительно 57% hybrid | High | Сильнейший результат спрятан в handoff/JSON |
| FastAPI только `/healthz` | Medium | Архитектура говорит API gateway, но продукта API нет |
| `sample-size` mismatch | Medium | Легко случайно перестроить Chroma не тем density |
| BM25 config B отсутствует | Medium | Методология обещает полную A-E ablation, но один baseline missing |
| Raw Streamlit visual polish | Medium | Для recruiter demo выглядит менее premium, чем engineering внутри |
| CI не lint-ит app/scripts | Medium | UI/scripts могут сломаться вне CI |
| Wide dependency ranges в deploy path | Medium | Streamlit Cloud может получить неожиданный future break |
| Dirty binary artefacts in worktree | Medium | Перед commit/push нужен строгий status gate |

## 10. Рекомендации

### P0 - перед публичным показом

1. Обновить README и UI headline:
   - Chinook: 60/60.
   - BIRD: 57.0% hybrid G.
   - Указать D/G lift: D 55.5%, G 56.5%, hybrid 57.0%.

2. Включить fewshot/G в Streamlit UI или явно назвать UI "fast demo mode".
   - Сейчас `fewshot_top_k=0`, хотя лучший pipeline зависит от fewshot.
   - Минимум: добавить toggle `Use few-shot + verify retry`.

3. Завершить Streamlit Cloud deploy.
   - README не должен вести на OAuth/login или полуживой URL.

4. Синхронизировать docs:
   - Удалить старые "D blocked" / "fewshot zero records" из актуальной части handoff.
   - Обновить тестовые числа: 230 tests, coverage 94%.
   - Обновить `DEPLOY.md` размер `chroma_data`.

5. Перед любым commit/push разобраться с dirty `chroma_data` и eval reports.
   - Не делать `git add -A`.
   - Добавлять только явно нужные файлы.

### P1 - техническая зрелость

1. Реализовать или удалить из методологии BM25 config B.
   - Сейчас A/C/D/G сильнее фактической истории, чем незакрытая A-E схема.

2. Добавить `/ask` и `/databases` в FastAPI.
   - Даже если UI остается Streamlit, API surface нужен для архитектурной честности.

3. Синхронизировать `build_index.py --sample-size` default с runtime.
   - Если production candidate s=3, default должен быть 3.

4. Расширить CI:
   - `uv run ruff check src tests scripts app`
   - `uv run ruff format --check src tests scripts app`
   - Streamlit import/smoke.
   - Metrics/doc consistency script.

5. Pin deploy dependencies.
   - Для Streamlit Cloud либо генерировать pinned `requirements.txt`, либо документировать, что deploy intentionally tracks latest compatible.

### P2 - визуальная и продуктовая отделка

1. Спрятать retrieval knobs в Advanced.
2. Переписать show-working как таблицу trace, не raw dict.
3. Сделать language mode: EN primary или RU primary.
4. Добавить copy SQL button.
5. Для scalar label использовать business label, не SQL expression.
6. Исправить initial auto-scroll/hero visibility.
7. Сделать compact metric strip вместо высокого metric card.
8. Добавить "Run example" path, который гарантированно cache-hit и объясняет, почему быстрый.

## 11. Итоговая оценка

NL_SQL технически сильный и современный. Самое ценное в нем - не UI и не сам факт генерации SQL, а дисциплина измерения: eval harness, ablation thinking, schema recall, provider comparison, cache, safety guards. Это уже выглядит как работа Senior Data Engineer / Analytics Engineer, особенно по research/eval части.

Главное, что мешает проекту выглядеть завершенным внешне: UI и документация отстают от фактической реализации. Внутри уже есть 57% hybrid и 9428 few-shot examples, а публичная поверхность все еще показывает более старую историю и использует более слабый UI pipeline. Если синхронизировать README/UI, включить few-shot path в demo, завершить Streamlit Cloud deploy и немного отполировать визуальный слой, проект станет существенно сильнее как portfolio artifact.

Короткий вердикт: инженерная часть - сильная и современная; продуктовая упаковка - хорошая идея, но требует финального прохода; визуальная часть - рабочая, но не дотягивает до уровня технической реализации.
