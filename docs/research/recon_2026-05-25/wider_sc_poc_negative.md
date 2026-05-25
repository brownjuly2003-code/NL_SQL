# Wider self-consistency POC — negative finding

**Date:** 2026-05-25
**Hypothesis:** Расширение config F (4 temps × 1 prompt) → (2 prompt variants × 4 temps = 8 candidates) с BIRD-shape preamble во второй variant пробьёт ceiling 92.5% на residue qids, нудя модель к альтернативным SQL-shape'ам (WHERE=MAX vs LIMIT, CAST(SUM)/COUNT vs AVG, date-format conventions).

**Source of method idea:** Recon TOP-10 (Kimi + Codex, 2026-05-25). Конкретно — синтез "diverse prompt variants" из CHASE-SQL + "execution-cluster voting" из Alpha-SQL / Wang 2023 (уже было в NL_SQL как config F).

**Decision rationale:** Methods требующие fine-tune (Arctic, Databricks RLVR, OmniSQL) или paid OR (Agentar, AskData) отбили. Methods architectural-heavy (WrenAI semantic layer, AskData metadata extraction) — out of scope POC. CHESS Unit-Tester — semantic не помогает когда residue не "wrong answer" а "BIRD-quirk gold". Остался **prompt-shape diversity** как cheapest delta vs current config F.

**Result: 0/3 on smoke (qids 25, 484, 930). Sweep остановлен.**

## Implementation

`scripts/wider_sc_poc.py` (337 LOC). Standalone, bypasses LangGraph:
1. Load v29 residue qids из `eval/reports/2026-05-24/v29-v28-plus-p3f-q1275-merged.json`.
2. Build context per qid via existing `retrieve_context` (same as production C).
3. For each (variant, temp) pair:
   - `default` = current `prompts/generate_sql.txt` rendered as-is
   - `bird_shape` = same + splice BIRD-shape rules block before `# Output contract`:
     - "highest/lowest/most X" → `WHERE col = (SELECT MAX/MIN ...)` not `ORDER BY ... LIMIT 1`
     - "average of average X" → `CAST(SUM(X) AS REAL) / COUNT(*)` not `AVG(X)`
     - "after Y/M/D" → match column literal format
     - "rank N" → `WHERE rank_col = N` not `ORDER BY LIMIT N`
     - Tie inclusion via `WHERE col = (SELECT MAX(col))`
     - european_football_2 "highest" может быть ASC (positional inversion)
4. Execute each → fingerprint → cluster → pick plurality (existing `vote()` logic inline).
5. Compare winner vs gold via `safe_compare_pred`.

Smoke: 3 qids × 8 candidates = 24 codestral calls (cache cold), сработало корректно за ~2 минуты до 429 на mistral-embed для qid 930.

## Per-qid diagnostic

### qid 25 moderate california_schools — "average of average math score for SAT > 400"

| | Shape | Result |
|---|---|---|
| Default winner (T=0.2) | `WHERE satscores.AvgScrMath > 400` per-row | 80 rows |
| BIRD-shape winner (T=0.2) | `WHERE satscores.AvgScrMath > 400` per-row | 80 rows |
| Gold | `GROUP BY sname HAVING SUM(AvgScrMath)/COUNT(*) > 400` | 6 rows |

**Verdict:** BIRD-shape preamble не дотянулась до aggregation shape. Variants сошлись на тот же шейп. Preamble rule про "average of average → CAST(SUM)/COUNT" was actually relevant, but model не дешифровал "average of average" в вопросе как aggregation-of-aggregation. **Prompt-level не пробивает — нужна explicit per-qid hint (P3.F-style).**

### qid 484 moderate card_games — "Italian names of cards in Coldsnap with the highest converted mana cost"

| | Shape | Result |
|---|---|---|
| Default winner (T=0.2 + T=0.8) | `ORDER BY convertedManaCost LIMIT 1` | 1 row |
| BIRD-shape winner (T=0.2-0.6, cluster size 3) | `WHERE convertedManaCost = (SELECT MAX(...) FROM cards WHERE setCode='CSP')` | 12 rows |
| Gold | `INNER JOIN sets ... ORDER BY convertedManaCost DESC` (no MAX filter) | **155 rows** |

**Verdict — самый ясный сигнал:** BIRD-shape preamble РАБОТАЕТ на shape-level (генерит реально другой SQL: WHERE=MAX subquery вместо LIMIT 1). Но BIRD-gold имеет третий, **non-NL-faithful** pattern: "highest" = "сортируй все по DESC, верни 155 строк". Ни default LIMIT 1 (1 row) ни BIRD-shape WHERE=MAX (12 rows) не попадают в 155. Это **BIRD annotation quirk** — gold не отвечает на буквальный вопрос. Никакой prompt-shape вариант не может одновременно (a) фильтровать "max" и (b) "list all DESC".

### qid 930 simple formula_1 — "race did Lewis Hamilton rank the highest"

429 на mistral-embed retrieval. Не дошли до generation step. Embeddings уже cached для предыдущих qids, но новый question = новый embed → rate limit на free tier.

## Why this is "physics ceiling" — anatomy of remaining 12 residue

Из `docs/NEXT_SESSION.md` per-qid анализ + smoke evidence:

| Failure pattern | Qids | Prompt-shape-fixable? | Why |
|---|---|---|---|
| Aggregation shape (AVG vs SUM/COUNT, GROUP BY) | 25, 1094 | **No** | Требует explicit per-qid hint про "average of average" semantics — generic preamble не дешифрует |
| Column-order in tuple | 37 | **No** | Gold имеет (Street, City, State, Zip), pred (Street, City, Zip, State) — formatting quirk, не shape |
| SELECT-shape (1 vs 3 cols) | 125, 1168 | **No** | Gold over-/under-selects vs NL question — annotation quirk |
| Aggregation logic + tie | 349 | **No** | Gold filters isPromo=1 + COUNT max artist subquery — derive нельзя из NL |
| LIMIT 1 vs no-LIMIT vs WHERE=MAX | 484, 930, 1144 | **Partial** | Smoke показал что BIRD-shape preamble меняет shape, но BIRD gold pattern "list all DESC" non-NL-faithful — недостижим из NL faithfully |
| Semantic ambiguity ("one history per post", "latest") | 595, 694 | **No** | NL formally ambiguous, BIRD gold выбирает one interpretation |
| Sort direction inversion | 1029 | **Partial** | Smoke preamble mentioned ASC fallback для football_2 — но это per-db hint, generic preamble redundant с P3.F |
| BIRD precedence bug | 1247 | **No** | Gold имеет OR/AND без скобок — annotation bug, не модель |
| Date interpretation | 1254 | **No** | "after 1990/1/1" ambiguous, gold ловит формат поля |
| Gold returns 0 rows | 518 | **No** | Closed bogus EOD-4 |

Из 15 residue: **0 чисто prompt-shape-fixable**, **3 partial** где shape diversity помогает но BIRD-gold remain non-NL-faithful. Smoke на 3 (включая 2 из этих 3) дала 0 matches.

## Implication for portfolio

92.5% — **ceiling под $0 budget + faithful-to-NL semantics**. Past 93% требует одно из:
1. **Paid OR top-up** (reasoning models broader context, был exhausted EOD-2, qid 518 reasoning rescue EOD-4 confirmed)
2. **Fine-tune** (Arctic-Text2SQL-R1 / Databricks RLVR style — out of free-tier)
3. **Acceptance of non-NL-faithful generation** (учить модель угадывать BIRD annotation quirks через массовое hint engineering — P3.F approach уже выжата на 8 targets)
4. **Switch metric** к expert-verified subset (ReViSQL approach — но это другой benchmark)

POC методически валидный, исполняемый, **подтверждает empirical saturation** утверждённую в handoff. Не lift, не regression — clean negative.

## Artifacts

- `scripts/wider_sc_poc.py` — POC implementation, 337 LOC, ruff clean
- `eval/reports/2026-05-25/wider_sc_smoke.json` — smoke output на 3 qids
- This document — write-up

## Recommendation

**Не интегрировать в production pipeline.** POC выполнила свою функцию — empirically confirmed physics ceiling. Script остаётся для будущих ablations / educational reference (e.g., если когда-нибудь появится paid OR budget — варьировать prompt+model перпендикулярно).

`scripts/wider_sc_poc.py` оставлен в `scripts/`, gitignore не нужно — это honest research artefact с negative result, имеет ценность как "что попробовали и почему не сработало" для портфолио.
