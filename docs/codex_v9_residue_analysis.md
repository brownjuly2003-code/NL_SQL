# v9 residue root-cause analysis

Primary category is assigned once per failed qid, so counts sum to 40. Many cases have secondary projection or duplicate-grain symptoms; the category below is the SQL decision that most likely caused the mismatch.

## Categories table

| category | count | sample qids (3) | typical fix |
|---|---:|---|---|
| wrong_aggregation | 11 | 25, 1094, 1531 | Add an evidence/formula checklist before SQL finalization: denominator scope, `SUM/COUNT` vs `AVG`, row grain, `DISTINCT` vs duplicate-preserving output, and metric column choice. |
| ambiguous_gold | 11 | 349, 1029, 1399 | Do not spend broad engineering effort. These are mostly BIRD annotation/evidence quirks where the gold contradicts the question or a more natural SQL: e.g. 1029 says highest but gold sorts ascending; 1399 asks yes/no but gold emits 14 event rows. |
| wrong_table | 6 | 173, 408, 584 | Table/column validation stage before generation: force the model to name the source table for each requested concept, especially `rulings.text` vs `cards.text`, `postHistory.Comment` vs `comments.Text`, `driverStandings.position` vs `results.position`. |
| wrong_sort_or_tiebreak | 4 | 518, 930, 1144 | Separate sort/limit critic: reject unsupported `LIMIT 1`, check whether the gold-style task wants all rows after ordering, all rank-1 rows, or a deterministic tie pick. |
| wrong_join_path | 3 | 125, 207, 1251 | Inject explicit FK/bridge paths for the selected tables only. Most failures are not recall misses; they are wrong fanout or missing bridge constraints. |
| missing_group_by | 2 | 595, 1404 | Grain critic: decide whether the grouping entity is user, post, event, expense type, etc. before writing the SELECT. |
| evidence_ignored | 2 | 866, 894 | Promote BIRD evidence from a passive hint to a mandatory checklist; these failed while the evidence explicitly named the required output columns. |
| wrong_filter_literal | 1 | 77 | Sample/check column values for literals such as grade span (`GSserved = 'K-9'`) instead of decomposing into nearby columns. |

Date arithmetic is not a primary remaining bucket after v9. qid 1168 computes the date and age correctly; the mismatch is the gold's extra `Birthday` projection, so it is counted as ambiguous_gold rather than date_arith.

Notable sanity finding: qid 990 locally executes to the same first row for gold and pred on the checked SQLite DB, despite the report saying `gold_rows=0, pred_rows=1`. Treat it as an eval/report artifact candidate before spending tokens on it.

## Strategies

### 1. Evidence-as-constraints retry

Convert `evidence` into a short mandatory checklist placed above the question, then run a narrow retry only on residue. The critic should answer yes/no for each atom: required column, formula, row grain, date/literal, final projection. This is different from the saturated column-count critique: it validates semantic atoms, not result width.

Expected lift: +1.0 to +2.0pp (2-4 qids).

Cost: 2-3 hours.

Likely qids: 25, 866, 894, 988, 1036, 1251, 1275, 1529, 1531.

Risk: low if merged rescue-only; medium if enabled globally because some BIRD evidence is itself noisy (1275, 1029).

### 2. Two-stage table/JOIN validator with FK JSON

For the top retrieved tables, inject `PRAGMA foreign_key_list` plus primary-key-like columns as compact JSON. Stage 1 asks only: selected tables, selected columns, join path, expected fanout. Stage 2 writes SQL only after Stage 1 is stable. This is not a custom schema-linker rewrite; it is a prompt-time guard around the existing retrieval.

Expected lift: +1.0 to +1.5pp (2-3 qids).

Cost: 3-4 hours.

Likely qids: 125, 173, 207, 408, 584, 896, 902, 1251, 1275.

Risk: medium. FK metadata may be sparse or absent in some SQLite DBs, and over-trusting it can miss implicit joins. Keep fallback to current schema text.

### 3. LIMIT/DISTINCT/grain micro-critic

A tiny static pass flags high-risk SQL shapes before retry: `LIMIT 1` on questions asking "list/all/which races"; `DISTINCT` added when question asks for rows rather than unique values; missing `DISTINCT` when evidence says "don't compute repetitive ones"; `COUNT(DISTINCT ...)` vs duplicate-preserving `COUNT(...)`.

Expected lift: +0.5 to +1.5pp (1-3 qids).

Cost: 2 hours.

Likely qids: 358, 407, 518, 930, 1144, 1235, 1254.

Risk: medium-high if global, because BIRD gold is inconsistent on "all/highest". Safe as residue-only rescue with exact-match merge.

## Top-3 quick wins

1. Evidence-as-constraints retry. Best ROI: roughly +1-2pp for 2-3 hours, and it attacks failures where the right formula/column is already present in BIRD evidence.

2. LIMIT/DISTINCT/grain micro-critic. Cheap, targeted, and likely to rescue at least one duplicate/limit failure. Do it residue-only to avoid regressions.

3. FK JSON + table/JOIN validator. Slightly more work, but it is the only 4-hour option that touches the wrong_table/wrong_join_path cluster without becoming P3.F custom schema-linking.

## Reality check

At 80.0%, the remaining residue is no longer "more retries will average out" territory. About 11/40 are ambiguous_gold or report-artifact style, and another large block needs BIRD-specific row grain rather than better retrieval. That means the residue is partly structurally incompressible on $0 unless you overfit to this eval slice.

82.0% is reachable in 4 hours only at the upper edge: qid 990 sanity recovery plus 3-4 real rescues from evidence/FK/grain checks. 83.0% needs 6 additional rescues, and that is unlikely in one short sprint without either paid stronger reasoning or P3.F-level schema-linking. The honest target for the next 2-4 hour attack is +1.0 to +2.0pp, not a reliable +3.0pp.
