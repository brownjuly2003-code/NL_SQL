# Quality Levers Research — What Is Left After the Levers Died

**Date:** 2026-07-12 (evening, after the lever-exhaustion pass)
**Question:** the 2026-07-12 measurement day killed eight levers (model swap within
reach, 2- and 3-model voting, weak and strong judge-selectors, retry-on-empty,
heuristic critique, LLM condition-coverage verifier — full table in the session
log; earlier passes killed DAC, M-Schema, column descriptions, self-consistency,
schema narrowing, compact prompts). The reproducible single-run number is 61.5%
(codestral, config E, n=200). Is there anything left that can move it on a
free stack — no fine-tuning, no logits access, no candidate selection?

Three research passes: (A) training-free techniques published or missed through
July 2026; (B) free API tiers carrying models plausibly stronger than codestral;
(C) a completeness sweep over established named systems (DIN/DAIL/C3/MAC/PET/
TA/E-SQL/RSL/MCS/CHASE/OpenSearch/Alpha/XiYan/SuperSQL + the NL2SQL360 taxonomy),
decomposed into components and filtered by the constraints. (D) is the resulting
ranked shortlist.

---

## A. Techniques — one live candidate, several confirmed-dead-by-analogy

### A1. Question-driven value retrieval (CHESS-style) — the only well-evidenced live lever

CHESS ([arXiv:2405.16755](https://arxiv.org/html/2405.16755v1)) ablation: removing
its entity & context retrieval module (LSH + semantic search of *actual DB cell
values* matching question tokens, injected into the prompt) costs ~5 pp EA on
BIRD dev. Training-free, no logits, single candidate — fits every constraint.

Honest expectation for our stack, lower than CHESS's ablation:

- Our schema cards **already carry static per-column top-K sample values**
  (`schema_index/introspector.py`, top-3 + extended tail mixture). CHESS's module
  is different — it is *question-driven*: it finds the exact rare literal the
  question mentions and says which column holds it (e.g. "Riverside" lives in
  `schools."District Name"` as `'Riverside Unified'`, not in `City`). Static
  top-K frequent samples cannot do that for rare values.
- Our dominant miss class (51/77: same result size, wrong content) is led by
  extra/lost conditions and wrong join keys — only part of it is
  wrong-literal/wrong-column-for-a-value, the part this lever targets. Historic
  residue examples squarely in scope: qid 25 (`City = 'Riverside'` vs
  `District Name LIKE 'Riverside%'`), qid 1275 (value tokens `-`/`+-` vs
  `negative`/`0` across tables), qid 743 (`'Marvel Comics'`).
- Prompt grows → pays attention rent (the top-of-prompt rule from the 07-11
  pass). Injection must be short and near the question.

Estimate: **+0.5 to +2 pp**, engineering ~half a day (substring/BM25 scan over
sampled cell values per question, inject as grounding lines), one live n=200
Mistral run to measure. No new quota, no keys, no money.

### A2. Confirmed dead or dead-by-analogy — do not spend runs on these

| Technique | Source | Why not |
|---|---|---|
| DecoSearch (routing + DAG decomposition) | [arXiv:2606.17821](https://arxiv.org/html/2606.17821v1), 2026-06 | +0.93 pp over CHESS; its ablation attributes the value to *routing simple questions away from decomposition* — our flat DAC already measured −6.5, and there is nothing to route to |
| Reflective self-refinement | [arXiv:2601.06678](https://arxiv.org/pdf/2601.06678), 2026-01 | Mechanically the same channel as our measured-dead heuristic critique (±0) and LLM verifier (precision 0.53/0.49) |
| Post-generation repair of semantic errors | MapleRepair, [arXiv:2501.09310](https://arxiv.org/html/2501.09310v2) | The paper's own conclusion: rule/LLM repair fixes format/convention errors well (74% of format class) but semantic errors — our entire miss class — "depend on model capability" and mostly do not repair |
| ReViSQL (93%+ "human-level") | [arXiv:2603.20004](https://arxiv.org/html/2603.20004v2), 2026-03 | RLVR fine-tuning of Qwen3-235B + up to 129 candidates with voting — violates every constraint at once |
| SEED auto-evidence | [arXiv:2506.07423](https://arxiv.org/pdf/2506.07423) | Generates the `evidence` field when absent; BIRD Mini-Dev ships gold evidence and it is already at the top of our prompt |

Unmeasured anywhere, no external evidence either way: execution-plan CoT,
question rewriting before generation, targeted micro-prompts per error class
(output-column completeness, yes/no answer format, LIMIT discipline — the v18
audit priced these at 1–2 questions each on a different stack). Legal candidates,
but each costs a live run against an expected gain of ~1 question; only worth
bundling with a run that is happening anyway.

### A3. Side-fact that strengthens the ceiling story

ReViSQL's expert verification found defects in **61.1% of BIRD Train instances**
(their BIRD-Verified set; verified data alone was worth +8–14 pp in their
training). Independent of Jin et al.'s 52.8% on Mini-Dev — two teams, two splits,
the same conclusion: a large share of the residual above ~60% on uncorrected
gold is annotation noise, not pipeline weakness.

---

## B. Free API tiers, July 2026 — one clear first pick

Provider state (limits verified against provider docs / recent third-party
audits; free-tier terms are volatile — re-check on the day of use):

| Provider | Strongest fit | Free limits | Card? | Verdict |
|---|---|---|---|---|
| **Google AI Studio** | **Gemini 3 Flash** | 10 RPM · 250K TPM · **1,500 req/day** | No (billing must stay off) | **First pick.** n=200 (+repair calls) fits in ONE day. Family evidence: Gemini-3-Pro 76.6% BIRD, Gemini-SQL2 80.0%; Flash itself unmeasured on BIRD. Pro models left the free tier 2026-04. Free tier may train on prompts — acceptable, BIRD is public |
| **OpenRouter `:free`** | Qwen3 Coder 480B | 20 RPM · **50 req/day** (reportedly 1,000/day after a one-time $10 credit) | No for 50/day | Second pick. Strongest open coding model for free, but n=200 ≈ 4–6 days at 50/day; endpoint stability reports conflict — canary first. DeepSeek free endpoints are gone |
| Mistral (existing key) | Devstral | same free tier we already use | No | Cheap probe, low prior — agentic-coding tune, no SQL-semantics evidence over codestral |
| Cerebras | zai-glm-4.7 / gpt-oss-120b | 1M tok/day · 30 RPM, **8,192-token context cap** on free tier | No | Context cap collides with our 4–8K prompts; model list volatile |
| Groq | Llama 4 / QwQ / R1-distill | 30 RPM · **6,000 TPM** · 1,000 RPD | No | 6K TPM ≈ one of our requests per minute; models not plausibly above codestral for SQL |
| GitHub Models | o-series, GPT | 10 RPM · **50 RPD**, hard cap **8,000 input tokens** | Copilot plan | Input cap rejects our prompts |

BIRD numbers found for context: Gemini-SQL2 (on Gemini 3.1 Pro) 80.04%
single-model; raw Gemini-3-Pro 76.58%; Claude Opus 4.6 ~70.1%;
Qwen3-Coder-30B inside the DeepEye-SQL framework 73.5% dev. No published BIRD
numbers for Gemini Flash variants, Kimi K2, or DeepSeek V3.x as bare generators.

---

## C. Second pass — sweep of established systems (completeness check)

A follow-up sweep over the named, well-described systems of 2023–2026 (DIN-SQL,
DAIL-SQL, C3, MAC-SQL, PET-SQL, TA-SQL, E-SQL, RSL-SQL, MCS-SQL, CHASE-SQL,
OpenSearch-SQL, Alpha-SQL, SQL-o1, XiYan-SQL, SuperSQL) plus the NL2SQL360 /
NL2SQL_Handbook taxonomy, decomposed into components and filtered by our
constraints. Verdict: the taxonomy adds **five legal technique families** beyond
section A, and confirms everything else reduces to channels we already measured.

Legal and genuinely unmeasured on this stack:

| Family | Best source & isolated number | Notes for our stack |
|---|---|---|
| **Instance-aware synthetic few-shot** — an extra LLM call writes 2–3 Q→SQL examples shaped like the test question, replacing retrieved shots | CHASE-SQL Table 4: 57.75 → **67.09 (+9.3)**, single generator, no selection — the strongest legal single-candidate number in the literature | Transfer risk is real: the same table's divide-and-conquer (+6.2 for them) measured **−6.5 here**. Ablations on Gemini 1.5 Pro are priors, not promises |
| **Few-shot selection à la DAIL** — mask schema tokens in the question before embedding; optionally re-rank by SQL-skeleton similarity | DAIL-SQL; MCS-SQL ablation credits masked-question few-shot with **+4.8%**, its largest single component | Our current shots are dense top-3 on the raw question — the upgrade path is concrete and cheap |
| **Question enrichment** — rewrite the question expanding conditions/steps/schema references, appended alongside the original | E-SQL (single-candidate by design): ~**+5% on challenging**; its predicate-augmentation module (−2% overall when removed) is draft-conditioned value grounding | Composes with value retrieval; one extra call per question |
| **Intermediate representation** — symbolic/pandas-like plan first, SQL second | TA-SQL (TALOG module; +21% relative combined with its linking module, GPT-4); OpenSearch-SQL's SQL-Like IR | CoT-family transfer risk on codestral (the DAC precedent) |
| **Calibration hints / error-class micro-prompts** — short bias-correcting rules (extra columns, wrong aggregation, LIMIT discipline, yes/no format) | C3-SQL (~1–2 pts, GPT-3.5 era); our own v18 residue audit priced output-column and answer-format rules at 1–2 questions each | Cheapest of all; rules must be narrow to avoid two-sided regressions |

Confirmed dead-by-equivalence (components map 1:1 onto measured-dead channels):
MAC-SQL (Selector=narrowing, Decomposer=DAC, Refiner=self-refinement), RSL-SQL
(bidirectional linking=narrowing + binary selection + multi-turn correction),
PET-SQL cross-consistency (=voting), Alpha-SQL / SQL-o1 (MCTS = multi-candidate
by construction), DIN-SQL (decomposition + self-correction; only its difficulty
routing is legal, with no isolated evidence), XiYan's fine-tuned parts, and
CHASE's query fixer (=self-refinement) and tournament selector (fine-tuned,
multi-candidate). Deterministic AST post-normalization: no survey shows EA gains
from it — published post-processing wins are all LLM-fixers or execution-guided,
both excluded; at 99% validity the expectation here is ~0.

## D. Ranked shortlist (revised after the second pass)

1. **Gemini 3 Flash as generator** (needs an AI Studio API key — a decision, not
   money). Near-zero engineering: `_openai_compat.py` already speaks the OpenAI
   protocol and Gemini exposes an OpenAI-compatible endpoint. Highest variance;
   **the pilot rule is binding** — only the full n=200 counts.
2. **Question-driven value retrieval** (needs nothing): best-evidenced targeted
   lever, honest estimate +0.5–2 pp. Measure on codestral first for attribution.
3. **DAIL-style few-shot selection** (needs nothing): cheap upgrade of the
   existing retrieval; masked-question variant first, skeleton re-rank only if
   the cheap variant shows signal.
4. **Instance-aware synthetic few-shot** (needs nothing, 2× calls): the largest
   literature number, discounted by the DAC transfer precedent.
5. **Question enrichment** (needs nothing, 2× calls).
6. **Error-class micro-prompts** (needs nothing, one run per bundle).
7. **Intermediate representation / query-plan CoT** — hold on codestral (CoT
   transfer risk), retry on the new generator if #1 lands.
8. **Qwen3 Coder 480B via OpenRouter free** (account/key + patience or $10 once)
   — only if #1 disappoints; canary the endpoint first.
9. **Devstral probe** (needs nothing) — bundle with other work; low prior.

Not worth runs: DecoSearch-style decomposition, reflective refinement, semantic
post-repair, SEED, AST normalization — sections A2 and C.

If the whole list lands at parity, the free-stack ceiling thesis (~61–62% on
this gold) gets its final confirmation, and the remaining value is the
ceiling-anatomy write-up — now reinforced by the 61.1% BIRD-Train defect rate.

---

## Sources

- CHESS: <https://arxiv.org/html/2405.16755v1>
- DecoSearch: <https://arxiv.org/html/2606.17821v1>
- SEED: <https://arxiv.org/pdf/2506.07423>
- MapleRepair error taxonomy: <https://arxiv.org/html/2501.09310v2>
- ReViSQL / BIRD-Verified: <https://arxiv.org/html/2603.20004v2>
- Reflective reasoning for SQL: <https://arxiv.org/pdf/2601.06678>
- DeepEye-SQL (Qwen3-Coder 73.5% dev): <https://arxiv.org/pdf/2510.17586>
- Gemini API rate limits: <https://ai.google.dev/gemini-api/docs/rate-limits>
- Gemini free-tier audits: <https://tokenmix.ai/blog/gemini-api-free-tier-limits>, <https://www.aifreeapi.com/en/posts/gemini-api-rate-limits-per-tier>
- OpenRouter free tier: <https://klymentiev.com/blog/openrouter-free-tier>, <https://costgoat.com/pricing/openrouter-free-models>
- Groq free tier: <https://tokenmix.ai/blog/groq-free-tier-limits-2026>
- Cerebras/Mistral free-tier survey: <https://ianlpaterson.com/blog/free-llm-api-2026/>
- GitHub Models limits: <https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models>
- Gemini-SQL2 on BIRD: <https://aiweekly.co/alerts/googles-gemini-sql2-tops-bird-text-to-sql-at-8004>, <https://byteiota.com/gemini-sql2-text-to-sql-bird-benchmark/>
- CHASE-SQL (Table 4 single-generator ablations): <https://arxiv.org/abs/2410.01943>
- DAIL-SQL: <https://arxiv.org/abs/2308.15363>, <https://github.com/BeachWang/DAIL-SQL>
- MCS-SQL (few-shot selection ablation): <https://arxiv.org/html/2405.07467v1>
- E-SQL question enrichment: <https://arxiv.org/abs/2409.16751>
- TA-SQL: <https://arxiv.org/abs/2405.15307>
- OpenSearch-SQL: <https://arxiv.org/html/2502.14913v1>
- C3-SQL: <https://arxiv.org/abs/2307.07306>; DIN-SQL: <https://arxiv.org/abs/2304.11015>; MAC-SQL: <https://arxiv.org/abs/2312.11242>; PET-SQL: <https://arxiv.org/abs/2403.09732>; RSL-SQL: <https://arxiv.org/abs/2411.00073>
- Taxonomy/surveys: <https://github.com/HKUSTDial/NL2SQL_Handbook>, <https://arxiv.org/html/2406.08426v5>, <https://arxiv.org/html/2407.15186>
