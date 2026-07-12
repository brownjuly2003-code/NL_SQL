# Quality Levers Research — What Is Left After the Levers Died

**Date:** 2026-07-12 (evening, after the lever-exhaustion pass)
**Question:** the 2026-07-12 measurement day killed eight levers (model swap within
reach, 2- and 3-model voting, weak and strong judge-selectors, retry-on-empty,
heuristic critique, LLM condition-coverage verifier — full table in the session
log; earlier passes killed DAC, M-Schema, column descriptions, self-consistency,
schema narrowing, compact prompts). The reproducible single-run number is 61.5%
(codestral, config E, n=200). Is there anything left that can move it on a
free stack — no fine-tuning, no logits access, no candidate selection?

Two research axes: (A) training-free techniques published or missed through
July 2026; (B) free API tiers carrying models plausibly stronger than codestral.

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

## C. Ranked shortlist

1. **Gemini 3 Flash as generator** (needs: an AI Studio API key — a decision,
   not money). Near-zero engineering: `_openai_compat.py` already speaks the
   OpenAI protocol and Gemini exposes an OpenAI-compatible endpoint; add a
   provider entry, run config E n=200 in one day within free limits.
   Highest variance of all options: could be anywhere from parity to a real
   jump. **The pilot rule is binding** — browser-Sonnet went +16.6 at n=30 to
   −3.0 at n=200; only the full slice counts.
2. **Question-driven value retrieval** (needs: nothing — local code + one
   Mistral run). Best-evidenced technique lever; modest honest estimate
   (+0.5–2 pp); composes with #1 — worth measuring on codestral first so the
   two levers stay attributable.
3. **Qwen3 Coder 480B via OpenRouter free** (needs: account/key + patience or
   $10 once). Only if #1 disappoints and the endpoint passes a canary.
4. **Devstral probe** (needs: nothing). One cheap run only if bundled with
   other work; prior is low.

Not worth runs: DecoSearch-style decomposition, reflective refinement,
semantic post-repair, SEED — table A2.

If #1–#3 all land at parity, the free-stack ceiling thesis (~61–62% on this
gold) gets its final confirmation, and the remaining value is the ceiling-anatomy
write-up itself — now reinforced by the 61.1% BIRD-Train defect rate (A3).

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
