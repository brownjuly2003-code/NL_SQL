# NL→SQL Assistant — постановка задачи

**Дата:** 2026-05-10
**Автор:** Julia Edomskikh
**Статус:** v1 draft (corrected 2026-05-10 после CX/KM review). См. также: `01_architecture.md` (v1 historical), `02_architecture_v2.md` (lean baseline), `03_eval_methodology.md` (ablation plan).

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
| **BIRD Mini-Dev** | 500 Q→SQL примеров (специальный efficient-eval split BIRD; полный BIRD = 95 БД / 12 751 пар / 33.4 GB) | Eval-harness, число Execution Accuracy на публичном leaderboard'е |
| **StackExchange public dump** в Postgres | Реальная сложная схема (Posts, Users, Votes, Comments, Tags, Badges), миллионы строк, JSONB-поля, временные ряды | Демо-вопросы с красивыми графиками («активность по часам», «распределение тегов», «топ-N пользователей по карме») |

Опционально третья — **Sakila** или **Chinook** — для онбординг-демо
(простая, всем знакомая, быстро отрабатывает первое впечатление).

## 4. LLM

Только Mistral по API. Две модели в роутинге:

- **`codestral-latest`** (Codestral v25.08, актуальный код-специалист — codestral-2501 deprecated с ноября 2025) — генерация SQL и self-correction.
- **`mistral-large-latest`** — объяснение результата на естественном языке (intent classification и format selection — детерминированно, без LLM, см. v2 архитектуру).

Embeddings — `mistral-embed`.

> **Provider abstraction обязательна** (LiteLLM или собственный adapter): локальное тестирование без API, замена модели для bakeoff (см. `02_architecture_v2.md`).

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

- [ ] Execution Accuracy на BIRD Mini-Dev: **baseline ≥35-40% к неделе 4, stretch ≥50%**. Для калибровки: GPT-4 zero-shot на BIRD Mini-Dev = 47.8 / 40.8 / 35.8% EX (SQLite/MySQL/PostgreSQL); 50% — это уровень GPT-4 с table-augmentation, не Codestral zero-shot. **Hard checkpoint на неделе 3:** если EA <35% → scope down (см. v2 архитектуру).
- [ ] На StackExchange — 20 эталонных вопросов проходят end-to-end с корректным ответом.
- [ ] Веб-UI: ввод вопроса, четыре формата ответа, переключение БД, история.
- [ ] CI: тесты на гард SELECT-only, на парсер схемы, на pipeline-граф.
- [ ] README + диаграмма архитектуры + страница eval-результатов.
- [ ] Деплой: docker-compose с Postgres + Chroma + FastAPI + UI.
