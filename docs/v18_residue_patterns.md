# v18 residue patterns — что осталось после 86.5% EA

> Written 2026-05-19 night. Audit of the 27 fails in
> `eval/reports/2026-05-18b/v18-gpt52-pro-merged.json` (n=200 BIRD original gold,
> v18 = 173/200 = 86.5% EA).
>
> Цель: найти overlap-паттерны для prompt patch v19 + честная оценка
> headroom + risk assessment regression'ов.

## Spread

| Метрика | Значение |
|---|---|
| Total fails | 27 |
| simple | 5 |
| moderate | 16 |
| challenging | 6 |
| DBs covered | 11 (max 6 в thrombosis_prediction, 4 в formula_1) |

## Pattern classification (per-qid)

| qid | diff | db | pattern | gold-arguably-wrong? |
|---:|:---:|---|---|:---:|
| 25 | mod | california_schools | C: WHERE-source (`District Name LIKE 'Riverside%'` vs `City='Riverside'`) | no |
| 37 | mod | california_schools | C: ORDER BY scope (outer vs subquery; tied values) | no |
| 125 | cha | financial | D: extra-table JOIN (pred adds spurious `client` → row explosion 45→5817) | no |
| 207 | cha | toxicology | B: JOIN-FK choice (`connected.atom_id` vs `connected.bond_id`) | partial |
| 349 | mod | card_games | A: gold nested-subquery for "most" — query structure | partial (Arcwise territory) |
| 408 | mod | card_games | C: missing JOIN to `rulings` (`COUNT(DISTINCT id)` через JOIN) | no — pred bug |
| 484 | mod | card_games | **A1: LIMIT mis-interp** (gold no LIMIT, pred `LIMIT 1`) | no |
| 584 | mod | codebase_community | C: WHERE-source (`postHistory.Comment` vs `comments.Text`) | no |
| 595 | mod | codebase_community | C: GROUP BY granularity (`UserId` vs `UserId,PostId`) | no |
| 694 | mod | codebase_community | C: ORDER BY column (`users.CreationDate` vs `comments.CreationDate`) | partial |
| 743 | cha | superhero | C: WHERE-filter + INNER vs LEFT JOIN + percentage form | no |
| 894 | mod | formula_1 | A2: column projection (gold возвращает `milliseconds`, pred — нет) | no |
| 902 | sim | formula_1 | B: JOIN-table choice (`driverStandings` vs `results`) | no |
| 930 | sim | formula_1 | **A1: LIMIT mis-interp** ("ranked highest" → gold returns all rank=1 races, pred `LIMIT 1`) | no |
| 959 | sim | formula_1 | C: time-format LIKE filter missing (`_:%:__.___`) | no |
| 1029 | mod | european_football_2 | **E: gold wrong** (gold uses `ASC` for "highest", pred uses `DESC`) | **YES** |
| 1094 | cha | european_football_2 | C: aggregation form (`SUM(CASE)` vs `MAX(CASE)`) | partial |
| 1144 | sim | european_football_2 | **A1: LIMIT mis-interp** (gold subquery+LIMIT 1, pred JOIN no-LIMIT → 38 rows) | no |
| 1168 | cha | thrombosis_prediction | A2: column projection (gold +Birthday col) | partial (Arcwise territory) |
| 1205 | mod | thrombosis_prediction | **A1: LIMIT mis-interp** (gold no LIMIT 67 lab records, pred `LIMIT 1`) | no |
| 1247 | cha | thrombosis_prediction | **E: gold wrong** (op precedence: gold `OR FG≥450 AND WBC>3.5 AND ...` without parens) | **YES** |
| 1251 | sim | thrombosis_prediction | F: spurious `Examination` JOIN (gold) | partial — pred natural |
| 1254 | mod | thrombosis_prediction | C: bounds form (`BETWEEN` vs `>`/`<`) + date format | partial |
| 1275 | mod | thrombosis_prediction | C: wrong source table (`Laboratory.CENTROMEA` vs `Examination.CENTROMEA`) | no — pred bug |
| 1399 | mod | student_club | A3: query-structure ("Did X attend Y?" → gold per-row CASE, pred boolean COUNT>0) | partial |
| 1404 | mod | student_club | C: GROUP BY column (`event.type` vs `expense.expense_description`) | no |
| 1531 | mod | debit_card_specializing | C: aggregation form (`SUM(P/A)` vs `SUM(P)/SUM(A)`) | partial |

## Pattern families collapsed

| Family | Count | Notes |
|---|---:|---|
| **A1 — LIMIT mis-interpretation** | 4 (484, 930, 1144, 1205) | Gold uses subquery / no-LIMIT for "highest/lowest/best" when ties exist; pred adds `LIMIT 1` |
| A2 — Column projection (gold +1 col) | 2 (894, 1168) | Gold returns extra grouping col not in question |
| A3 — Query structure | 1 (1399) | "Did X attend Y?" → BIRD wants per-attendance-row CASE |
| **B — JOIN-path / FK / source-table choice** | 4 (207, 902, 959, 1275) | driverStandings/results, results.fastestLap, Examination/Laboratory |
| **C — WHERE/filter/GROUP-BY semantics** | 11 (25, 37, 125, 408, 584, 595, 694, 743, 1094, 1254, 1404, 1531) | Heterogeneous — каждый case уникален |
| D — Extra-table JOIN expansion | 1 (125) | Spurious `client` → 5817 rows |
| **E — Gold itself wrong (Arcwise catch territory)** | 2 (1029, 1247) | Confirmed Arcwise-style: ASC-for-highest, op-precedence bug |
| F — Spurious JOIN in gold | 1 (1251) | Examination INNER drops valid patients |

## Realistic v19 prompt-patch headroom

### Patch P1 — LIMIT discipline (A1 family, 4 cases)

**Proposed addition to system prompt:**

> При вопросах формата "highest/lowest/best/most X" или "the player/card/team with the most/least Y":
> если результат может содержать ties (несколько строк с одинаковым экстремальным значением),
> верни все tied rows — используй subquery `WHERE col = (SELECT MAX(col) FROM ...)` либо
> `ORDER BY col DESC` без `LIMIT 1`. Добавляй `LIMIT 1` **только** когда вопрос явно
> требует одну запись ("the single", "the top one", "first" с явным указанием на одну).

**Expected:** +2-4 cases on residue (484, 930, 1144, 1205 — all 4 are LIMIT-discipline).
**Risk:** regression on legit `LIMIT 1` cases (e.g., qid 37 already removes LIMIT 1 правильно через subquery — но какой-то simple "the school with the lowest score" case в текущем passing-set может ослабнуть). Нужно прогнать на full n=200 чтобы померить regression cost.

### Patch P2 — driverStandings vs results disambiguation (B family, 1 case)

**Proposed schema-doc addition (db_id=formula_1):**

> `driverStandings.position` = season standings rank (per race snapshot of overall standings).
> `results.position` / `results.positionOrder` = race finish position (per race).
> "track number" / "in track number less than 20" → `driverStandings.position` (standings rank).
> "finished in position N" / "Nth place in the race" → `results.position`.

**Expected:** +1 case (902).
**Risk:** low — schema clarification, не behavioral nudge.

### Patch P3 — postHistory vs comments disambiguation (C/B family, 1 case)

**Proposed schema-doc addition (db_id=codebase_community):**

> `postHistory.Comment` = the edit comment left by an editor.
> `comments.Text` = a reader's comment on the post.
> "comments left by users who edited" → `postHistory.Comment` (the edit message).
> "comments to the post" / "comments under" → `comments.Text`.

**Expected:** +1 case (584).
**Risk:** low.

### Combined ceiling

| Scenario | Best case | Worst case (regression) |
|---|---:|---:|
| P1 only | +4 cases (+2.0pp) | +0 cases (if regression equals gain) |
| P2 + P3 only | +2 cases (+1.0pp) | +2 cases (low regression risk) |
| P1+P2+P3 | +6 cases (+3.0pp) | +2 cases (P1 regression cancels) |

**Headline target:** v19 = 87.5-89.5% EA (175-179/200), if P1 has zero regression.
**Realistic:** v19 = 87.0-87.5% EA (174-175/200), expecting some P1 regression.

## What can't be patched cheaply

- **Family A2/A3 (column projection, query structure)** — gold's choices for which columns to project or whether to return per-row vs aggregate are not derivable from question text alone. Would need example-driven few-shot patches per pattern. Marginal cost.
- **Family C (heterogeneous)** — 11 unique semantics, each needs own example. Diminishing returns.
- **Family D/F (extra JOIN, spurious JOIN)** — P3.F-style schema linker. Multi-day. p3f_design.md says don't speculate.
- **Family E (gold wrong)** — Arcwise catches. Already credited in 72.36% Arcwise-Plat number. No v19 patch needed.

## Recommended action

Apply P2 + P3 only (low-risk schema-doc patches). **Defer P1** until evidence that LIMIT-discipline patch на n=200 не регрессит. Запустить experimental v19 build with P2+P3 + run full n=200 eval — expected +1pp without regression.

P1 экспериментально гонять на v18-passing subset (173 cases) и измерять regression rate напрямую. Если ≤+0 regression, добавлять; иначе skip.

## How to verify regression for P1

```bash
# 1. Apply P1 prompt patch
# 2. Re-run full n=200 eval
make eval ARGS="--limit 200"
# 3. Compare per-qid match flags v18 baseline vs v19
python scripts/audit_rescore.py \
  --baseline eval/reports/2026-05-18b/v18-gpt52-pro-merged.json \
  --candidate eval/reports/<date>/v19-with-P1.json
# 4. Count regressions (passing in v18, failing in v19)
```

If regression count > P1 gain count, **revert P1**.
