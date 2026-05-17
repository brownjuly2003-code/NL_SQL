# v9 Residue Root-Cause Analysis (40 fails @ 80.0% EA)

> Анализ проведён над `hybrid-vote-critique-selfcon-sonnet-fewshot5-groq4-v9.json` (200 записей, 40 mismatch).  
> Категоризация по **реальной причине в SQL**, не по surface bucket (row_count_off / filter_or_value / order_by_off).

---

## 1. Сводная таблица категорий

| category | count | sample qids | typical fix |
|---|---|---|---|
| **wrong_aggregation** | 16 | 358, 866, 1235, 484, 518, 1531 | DISTINCT/LIMIT/subquery-scope audit rule; evidence-formula enforcement |
| **wrong_table** | 8 | 173, 408, 584, 896, 902, 1251, 1275 | Two-stage critique (table validation first); FK-hint injection |
| **ambiguous_gold** | 4 | 930, 990, 1247, 672 | Не фиксится — annotation issue / precedence bug в gold |
| **wrong_join_path** | 4 | 125, 207, 694, 743 | Explicit FK declaration for top-K tables |
| **wrong_filter_literal** | 4 | 37, 77, 1254, 1404 | Evidence re-prioritization; value sampling validation |
| **evidence_ignored** | 2 | 349, 894 | Evidence-as-rule block (переместить в топ промпта) |
| **wrong_sort_or_tiebreak** | 2 | 1029, 1168 | Column semantic hint (ASC/DESC, NULL handling) |

**Распределение по тиру:** simple 6 | moderate 21 | challenging 11 (совпадает с surface-отчётом: 21 moderate / 11 challenging / 6 simple + 2 exec_error).

---

## 2. Конкретные rescue-стратегии ($0 budget, ≤4ч each)

### Стратегия A: Evidence-first prompt reordering + formula lock
**Что:** В текущем пайплайне evidence уже инжектируется (`_compose_question` добавляет `\n\nHint: {evidence}`), но он оказывается **после schema block**. Модель (codestral / oss-20b) тонет в схеме и игнорирует hint.  
**Действие:** Переместить evidence в самый верх промпта, оформить как блок правил:
```
[EVIDENCE — obey strictly]
- average pitstop duration = Divide(SUM(duration), COUNT(duration))
- ...
[SCHEMA]
...
```
Добавить prompt rule: "Если evidence содержит формулу, используй её дословно, не упрощай через AVG/COUNT(*)."

**Ожидание:** +1–2pp.  
**Стоимость:** 1–1.5ч (правка `context_builder` + prompt template).  
**Покрытие:** qids 349, 894, 988, 1029, 1254, 1404, 1531 — 7+ случаев, где модель видела evidence, но либо проигнорировала формулу (988: AVG(milliseconds) вместо AVG(duration)), либо упустила фильтр (349: isPromo = 1).  
**Риск регрессии:** Низкий. Evidence — ground truth от BIRD annotator. Единственный риск — увеличение длины промпта; на Groq/малых моделях нужно следить за TPM.

---

### Стратегия B: Two-stage critique — сначала таблицы/JOIN, потом агрегация
**Что:** Текущий grounded critique валидирует целый SQL сразу. В residue 30% ошибок — это wrong_table / wrong_join_path. Модель-генератор и модель-критик (часто тот же codestral) соглашаются на неправильный выбор таблицы, потому что критика не изолирована.  
**Действие:** На фейлах первого прохода запускать **Stage-1 critique**: только проверка "правильные ли таблицы и JOIN-условия?" с возвратом `tables_ok: bool`. Если `false` — перегенерация с explicit FK hint. **Stage-2 critique**: только проверка WHERE/HAVING/ aggregation.

**Ожидание:** +1.5–2pp.  
**Стоимость:** 2–3ч (новый prompt template + двухпроходная логика в `run_critique_retry.py`).  
**Покрытие:** qids 25, 125, 173, 207, 408, 584, 694, 743, 896, 902, 1251, 1275 — 12 случаев (30% residue).  
**Риск регрессии:** Средний. Двухпроходная критика удваивает latency; на Groq free tier это может упереться в TPD. Нужен gate: two-stage только на moderate/challenging фейлах первого прохода.

---

### Стратегия C: DISTINCT / GROUP-BY / LIMIT audit rule
**Что:** 16/40 ошибок — wrong_aggregation. Разбивка этого bucket:
- Лишний DISTINCT: 407 (408→1693 rows), 1235 (759→73 rows)
- Пропущен DISTINCT: 358 (4→1 row), 866 (82→9 rows)
- Лишний LIMIT 1: 484 (155→1), 518 (0→1), 930 (37→1)
- Неправильный aggregate column / formula: 988 (milliseconds vs duration), 1094 (MAX vs SUM), 1531 (SUM/Amount vs SUM(Price/Amount))
- Неправильный subquery scope: 1036, 1144, 1205, 1525, 1529

**Действие:** Добавить в prompt 3 bullet-а:
1. "If the question asks for a unique list of X, use DISTINCT."
2. "If the question asks for 'all' or 'list', do NOT add LIMIT 1 unless the question explicitly asks for a single top result."
3. "Check that your GROUP BY matches the question's granularity. If you return one row per entity, group by that entity's key."

**Ожидание:** +2–3pp (охватывает ~8 случаев, половина может пройти).  
**Стоимость:** 30 мин (prompt edit, no code).  
**Покрытие:** 358, 407, 484, 518, 866, 930, 988, 1094, 1144, 1205, 1235, 1525, 1529, 1531 — 14 случаев.  
**Риск регрессии:** Средний. Некоторые текущие correct answers могут полагаться на отсутствие DISTINCT. Нужно прогнать на full n=200 с `--no-cache` или довериться diskcache diff-анализу.

---

## 3. Top-3 quick wins по ROI = lift / effort

| Rank | Стратегия | Ожидание | Усилие | ROI | Риск |
|---|---|---|---|---|---|
| **1** | **DISTINCT / GROUP-BY / LIMIT audit rule** (C) | +2–3pp | 30 мин | **4–6 pp/час** | Средний (возможна регрессия на correct-ответах без DISTINCT) |
| **2** | **Evidence-first reordering + formula lock** (A) | +1–2pp | 1–1.5ч | **1–1.5 pp/час** | Низкий |
| **3** | **Two-stage critique** (B) | +1.5–2pp | 2–3ч | **0.5–1 pp/час** | Средний (TPD/latency) |

**Рекомендуемый план на 2–4 часа:**
1. **0:00–0:30** — внедрить audit rule (C). Запустить dry-run на n=200 через diskcache diff (только cache misses).
2. **0:30–2:00** — если lift ≥ +1pp, закоммитить. Если нет — откатить. Переключиться на evidence-first reordering (A): переместить evidence блок выше schema, добавить formula-lock rule.
3. **2:00–4:00** — прогнать n=200 с (A). Если cumulative lift от (C)+(A) даёт ≥ +2pp — остановиться. 82% достигнуто или близко.

---

## 4. Reality check: есть ли 82–83% за 4 часа?

**Честный ответ:** 82% — в досягаемости, но требует удачи. 83% — маловероятно на $0 за 4 часа.

**Почему:**
- **16 wrong_aggregation** — это structural ceiling free-tier LLM. Codestral и семейство Mistral pattern-match на `AVG(col)` вместо `SUM(col)/COUNT(col)`, на `LIMIT 1` вместо CTE, на `MAX(weight)` вместо `ORDER BY weight DESC LIMIT 1`. Voting с qwen3/llama70b/gpt-oss-20b **не ловит** эти ошибки, потому что все модели на free tier делают одинаковые упрощения.
- **4 ambiguous_gold** — incompressible. Например, qid 1247: gold SQL пропускает скобки в `FG <= 150 OR FG >= 450 AND ...`, что из-за precedence даёт семантически неверный результат; pred с правильными скобками падает на exact-match. qid 930: gold возвращает 37 строк (все гонки с rank=1), pred — 1 строку; вопрос написан в singular ("In which race...").
- **12 wrong_table / wrong_join_path** — wide-schema retry (top_k=10) дал 0/20 спасений. Значит модель выбирает не ту таблицу **не из-за отсутствия схемы**, а из-за семантической путаницы (comments vs postHistory, results vs driverStandings). Больше схемы не помогает.

**Математика:**
- Из 40 фейлов: ~4 ambiguous_gold (не ловятся), ~16 wrong_aggregation (ловятся только prompt-правилами, не voting-ом).
- Если audit rule (C) спасает 4 из 16 wrong_aggregation = +2pp.
- Если evidence-first (A) спасает 2 из 7 evidence-linked = +1pp.
- Если two-stage critique (B) спасает 3 из 12 table/join = +1.5pp.
- **Best case:** +4.5pp → 82.25%. **Realistic case:** +2pp → 81.0%.

**Сравнение с физикой ceiling:** feedback_bird_ceiling_physics говорил ~65-70% на $0. Мы на 80% благодаря stacked ensemble (Sonnet bridge + voting + critique + self-consistency). Каждый следующий слой даёт убывающую отдачу. Остаток в 40 cases — это "hard core" где **все модели согласны на неправильную структуру SQL**. Это классический ceiling signal: дальнейший lift требует либо (1) smarter generator (paid GPT-4/Claude API — out of budget), либо (2) structural prompt engineering (audit rules, two-stage critique), либо (3) custom schema-linker (P3.F, дни-недели).

**Вердикт:**
- **81% — realistic за 2-4 часа** (audit rule + evidence reorder).
- **82% — possible**, если audit rule срабатывает на 6+ из 16 wrong_aggregation и luck на 1-2 ambiguous_gold.
- **83% — нет**. Для этого нужен custom JOIN-path hint или paid frontier model на residue. На $0 residue структурно incompressible выше ~82%.

---

*Report generated: 2026-05-17. Based on v9 residue n=40, post-voting, post-critique, post-self-consistency.*
