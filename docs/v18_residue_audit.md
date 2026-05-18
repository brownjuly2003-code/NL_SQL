# v18 residue audit — 27 fails after gpt-5.2 Pro + thinking sprints

> Status: per-qid audit complete, 2026-05-18 day-5 night. Written after closing
> 4 v18-residue saturation levers (kimi, sonnet45, grok-Pro+DAC, gpt-5.2 Pro+DAC,
> see `v11_saturation_evidence.md` § Pro+DAC combo).
> Headline: 86.5% EA n=200 (173/200). Residue: 27 fails (5 simple / 16 moderate / 6 challenging).

## Bucket distribution (n=27)

Classification by `(pred_row_count, gold_row_count)` pattern:

| Bucket | Count | Description |
|---|---:|---|
| **rc_match** (same count, semantic diff) | 14 | Column projection / wrong filter / wrong JOIN — both queries return same row count, content differs |
| **rc_pred_more** (pred returns extra rows) | 6 | Missing filter or DISTINCT |
| **rc_pred_less** (pred returns fewer rows) | 6 | Extra LIMIT, extra filter, or GROUP BY collapse |
| **exec_failed** | 1 | Pred SQL fails to execute |

Distribution shifted vs v11 residue (`docs/p3f_design.md`): v11 had `row_count_off`
as biggest bucket (20/38 = 52%); v18 has `rc_match` as biggest (14/27 = 52%).
v18 residue is harder — easier row-count-off cases were already rescued by Pro
and thinking sprints (v12 → v18, +6pp combined).

## Per-qid diagnosis & root cause

### rc_match (14) — same row count, content differs

| qid | tier | db | Root cause | Solvable by |
|----:|---|---|---|---|
| 37 | mod | california_schools | Pred adds `WHERE NumTstTakr > 0` zero-divisor guard, gold lacks it — gold returns school with zero test-takers (NaN/divz row first). **Pred is technically more correct.** | Arcwise audit (potential new catch) |
| 349 | mod | card_games | Gold complex MAX-subquery pattern, pred uses GROUP BY + LIMIT. **BIRD interpretation ambiguity** ("name the card with the most rulings" — multiple ties possible). | None — gold/question ambiguity |
| 408 | mod | card_games | Gold `COUNT(DISTINCT T1.id)`, pred `COUNT(*)`. **No JOIN duplication present** — both produce same count here, but gold's defensive DISTINCT is semantically robust. Pred logically equivalent for this data. | Arcwise audit (defensive DISTINCT) |
| 694 | mod | codebase_community | Gold orders by `users.CreationDate DESC` (newest users), pred orders by `comments.CreationDate DESC` (newest comments). **Question ambiguity** ("latest 10 comments"). | None — question phrasing |
| 743 | chal | superhero | Gold filters on `publisher_name = 'Marvel Comics'` count, pred uses `alignment = 'Bad'`. **Wrong schema-linking** — pred misinterpreted "act in self-interest". | Domain knowledge / schema-linker |
| 894 | mod | formula_1 | Pred missing `T2.milliseconds` column in SELECT. **Output column omission** — gold includes lap time value alongside driver+race. | Strict column-listing prompt |
| 959 | simple | formula_1 | Gold uses `time LIKE '_:%:__.___'` (finished races only), pred uses `positionOrder = 1` (champion). **Schema-domain knowledge** — BIRD's "fastest lap of champion" means the per-race fastest-lap field, not overall. | Evidence-grounded prompt |
| 1029 | mod | european_football_2 | **Already-known Arcwise catch** — gold sorts ASC for "highest" question, pred sorts DESC. Pred matches Arcwise-Plat-SQL gold. | Already in +6 audit catches |
| 1094 | chal | european_football_2 | Gold `SUM(CASE)`, pred `MAX(CASE)` for per-player rating. **Semantic equivalence** when only one row per player matches CASE — both correct. | Arcwise audit (defensive SUM) |
| 1168 | chal | thrombosis_prediction | Pred missing `T2.Birthday` column. **Output column omission** — gold includes 3 columns, pred 2. | Strict column-listing prompt |
| 1247 | chal | thrombosis_prediction | **Already-known Arcwise catch** — gold has SQL operator-precedence bug (`A OR B AND C` parses as `A OR (B AND C)`), pred parenthesises. Pred matches Arcwise-Plat-SQL gold. | Already in +6 audit catches |
| 1251 | simple | thrombosis_prediction | **Already-known Arcwise catch** — gold adds irrelevant Examination JOIN, pred queries Laboratory directly. Pred matches Arcwise-Plat-SQL gold. | Already in +6 audit catches |
| 1254 | mod | thrombosis_prediction | **Already-known Arcwise catch family** — same unnecessary-JOIN pattern + boundary inclusivity (`BETWEEN` vs `>/<`). Pred matches Arcwise-Plat-SQL gold. | Already in +6 audit catches |
| 1531 | mod | debit_card_specializing | Gold `SUM(Price/Amount)` (avg of ratios), pred `SUM(Price)/SUM(Amount)` (ratio of sums). **Math interpretation** of "average price per single item" — both defensible; pred is arguably more natural. | Arcwise audit |

### rc_pred_more (6) — pred returns extra rows

| qid | tier | db | Root cause | Solvable by |
|----:|---|---|---|---|
| 125 | chal | financial | Gold projects single `(A13-A12)*100/A12` value; pred projects district name + same value (CROSS JOIN explodes via client table). **Wrong JOIN structure**. | Schema-linker / JOIN-path |
| 207 | chal | toxicology | Pred joins `connected.bond_id` for "double bond" filter; gold joins `connected.atom_id`. **Wrong FK choice** (classic JOIN-path target). | Schema-linker / JOIN-path |
| 584 | mod | codebase_community | Gold queries `postHistory.Comment` (edit comments), pred queries `comments.Text` (user comments). **Wrong table** — "comments left by users who edited" gold-interprets as edit-trail comments. | Schema-domain knowledge |
| 595 | mod | codebase_community | Pred groups by `(UserId, PostId)` with `COUNT(*) = 1`; gold groups by UserId with `COUNT(DISTINCT PostId) = 1` (after WHERE filter). **GROUP BY structure mismatch**. | Prompt: aggregate-key consistency |
| 1144 | simple | european_football_2 | **Already-known Arcwise catch** — gold projects `id, finishing, curve` (extra id column), pred projects only `finishing, curve`. Pred matches Arcwise-Plat-SQL gold. | Already in +6 audit catches |
| 1404 | mod | student_club | Gold groups by `event.type` (event type), pred groups by `expense.expense_description` (expense type). **Wrong source table for "type"**. | Schema-linker / column-grounding |

### rc_pred_less (6) — pred returns fewer rows

| qid | tier | db | Root cause | Solvable by |
|----:|---|---|---|---|
| 25 | mod | california_schools | Gold uses `District Name LIKE 'Riverside%'` (district-level), pred uses `City = 'Riverside'` (city-level). **Wrong filter column source-table**. | Schema-linker |
| 484 | mod | card_games | Pred adds `LIMIT 1`, gold returns all 155 cards tied at highest mana cost. **LIMIT mis-interpretation**. | Prompt: "list" → no LIMIT |
| 902 | simple | formula_1 | Gold uses `driverStandings.position < 20` (championship rank), pred uses `results.grid < 20` (grid position). **Schema-linking — "track number" is ambiguous; gold reads as standings position**. | Domain knowledge |
| 930 | simple | formula_1 | Gold subquery returns 37 races where Hamilton ranked 1; pred ORDER BY + LIMIT 1 returns single race. **"Highest rank" question interpretation** — gold reads all-races-at-rank-1, pred reads best-single-race. | None — question ambiguity |
| 1205 | mod | thrombosis_prediction | Gold returns CASE per Laboratory record (67 rows for patient 57266); pred adds DISTINCT or aggregation collapsing to 1. **"Was X within range" answer-format** — gold expects per-record, pred expects scalar. | Prompt: yes/no question format |
| 1399 | mod | student_club | Same answer-format issue: gold returns per-attendance CASE (14 rows for "Did Maya attend?"); pred returns `COUNT(*) > 0` scalar. **Same yes/no anti-pattern.** | Prompt: yes/no question format |

### exec_failed (1)

| qid | tier | db | Root cause |
|----:|---|---|---|
| 1275 | mod | thrombosis_prediction | Pred joins `Examination` table for `CENTROMEA`/`SSB` columns (values `-` / `+-`), gold joins `Laboratory` (values `negative` / `0`). Pred fails because columns are missing or value-tokens differ. **Wrong table + wrong value tokens**. |

## Lever feasibility summary

| Lever | Potential gain | Risk | Priority |
|---|---:|---|---:|
| **Schema-linker (P3.F)** | 5-6 cases: 25, 125, 207, 743, 902, 1404 (+ partial 37, 1029, 1144) | Days of work, may regress correct cases | Medium |
| **Strict output-column prompt** | 2 cases: 894, 1168 (both `T2.Birthday`/`T2.milliseconds` omissions) | Low — pure additive | **High (cheap)** |
| **Yes/No answer-format prompt** | 2 cases: 1205, 1399 | Medium — could regress questions where scalar is expected | Medium |
| **"List" → no LIMIT prompt** | 1 case: 484 | Medium — gold for "top N" uses LIMIT, would regress | Low |
| **Domain-knowledge value tokens (CENTROMEA/SSB)** | 1 case: 1275 | High specificity — db-specific values | Low |
| **Re-run Arcwise-Plat-SQL rescore on v18** | 5 known catches (1029, 1144, 1247, 1251, 1254) confirmed still in residue + 4-5 potential new catches (37, 408, 1094, 1531) | Pure measurement, no regression risk | **High (cheap)** |
| **Pro-quota retry full 27** | +0-2 rescues | Requires ≥6-8h cooldown | Medium |

## Realistic ceiling past 86.5% chrome-free $0

- True semantic-error rescues addressable: **~5-7 cases** = +2.5-3.5pp on residue = **+0.5-1pp on n=200 EA**.
- BIRD-interpretation-ambiguity cases (349, 694, 930, 1205, 1399, 1531, 484): **~7 cases** structurally unaddressable without changing gold scoring.
- Schema-domain-knowledge cases (584, 743, 902, 959, 1275): **~5 cases** would require evidence-grounded domain prompts.
- Already-Arcwise-catches still in residue: **5 cases** — don't count toward BIRD headline, but boost the audit-catch portfolio framing.

**Net realistic free-tier headroom past 86.5%:** +1 to +1.5pp (i.e. 87.5-88% EA n=200 ceiling without paid API, VPN, or first-pass model swap).

Past that requires:
- Paid Anthropic/OpenAI bypass for true rescue diversity (probable +1-2pp from claude-sonnet-Pro through clean quota).
- First-pass model swap (codestral → claude/gpt-5.2 across all 200) — costly time/quota investment.
- Days of schema-linker engineering for cases like 25, 125, 207, 743, 902, 1404 (+0.5-1pp).

## Cross-reference with Arcwise-Plat-SQL audit catches

Re-ran `scripts/rescore_arcwise.py` on the v18 merged predictions (`eval/reports/2026-05-18b/v18_arcwise_rescored.json`). Updated triplet:

| Metric | v10 | v18 | Δ |
|---|---:|---:|---:|
| BIRD original | 80.5% (161/200) | **86.5% (173/200)** | **+6.0pp** |
| Arcwise-Plat-SQL | 67.34% (134/199) | **72.36% (144/199)** | **+5.0pp** |
| Arcwise-Plat (full) | 61.81% (123/199) | **66.33% (132/199)** | **+4.5pp** |
| Audit catches (gained vs BIRD) | +6 | **+5** | **-1** |

Per-tier v18:

| Variant | simple | moderate | challenging |
|---|---:|---:|---:|
| BIRD original | 92.5% (62/67) | 83.8% (83/99) | 82.4% (28/34) |
| Arcwise-Plat-SQL | 82.1% (55/67) | 69.4% (68/98) | 61.8% (21/34) |
| Arcwise-Plat (full) | 74.6% (50/67) | 64.3% (63/98) | 55.9% (19/34) |

### Audit catches at v18 (qids where pred matches Arcwise-Plat-SQL gold but NOT BIRD original)

| qid | tier | db | Same as v10 catch? |
|----:|---|---|---|
| 1029 | mod | european_football_2 | Yes — gold `ASC` for "highest" question |
| 1144 | simple | european_football_2 | Yes — gold projects extra `id` column |
| 1247 | chal | thrombosis_prediction | Yes — gold operator-precedence bug |
| 1251 | simple | thrombosis_prediction | Yes — gold's irrelevant Examination JOIN |
| 1254 | mod | thrombosis_prediction | Yes — gold's unnecessary-JOIN family |

**qid 672 (moderate codebase_community, v10 catch)** is no longer a catch at v18 — pred now matches BIRD original. This is a BIRD-side improvement (gpt-5.2 Pro picks the right `COUNT(DISTINCT ...)` pattern).

### Audit-catch portfolio framing

| Variant | Framing |
|---|---|
| **v10 portfolio** | 80.5% BIRD / 67.34% Arcwise-SQL / +6 audit catches |
| **v18 portfolio** | **86.5% BIRD / 72.36% Arcwise-SQL / +5 audit catches** |

Catches metric is **non-monotonic with improvement** — fewer catches at v18 because the system is now BIRD-correct on more cases (qid 672 example). The combined triplet reads as:
- BIRD gain +6pp = strict published-leaderboard improvement
- Arcwise gain +5pp = honest-noise-floor improvement (mostly tracks BIRD gain)
- Catch count -1 = system converging on BIRD-correct answers, fewer "gold is buggy, we caught it" cases

Net portfolio differentiation vs v10 strengthens on (1) and (2), softens on (3). Net signal still positive: system is more accurate on both clean and noisy gold, with fewer detected-gold-bug overlaps.

### Potential new catches not in Arcwise-Plat-SQL gold

Several v18 fails look like cases where pred is logically equivalent to gold but BIRD set-comparison rejects them. These are **NOT** currently in Arcwise-Plat-SQL (Jin et al. team didn't flag them):

| qid | Argument |
|----:|---|
| 37 | Pred adds `WHERE NumTstTakr > 0` zero-divisor guard. Gold's `MIN(NumGE1500/NumTstTakr)` sorts NULL/divz first under SQLite — pred's result is technically more defensible. |
| 408 | Pred `COUNT(*)` equals gold `COUNT(DISTINCT T1.id)` when no JOIN duplication exists for the filter (rulings.uuid is FK to cards.uuid, one row per matched rule). |
| 1094 | Gold `SUM(CASE WHEN x THEN val ELSE 0)` equals pred `MAX(CASE WHEN x THEN val)` when only one row matches CASE WHEN per name (true here for player names). |
| 1531 | "Average price per single item" is ambiguous: gold averages per-row ratios `SUM(P/A)`, pred ratio-of-sums `SUM(P)/SUM(A)`. Pred is the more common business-metric reading. |

These would require expert review (Arcwise team's methodology) before claiming. Not added to headline triplet without independent validation.

## Artefacts

- `eval/reports/2026-05-18b/v18_arcwise_rescored.json` — full Arcwise rescore on v18 predictions
- `eval/reports/2026-05-18b/v18-gpt52-pro-merged.json` — v18 baseline
- `scripts/rescore_arcwise.py` — rescore tool (no LLM calls, ~90s on n=200)

