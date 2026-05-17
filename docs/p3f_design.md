# P3.F — JOIN-path schema-linker: design analysis & realistic ceiling

> Status: analysis complete, code deferred. Written 2026-05-18 after llama70b
> TPD-reset retry sanity check (`v11_saturation_evidence.md` § day-3).

## Why P3.F exists

The v11 residue is 38 cases. The biggest single bucket is `row_count_off`
(20 cases), and `feedback_bird_ceiling_physics` + memory suggested P3.F
(custom JOIN-path schema-linker) could lift it +5–10pp by addressing
"`row_count_off` is structural unanimous failure across all Mistral models".

## Bucket sub-classification (script-derived, n=20)

Run `python -c` snippet on `eval/reports/2026-05-17/…-v11.json` with table-set
diffing + DISTINCT diffing gave:

| Sub-bucket | Count | Description |
|---|---:|---|
| same_tables_diff_join_cols_or_filter | 10 | Pred picks same tables as gold, but wrong JOIN ON column, wrong WHERE column, or wrong projection |
| missing_table_in_pred | 5 | Pred substitutes wrong table or omits a required one |
| distinct_diff_only | 4 | Bidirectional: 3 cases gold-has-DISTINCT/pred-doesn't, 1 case pred-has-DISTINCT/gold-doesn't |
| extra_table_in_pred | 1 | Pred joined extra table that changes row count |

## Per-qid audit of the "same_tables_diff_join_cols_or_filter" bucket

This is the supposed P3.F target. Reading each gold ↔ pred pair:

| qid | diff | Real root cause | Solvable by JOIN-path linker? |
|---:|---|---|---|
| 77 | mod | Pred filters on `frpm.CountyName + Low/High Grade`, gold on `schools.County + GSserved='K-9'`. Wrong **filter-column source-table**. | partially — needs column-to-table grounding heuristic |
| 207 | chal | Pred joins `connected.bond_id`, gold joins `connected.atom_id`. Wrong **FK choice** between same tables. | **yes — classic JOIN-path** |
| 484 | mod | Pred adds `LIMIT 1`, gold doesn't (returns all 155 cards tied at top mana cost). **Query-structure mis-interpretation**. | no |
| 518 | mod | Gold uses WITH-clause to find max format then selects all matching cards. Pred just GROUP BY + LIMIT 1. **Query-structure mis-interpretation**. | no |
| 930 | simple | Gold uses subquery IN (returns 37 races where Hamilton ranked 1). Pred uses JOIN + ORDER BY ASC + LIMIT 1 (returns single best race). **Semantic mis-interpretation of "highest rank"**. | no |
| 990 | chal | Pred missed `WHERE results.time LIKE '_:%:__.___'` filter from gold. **WHERE clause omission**. | partially — needs evidence-grounded WHERE |
| 1144 | simple | Pred uses JOIN, gold uses subquery + LIMIT 1. Pred returns 38 rows (Player_Attributes has 38 rows per player). **Subquery-vs-JOIN issue**. | no |
| 1205 | mod | Pred has `LIMIT 1`, gold doesn't. Gold returns 67 lab records for patient 57266; pred truncates to 1. **LIMIT mis-interpretation**. | no |
| 1399 | mod | Gold returns 14 rows (one per attendance match) via CASE WHEN. Pred returns single COUNT > 0 boolean. **Query-structure interpretation** ("Did X attend Y?" → BIRD wants per-attendance-row not single bool). | no |
| 1404 | mod | Pred groups by `expense.expense_description`, gold groups by `event.type`. Wrong **GROUP BY column source-table**. | **yes — schema linking** |

**Solvable-by-JOIN-path-linker count: ~2** (qid 207, 1404), maybe 2 more partial
(qid 77, 990 if linker also handles WHERE-column source).

## Realistic ceiling revision

Earlier memory: «P3.F +5–10pp ceiling lift, дни-недели работы».
Reality after audit: **+1–2pp on residue = +0.5–1pp on n=200 EA.** Most of the
20 row_count_off cases are query-structure mis-interpretations (LIMIT/subquery/CASE
shape), not JOIN-path choice errors. A schema-linker addresses 2–4 cases out
of 38 residue.

Combined with other buckets:
- `distinct_diff_only` (4): would need a bidirectional DISTINCT-rule, but it's
  bidirectional — same prompt rule would regress qid 407 (where gold lacks
  DISTINCT but pred adds it).
- `set_mismatch` (10), `col_projection_off` (7): not addressed by JOIN-path linker.

**Total realistic chrome-free $0-budget headroom past v11 81.0%:** ≤+2.5pp.
This matches the upper bound from `v11_saturation_evidence.md` § lower bound
estimate (binomial CI ≤5% rescue rate across all attempted free-tier voting).

## Design (sketch only, not implemented)

If we did build P3.F:

1. **Foreign-key candidate enumeration.** For each pair of tables (T1, T2)
   in retrieved set, collect ALL FK paths via SQLite `pragma foreign_key_list`
   and via heuristic `T1.X_id ↔ T2.id` matches. Each path has score.
2. **Question-token grounding.** Map question entities to columns via
   embedding similarity against `column_name + column_description` (already
   in chunker). Drop FK paths whose entity-mapped columns are not on the
   path.
3. **Re-prompt with candidate JOIN paths as hint.** "For tables {T1, T2, T3},
   the candidate JOIN paths are: (a) T1.X = T2.X via FK; (b) T1.Y = T3.Y +
   T3.Z = T2.Z indirect. Question 'X' suggests path (a). Use it unless the
   evidence forces (b)."

This is research-grade work. Memory `feedback_no_redraft_after_approval` +
the realistic +0.5–1pp ceiling argue against starting it without explicit
user mandate.

## Recommendation

**Don't build P3.F speculatively.** The headline 81.0% v11 + 67.34% corrected-gold
triplet is portfolio-ready. The marginal +0.5–1pp from a JOIN-path linker
costs days of work for a number that won't change the narrative.

If user wants past 81% chrome-free, the cheaper paths are:
1. **Wait for daily quotas to fully reset** (24h+) and re-run llama70b on
   the 21 unattempted qids — expected ≤1 rescue but $0 cost.
2. **Try `gemini-2.5-pro` (RPD ≥100, 5× higher than 2.5-flash)** via Google
   AI Studio. New provider on residue, ortogonal model family.
3. **OpenRouter paid $1 top-up** unlocks 1000 free-model requests/day —
   not paid model usage, just lifts free-tier cap. Could re-run nemotron and
   other free OpenRouter models with no daily cap.

If user wants past 81% with $1–3 budget: paid Anthropic API Sonnet sweep on
the 38 residue. Memory marks this deprecated, but it's the highest $/pp.

If user wants research-grade improvement: P3.F design above + custom corrective
self-consistency (CSC-SQL technique from `docs/bird_sota_research.md`). Multi-day
work, expected +2–4pp combined.
