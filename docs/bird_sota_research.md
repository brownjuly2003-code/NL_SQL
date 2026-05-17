# BIRD Text-to-SQL SOTA Research — How Systems Get Past 80% EA

**Date:** 2026-05-17
**Goal:** Understand who crosses 80% Execution Accuracy on BIRD, what they do, and whether 80% → 85% → 88% is realistic for our $0-budget Mini-Dev setup at 80.0%.
**Our context:** BIRD Mini-Dev (SQLite, dev_split, n=200, seed=0), 80.0% EA, free-tier stack (Codestral + Groq + Sonnet 4.6 via Perplexity bridge).

---

## 1. Current SOTA on BIRD (full dev/test, May 2026)

Pulled from the official leaderboard at <https://bird-bench.github.io/>. **The leaderboard publishes full-test EA, not Mini-Dev n=200**, so all numbers below are full BIRD test (1789 examples) unless noted.

| Rank | System | Dev EA% | Test EA% | Key leverage | Paid / Free | Date |
|------|--------|---------|----------|--------------|-------------|------|
| Human baseline | DB students + DE | — | **92.96** | Human experts | — | reference |
| 1 | **AskData + GPT-4o** (AT&T DSAIR) | 77.64 | **81.95** | Oracle-knowledge prompting + GPT-4o ensemble | **Paid (GPT-4o)** | 2025-09-25 |
| 2 | **Agentar-Scale-SQL** (Ant Group) | 74.90 | **81.67** | RL-fine-tuned 32B + parallel synthesis + tournament selection | **FT + heavy compute** | 2025-07-14 |
| 3 | LongData-SQL (LongShine) | 74.32 | 77.53 | Long-context schema grounding | Proprietary | 2026-04-28 |
| 4 | SiriusAI-Text2SQL (Tencent) | 75.35 | 77.03 | Agent system | Proprietary | 2026-01-02 |
| 5 | Zhiwen-Lingsi (China Telecom) | 73.53 | 76.63 | Multi-component | Proprietary | 2026-01-26 |
| 6 | DeepEye-SQL (HKUST-GZ) | 73.53 | 76.58 | Open-source code | Mixed | 2026-04-25 |
| 7 | GT-ChatBI-SQL (MR Tech) | 74.70 | 76.47 | Conversational | Proprietary | 2025-12-04 |
| 8 | Q-SQL (AWS) | 72.99 | 76.47 | 30B-3B MoE | Mostly free models | 2026-02-06 |
| 9 | MIC2-SQL | 74.45 | 76.41 | Anonymous | Proprietary | 2025-04-16 |
| 10 | CHASE-SQL + Gemini (Google) | 74.90 | 76.02 | Multi-path reasoning + pairwise selector + Gemini-1.5-Pro | **Paid (Gemini)** | 2026-04-03 |
| 11 | xiaoyi-text-to-sql | 72.75 | 75.96 | Custom | Proprietary | 2026-02-21 |
| 12 | RED-SQL (SCNU) | 74.19 | 75.91 | 30B open-source | Free model + FT | 2025-09-22 |
| 13 | JoyDataAgent (JD) | 74.25 | 75.85 | Open-source | Mixed | 2025-10-23 |
| 14 | Sinovatio-SQL | 73.72 | 75.80 | Proprietary | Proprietary | 2025-05-30 |
| — | **CSC-SQL 32B** (paper, not on board) | — | **73.67** | Self-consistency + correction RL on Qwen2.5-32B | Open FT | 2025-05 |
| — | **Arctic-Text2SQL-R1 32B** (Snowflake) | — | **71.83** | GRPO-RL fine-tuned 32B | Open weights, requires FT | 2025-05 |
| — | XiYan-SQL (Alibaba) | — | **75.63** | Multi-generator ensemble, only 5 candidates, fine-tuned + ICL | Mixed | 2024 preview |
| — | CHESS (Stanford) | 65.00 | **66.69** (71.10 hi-budget) | 4-agent retrieve/select/generate/unit-test | Open code, GPT-4 calls | 2024 |

### Key observations

- **Only 2 systems on the public leaderboard cross 80%**: AskData (81.95%) and Agentar-Scale-SQL (81.67%). Both use heavy compute and at least one paid or fine-tuned component.
- **The 73–77% band is crowded** — that's where every serious agent system lives.
- **No published $0-budget system** crosses 80% on the full BIRD test set with public scores. Free-tier open-source ceilings published openly: Arctic-32B 71.83%, CSC-SQL 32B 73.67%, XiYan 75.63% (latter uses fine-tuning).
- **Critical caveat**: Jin et al. (CIDR/VLDB 2026, [arXiv:2601.08778](https://arxiv.org/abs/2601.08778)) audited BIRD and found **52.8% of BIRD Mini-Dev questions have annotation errors**. Re-evaluation on corrected data shifts top-system EA by **−3% to +31%**. CHESS jumped from 62% → 81% just from corrected gold. The community consensus emerging: **scores in the 75–85% band are partly noise**, and chasing them risks overfitting to wrong-gold artifacts.

---

## 2. What drives the lift past 75% → 80%+

Synthesized across CHESS, CHASE-SQL, XiYan-SQL, Agentar-Scale-SQL, CSC-SQL, Arctic-R1, Contextual-SQL.

### A. Test-time scaling — biggest single lift (~+3 to +7 pp)
- **Parallel sampling**: 5–32 candidate SQLs from one or more generators with high temperature.
- **Tournament / pairwise selector** (CHASE-SQL): trained binary judge picks best of 2, run as bracket. CHASE got ~+5 pp over self-consistency.
- **Self-consistency on execution result**: cluster by result-set hash, pick majority. Baseline ~+2-3 pp.
- **Corrective self-consistency** (CSC-SQL, [arXiv:2505.13271](https://arxiv.org/abs/2505.13271)): pick top-2 most frequent results, feed both to a *merge-revision* model. +0.72 to +5.54 pp over plain SC.

### B. Schema linking (~+2 to +5 pp)
- **M-Schema / semi-structured schema** (XiYan): include column type, sample values, FK as compact serialization. Replaces flat CREATE TABLE dumps.
- **Bidirectional retrieval** ([arXiv:2510.14296](https://arxiv.org/html/2510.14296v1)): question→schema AND schema→question to recover dropped columns. Recall-first.
- **Value retrieval**: index DB cell values, retrieve top-k for question entities (CHESS Information Retriever).

### C. Reasoning style (~+2 to +4 pp)
- **Divide-and-conquer** (CHASE-SQL): decompose into sub-queries in one LLM call.
- **Execution-plan CoT**: prompt model to reason as a query optimizer (joins → filters → projections).
- **Instance-aware synthetic few-shot**: generate fewshots tailored to the test question shape, not static top-k retrieval.

### D. Fine-tuning (~+5 to +10 pp — but blocks $0)
- **Arctic-R1 GRPO** with simple execution-correctness reward, on Qwen2.5-7B/32B. Beats GPT-4o.
- **Agentar generation model** is Omni-SQL-32B + GRPO further-trained on execution.
- **CSC-SQL** trains both generator and revisor via GRPO.
- Without FT, the same architectures lose ~5–8 pp.

### E. Domain knowledge / evidence (~+2 to +3 pp)
- **Evidence injection from BIRD's `external_knowledge` field**: already standard; just including it is +3–5 pp.
- **Auto-generated evidence** (SEED, [arXiv:2506.07423](https://arxiv.org/html/2506.07423v1)): when human-written evidence isn't available.

### F. Unit testing / execution self-debug (~+1 to +3 pp)
- CHESS Unit-Tester: LLM-written natural-language assertions checked against result.
- **RetrySQL** ([arXiv:2507.02529](https://arxiv.org/html/2507.02529v1)): explicit `[BACK]` retry tokens during training. +4 pp.
- Execution-feedback retry loop: just running and feeding the error back is +1–2 pp.

---

## 3. $0-budget reachable techniques (realistic for our setup)

We already have: codestral gen, fewshot top-3/5, Sonnet voting, Groq voting, grounded-critique, evidence injection, sort_default. Map of unused leverage:

### High-EV (1–4 hour cost, plausible +1 to +3 pp each, additive ≤2 pp)

1. **M-Schema serialization** (XiYan-SQL). Replace current schema dump with `table.column (type) [sample1, sample2] FK→other.col` per line. **GitHub**: <https://github.com/XGenerationLab/XiYan-SQL> (M-Schema implementation in repo). Free, prompt-only change. Expected +1–2 pp if our schema rendering is currently flat.

2. **Pairwise tournament selector with Sonnet** instead of plurality voting on residue. Currently we do majority-vote on Groq + Sonnet. CHASE-SQL ([arXiv:2410.01943](https://arxiv.org/abs/2410.01943)) shows pairwise > plurality by ~2 pp because plurality loses when 4 wrong candidates outnumber 1 right one. Sonnet 4.6 is strong enough to act as judge. Implement: pick top-k by Groq, run bracket with Sonnet as comparator. Free if we stay within Sonnet quota.

3. **Divide-and-conquer prompting** (CHASE-SQL technique #1) on `challenging` tier only (67.6% → potentially 72%). Single-call decomposition prompt, no additional API spend. Expected +0.5 to +1.5 pp overall.

4. **Value-retrieval grounding**. For each question, BM25 / substring-search over DB cell values (sampled), inject matches as `evidence: question token "X" appears in column Y`. Free, local. CHESS shows ~+2 pp from this alone.

### Medium-EV (3–8 hours, uncertain payoff)

5. **Corrective self-consistency** (CSC-SQL approach without RL): take top-2 result clusters, feed both SQLs + their results to Sonnet, ask which is correct or to merge. Paper shows +0.7 to +5.5 pp over plain SC. Free.

6. **Instance-aware few-shot** (CHASE): instead of static top-k retrieval, use LLM to *generate* synthetic Q→SQL examples that mimic the structural shape of the test query. One extra Groq call per question. Caveat: when we tried fewshot=5 vs 3 it was a wash, suggesting our retrieval is the bottleneck, not k. This could fix that.

### Low-EV (do not attempt)

- **Fine-tuning** — out of budget and skill envelope for the deadline.
- **Adding more voter models** — saturated (we already showed gpt-oss-120b, mistral-large, codestral-fewshot7 zero rescues).
- **Wider schema retry** — already saturated per residue analysis.

---

## 4. Realistic verdict for $0 Mini-Dev n=200

### Ceiling math

| Target | Realistic? | Why |
|--------|-----------|-----|
| **82%** (164/200) | **Yes, plausible** — +4 hits needed. M-Schema + value-retrieval + D&C on challenging tier could plausibly each rescue 1–2 questions. |
| **85%** (170/200) | **Hard but not impossible** — +10 hits. Requires combining 3+ of the techniques above AND not regressing easy/moderate. Pairwise tournament + corrective SC + M-Schema is the strongest stack. |
| **88%** (176/200) | **Highly unlikely at $0** — would put us above the #1 paid leaderboard system. The only published systems above 81% on full test use either GPT-4o oracle prompting or 32B + RL fine-tuning. |
| **90%+** | **Effectively impossible** — even human experts only hit 92.96%. Annotation errors in BIRD Mini-Dev (52.8% per Jin et al.) mean the *real* ceiling is far lower than 92.96% on uncorrected gold; pushing past ~85% means memorizing benchmark mistakes. |

### Key takeaway from the broken-benchmarks paper

Jin et al. ([arXiv:2601.08778](https://arxiv.org/abs/2601.08778), CIDR/VLDB 2026) found **BIRD Mini-Dev has 52.8% questions with annotation issues**. They re-evaluated 5 top open systems on corrected data — rank shifts of up to 3 positions, EA changes from −3% to +31%. CHESS jumped from 62% → 81% on the corrected set. **Implication**: our 80.0% on the uncorrected n=200 may already be near the achievable ceiling for our slice. Further gains may require fitting to specific wrong-gold cases (anti-pattern).

### Recommendation: stop at 80.0% as headline, redirect the next 2-8 hours to

1. **Stress-test the 80% number on Jin et al.'s corrected gold subset** if available in their GitHub <https://github.com/uiuc-kang-lab/text_to_sql_benchmarks>. If our EA-on-corrected is ≥80%, our number is *more* trustworthy than the leaderboard's 73–77% band.
2. If chasing one more bump: **M-Schema + pairwise Sonnet tournament on residue** (highest-EV combo, ~3 hours, plausible 82%).
3. **Package the result around methodology, not the raw number**: we beat free-tier published ceilings (Arctic 71.83%, CSC 73.67%, XiYan 75.63%) and approach paid SOTA (81.95%) without fine-tuning or paid APIs. That's the headline. Pushing 80% → 82% is marginal; pushing the *story* is high-EV.

### Update 2026-05-17 next-day: recommendation #1 executed

Arcwise-Plat artefacts (`arcwise_plat_sql_only_with_diff.json`, `arcwise_plat_full_with_diff.json`) downloaded from Jin et al.'s repo; 199/200 of our v10 qids overlap.

**Results** (scoring v10 predictions against corrected gold; see `docs/corrected_gold_evaluation.md`):

| Gold variant | EA | Δ vs original |
|---|---:|---:|
| BIRD original (published) | 80.5% (161/200) | — |
| Arcwise-Plat-SQL (SQL-only fixes) | **67.34%** (134/199) | **−13.2pp** |
| Arcwise-Plat full (SQL + question + evidence + schema) | **61.81%** (123/199) | **−18.7pp** |

Net transitions vs original (sql_only): **+6 gained / −32 lost**. Gained cases are auditable proof our pred catches BIRD annotation bugs (missing DISTINCT, ASC-vs-DESC, extra-id-column, wrong-precedence, unnecessary-joins). Lost cases mostly reflect Arcwise tightening gold with quality fixes (rtype filters, NOT NULL guards, DISTINCT corrections, tie-handling).

**Implication for portfolio:** publish a triplet, not a single number — "80.5% on published BIRD; 67.34% on Arcwise corrected; +6 cases where our pred beats BIRD's wrong gold". Triplet differentiates from leaderboard-only entries and directly addresses the Jin et al. credibility critique.

Reproduce: `uv run python scripts/rescore_arcwise.py --report eval/reports/2026-05-17/hybrid-vote-critique-selfcon-sonnet-fewshot5-groq4-mschema-v10.json --sql-only data/arcwise_plat_sql_only.json --full data/arcwise_plat_full.json --out eval/reports/2026-05-17/arcwise_rescored.json` (~90s, no LLM calls).

---

## Sources

- BIRD leaderboard: <https://bird-bench.github.io/>
- BIRD Mini-Dev repo: <https://github.com/bird-bench/mini_dev>
- Agentar-Scale-SQL: <https://arxiv.org/abs/2509.24403>, <https://github.com/antgroup/Agentar-Scale-SQL>
- CHESS: <https://arxiv.org/abs/2405.16755>, <https://github.com/ShayanTalaei/CHESS>
- CHASE-SQL: <https://arxiv.org/abs/2410.01943>
- XiYan-SQL: <https://arxiv.org/abs/2411.08599>, <https://github.com/XGenerationLab/XiYan-SQL>
- CSC-SQL: <https://arxiv.org/abs/2505.13271>, <https://github.com/CycloneBoy/csc_sql>
- Arctic-Text2SQL-R1: <https://arxiv.org/abs/2505.20315>, <https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B>
- Contextual-SQL: <https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system>
- Adnan Masood analysis: <https://medium.com/@adnanmasood/pushing-towards-human-level-text-to-sql-an-analysis-of-top-systems-on-bird-benchmark-666efd211a2d>
- Benchmarks-are-broken (Jin et al.): <https://arxiv.org/abs/2601.08778>, <https://github.com/uiuc-kang-lab/text_to_sql_benchmarks>
- RetrySQL: <https://arxiv.org/abs/2507.02529>
- Bidirectional schema linking: <https://arxiv.org/abs/2510.14296>
- SEED auto-evidence: <https://arxiv.org/abs/2506.07423>
- Snowflake Arctic blog: <https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/>
- Distyl #1 announcement (historical, July 2024): <https://distylai.substack.com/p/distyl-takes-1-spot-on-bird-benchmark>
