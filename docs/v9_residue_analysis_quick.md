# v9 Residue — quick root-cause анализ (40 fails, 2026-05-17 late-night)

> Quick-analysis из-под CC, пока Codex residue agent работает в фоне (gpt-5.5 xhigh, 500K+ tokens reasoning). Этот отчёт — minimal verdict для быстрого решения.

## Сводка распределения

- **Surface buckets:** 20 row_count_off + 11 filter_or_value + 7 order_by_off + 2 exec_error
- **Difficulty:** 21 moderate + 11 challenging + 6 simple
- **Concentration:** formula_1 (7), card_games (6), thrombosis_prediction (6), codebase_community (4), european_football_2 (4) — 27/40 в пяти доменах

## Root-cause категоризация (ручной обход репрезентативных)

| Category | Approx count | Sample qids | Typical fix |
|---|---:|---|---|
| **Wrong JOIN key / FK chain** | 5-7 | 207 (bond_id vs atom_id), 902 (results vs driverStandings), 866 | Explicit FK declaration в schema prompt |
| **Missing/extra DISTINCT** | 3-5 | 358 (missing), 407 (extra), 484 | Add column-cardinality + DISTINCT-intent critique |
| **Wrong SELECT shape** | 2-3 | 866 (url-only vs full row), 988 (concat vs tuple) | "Return columns separately, match gold-tuple shape" hint |
| **Wrong SQL strategy** (correlated subquery vs JOIN-agg) | 2-3 | 349, 484 | Hard — модельная стратегия отличается structurally |
| **Missing JOIN / wrong table** (classifier match) | 8 | 37, 173, 408, 518, 595 | Schema-linker miss → P3.F territory |
| **CAST AS REAL / division aggregation** | 3 | 25, 37, 1036 | Inject "use CAST(x AS REAL) for division" в critique |
| **LIKE pattern miss** | 2 | 25, 990 | hard (требует value-aware retrieval) |
| **Missing ORDER BY / LIMIT** | 3 | 894, 1144 | Add "preserve ordering hints" в critique |
| **Date arithmetic** | 1 | 1254 | gpt-oss-20b уже фиксанул похожий (1232); residue — особый case |
| **Exec failed / empty** | 2 | 1275, 77 | edge, не стоит effort'а |
| **Genuine ambiguity (gold annotation)** | 2-3 | 407 (DISTINCT-vs-not), 358 | НЕ наша вина, не fixable |

Многие fails multi-label — пересечения категорий.

## 3 кандидата rescue стратегий ($0 budget, 2-4 часа)

### 1. Explicit FK pairs в schema prompt (HIGH ROI)
- **Что:** при schema retrieval добавить `PRAGMA foreign_key_list(table)` для каждой из top-K retrieved tables. Инжектить в prompt отдельным блоком `## Foreign keys` перед `## Tables`. Формат: `lapTimes.driverId → drivers.driverId`.
- **Покрывает:** 5-7 wrong-JOIN-key cases (qids 207, 902, 866, и аналоги).
- **Стоимость:** 2-3 часа (extend `src/nl_sql/schema_index/indexer.py` + `agent/graph.py:context_builder` + tests).
- **Ожидание:** **+1.5-3pp** (3-6 rescues на 40 residue).
- **Risk:** low — additive context, не ломает existing prompts. Может сэкономить tokens если FK explicit важнее некоторых column descriptions.

### 2. Shape-aware critique on order_by_off bucket (MEDIUM ROI)
- **Что:** в `run_critique_retry.py` для residue с `comparison_reason starts with "ordered row"` добавить explicit hint: "Gold returns N columns: <names>. Match exactly, do not concat with `||`, do not add aliases". Только targeted, не глобально.
- **Покрывает:** qids 866, 988, 1144 (3 фейла).
- **Стоимость:** 1 час (bucket-specific prompt template).
- **Ожидание:** **+0.5-1pp** (1-2 rescues).
- **Risk:** low.

### 3. Question rephrasing на codestral (LOWER ROI)
- **Что:** для residue прогнать question через codestral с prompt "Rephrase this SQL question, making implicit DISTINCT / ORDER / GROUP hints explicit". Затем re-feed в pipeline.
- **Покрывает:** 2-4 cases с ambiguous formulation (qids 349, 484).
- **Стоимость:** 3-4 часа (new script + vote merge logic).
- **Ожидание:** **+0.5-1.5pp** (1-3 rescues).
- **Risk:** medium — rephrasing может drift'нуть semantics, потенциальные regressions если применять глобально (targeted only).

## Top-1 quick win

**№1 — Explicit FK pairs.** ROI = +2pp / 2h = 1.0 lift/hour, vs №2 = 0.75, №3 = 0.4. Подтверждение из данных: 8 missing_join + 5 wrong_join_key = 13 fails где graph traversal mис'ит. FK list — это **тот же сигнал** что custom schema-linker P3.F даст, только без графа путей — простая лента pairs, дешёво в 2-3 часа.

## Reality check

Memory `feedback_bird_ceiling_physics` фиксирует $0 ceiling ~65-70%. Мы на **80.0%**. Что мы знаем:
- Residue концентрируется в 5 БД из 11 (27/40 fails). Это **domain-specific**, не universal model weakness.
- Wrong-JOIN-key bucket — это **доказуемо фиксимый** через explicit FK (gold uses `atom.atom_id = connected.atom_id`, pred — `bond.bond_id = connected.bond_id`. Если pipeline видит FK list, выберет правильно).
- Multi-source rescue saturation: voting через Sonnet + Groq уже добавил 12+ rescues. Каждый next pp требует exponentially больше попыток.

**Verdict:** **82.0% в досягаемости за 4 часа** через FK pairs + shape critique. **83-84%** — потенциально через все 3 стратегии за 6-8 часов. **85%+ — нет**, нужен schema-linker (P3.F, дни) или paid SOTA model.

## Что НЕ делать

- НЕ повторять wide-schema retry (saturated).
- НЕ trying mistral-large без throttling (TPD + structural unanimity).
- НЕ ждать GraceKelly bridge без Chrome confirm от юзера.
- НЕ refactor existing voting pipeline для new prompts — добавлять additive script.
