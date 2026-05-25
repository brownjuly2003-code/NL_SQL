## TOP-10 Progressive NL→SQL Projects

| # | Project | Type | Key idea (1 sentence) | Why progressive | BIRD/Spider score | Stars/Activity | Link |
|---|---|---|---|---|---|---|---|
| 1 | **ReViSQL** | research | Achieves human-level accuracy by training with RLVR on a small **expert-verified** dataset (BIRD-Verified, 2.5k samples) instead of complex agent pipelines. | First to exceed proxy human performance (92.96%) on BIRD; proves that **data quality > architectural complexity** for the final gap. | BIRD Mini-Dev (expert-verified) **93.2%** EX; Spider 2-Snow **55.6%** EX | Paper only (Mar 2026); no public code yet | https://arxiv.org/abs/2603.20004 |
| 2 | **Agentar-Scale-SQL** | research/oss | Orchestrated test-time scaling combining **internal** (RL-enhanced reasoning), **sequential** (iterative refine), and **parallel** (diverse synthesis + tournament selection) scaling. | BIRD leaderboard #1 (as of Nov 2025); general-purpose plug-and-play framework that improves with more compute. | BIRD test **81.67%** EX; dev **74.90%** EX | Active (Sep 2025); 32B model & tools open-sourced on HF/ModelScope | https://arxiv.org/abs/2509.24403 |
| 3 | **Arctic-Text2SQL-R1** | research/oss (Snowflake) | RL with a **simple execution-correctness reward** (no complex shaping) to train SQL-specific reasoning models at 7B/14B/32B scales. | 7B model outperforms prior 70B-class systems; shows execution-based RL is enough for strong SQL reasoning. | BIRD test **71.83%** EX (32B), **70.04%** (14B), **68.47%** (7B) | Active (May 2025); open weights on HuggingFace | https://arxiv.org/abs/2505.20315 |
| 4 | **XiYan-SQL** | research/oss (Alibaba) | **Multi-generator ensemble** (ICL + SFT candidates) with **M-Schema** representation and a learned selection model. | Long-time BIRD top-3; open-weight family (3B–32B) with 100k+ downloads; defines the "schema-as-context" SOTA. | BIRD test **75.63%** EX (ensemble); single model **69.03%**; Spider test **89.65%** | Very active (2024–2025); XiYanSQL-QwenCoder series on HF/ModelScope | https://github.com/alibaba/XiYan-SQL |
| 5 | **CHASE-SQL** | research (Google Cloud / Stanford) | Multi-path reasoning via divide-and-conquer + query-plan CoT + instance-aware synthetic few-shot, with a **fine-tuned pairwise candidate selector**. | Set the multi-agent/generate-then-select template; ICLR 2025; selector beats majority voting by ~6pp. | BIRD dev **73.01%**; test **73.0%** EX | Paper (Oct 2024); code not public yet | https://arxiv.org/abs/2410.01943 |
| 6 | **OmniSQL** | research/oss (Renmin / ByteDance) | Scalable synthesis of **SynSQL-2.5M** (2.5M samples, 16k DBs) to fine-tune strong open-source coder LLMs for SQL. | First million-scale synthetic SQL dataset; demonstrates data scaling laws for text-to-SQL; strong generalization. | BIRD test **72.05%** EX (32B); **67.97%** (7B); Spider test **88.9–89.8%** (maj vote) | Active (Mar 2025); code, data, models on HF/ModelScope | https://github.com/RUCKBReasoning/OmniSQL |
| 7 | **SkyRL-SQL** | research/oss (NovaSky / UC Berkeley) | **Multi-turn RL** pipeline where the model probes the DB, receives execution feedback, and refines SQL across turns. | Trained on only **653 samples** beats GPT-4o and o4-mini; proves interactive RL with simple rewards > massive SFT. | Spider dev **82.4%** EX (multi-turn eval); surpasses GPT-4o on SQL benchmarks | Active (May 2025); open RL framework on GitHub | https://github.com/NovaSky-AI/SkyRL |
| 8 | **Alpha-SQL** | research/oss (HKUST) | **Zero-shot MCTS** for progressive SQL construction using LLM-as-Action-Model and self-supervised execution consistency rewards. | No fine-tuning needed; boosts Qwen2.5-32B to **69.7%** BIRD dev, beating GPT-4o zero-shot; plug-in framework. | BIRD dev **69.7%**; test **70.26%** EX (zero-shot) | Open source (ICML 2025); full code on GitHub | https://github.com/HKUSTDial/Alpha-SQL |
| 9 | **CHESS** | research/oss (Stanford) | Four-agent pipeline: **Information Retriever → Schema Selector → Candidate Generator → Unit Tester** with budget-aware configuration. | Highly influential baseline; on corrected BIRD dev jumps to **81%** EX, showing robustness to annotation noise. | BIRD test **71.10%** EX (best config); dev **81%** (corrected); Spider dev **87.2%** | Open source (May 2024); 4-agent framework code available | https://arxiv.org/abs/2405.16755 |
| 10 | **WrenAI** | product/oss (Canner) | **Open context layer / semantic layer** for agents over business data: MDL, memory, governed execution, agent SDKs. | Represents the leading open-source **GenBI platform** direction; 15k+ stars, weekly releases, LLM-agnostic. | N/A (product; no standard academic benchmark) | Very active (2024–2026); 15k+ GitHub stars, 1.5k+ Discord | https://github.com/Canner/WrenAI |

---

## Applicability to NL_SQL (D:/NL_SQL)

For each project, 1–2 lines: **steal-able for NL_SQL?** (yes/no/maybe + what specifically).
Особенно интересует: что может пробить free-tier ceiling 92.5% → 93–95% БЕЗ paid OR / без fine-tune.

1. **ReViSQL** — **Maybe.** The core insight (clean verified data + inference-time reconciliation/voting) is steal-able; NL_SQL could build a **"verified few-shot index"** from its own audit_rescore corrections and use execution-based reconciliation instead of simple majority vote. RLVR itself is off-limits without training budget.
2. **Agentar-Scale-SQL** — **Yes.** NL_SQL already votes, but lacks **sequential scaling** (iterative refinement) and **tournament selection**. Adding a "critique → revise → re-select" loop with the existing free reasoning models could squeeze extra points without new API costs.
3. **Arctic-Text2SQL-R1** — **Maybe.** If NL_SQL can self-host a 7B/32B model locally, it could replace the primary CSG generator; but on BIRD Mini-Dev (n=200) a raw 7B model is unlikely to beat 92.5% without agentic wrapping. Good for latency, not a ceiling breaker alone.
4. **XiYan-SQL** — **Yes.** The **M-Schema** representation and dense schema-card retrieval are directly steal-able for the `render_schema` node; also the multi-generator ensemble idea (generate with both Mistral and a reasoning model, then select) fits the existing voting layer.
5. **CHASE-SQL** — **Yes.** The **instance-aware synthetic few-shot** generator and the **fine-tuned pairwise selector** are the highest-impact ideas. NL_SQL could build a small preference dataset from its 185 correct runs and train a lightweight selector (even a classifier) to pick the best SQL among candidates instead of pure majority voting.
6. **OmniSQL** — **Maybe.** SynSQL-2.5M is open; NL_SQL could index it with embeddings and retrieve **synthetic CoT examples** as few-shot demonstrations, improving coverage without human annotation. Not a direct inference fix, but enriches the retrieval bank.
7. **SkyRL-SQL** — **Yes.** The multi-turn "probe → execute → reflect" loop mirrors NL_SQL's `execute → reflect`, but SkyRL shows that **training the model to interact** (even 4 turns) beats single-shot. NL_SQL can steal the prompt structure and turn budget: force the generator to emit intermediate test SQLs before the final query.
8. **Alpha-SQL** — **Yes (high potential for $0).** MCTS with self-supervised execution rewards is a **training-free** way to boost a small open-source model. NL_SQL could wrap Mistral (or a local Qwen) in an MCTS loop for critical/hard questions, trading latency for accuracy without any fine-tune or paid API.
9. **CHESS** — **Yes.** The **Unit Tester** agent is missing from NL_SQL's graph. Adding a dedicated node that writes unit-test assertions (e.g., "check that the count matches the question's filter") and validates execution outputs could catch semantic errors before voting.
10. **WrenAI** — **Maybe.** The **Modeling Definition Language (MDL)** and semantic-layer concepts are architecture-heavy for a pet project, but the idea of a **governed, versionable context layer** could inspire a lightweight "schema enrichment" step (e.g., git-friendly business descriptions for columns).

**Best bets to breach 93% on $0:**
- **Inference-time scaling:** Agentar-style sequential refinement + Alpha-SQL-style MCTS on hard questions.
- **Selection:** Replace majority vote with a learned preference model (CHASE-SQL style) or execution-reconciliation (ReViSQL style).
- **Unit testing:** Add CHESS-style unit-tester node to catch false positives before they reach the vote.

---

## Sources searched

- **BIRD leaderboard** — https://bird-bench.github.io/ (snapshot fetched, rankings up to May 2026)
- **Spider 2.0 leaderboard** — https://spider2-sql.github.io/ (via arXiv papers citing ReFoRCE/Spider-Agent scores)
- **arXiv direct fetches:** ReViSQL (2603.20004), Agentar-Scale-SQL (2509.24403), Arctic-Text2SQL-R1 (2505.20315), CHASE-SQL (2410.01943), Alpha-SQL (2502.17248), OmniSQL (2503.02240), CHESS (2405.16755), BIRD-Critic / SWE-SQL (2506.18951)
- **Papers with Code** — text-to-sql task searches; verified publication dates and code availability
- **GitHub direct checks:** alibaba/XiYan-SQL, XGenerationLab/XiYan-SQL, RUCKBReasoning/OmniSQL, HKUSTDial/Alpha-SQL, NovaSky-AI/SkyRL, Canner/WrenAI, vanna-ai/vanna (archived Mar 2026)
- **Industry blogs:** Snowflake Arctic-Text2SQL-R1 blog (May 2025), WrenAI vs Vanna comparison (Dec 2025), Defog SQLCoder-70B release notes (Jan 2024)

---

## Gaps / unknowns

- **BIRD Mini-Dev corrected benchmarks:** ReViSQL reports on Arcwise-Plat-Full/SQL (expert-verified subsets of BIRD Mini-Dev). No public leaderboard tracks these corrected subsets; NL_SQL's 92.5% is on the original (noisy) Mini-Dev, so direct comparison to ReViSQL's 93.2% is apples-to-oranges.
- **Free-tier evaluation of Arctic-Text2SQL-R1 / OmniSQL on Mini-Dev:** Both report full BIRD dev/test; their exact performance on the n=200 Mini-Dev is unpublished.
- **DeepSeek-R1 / QwQ-32B distilled for SQL:** Several papers mention strong reasoning models, but no dedicated BIRD Mini-Dev score with agentic wrapping was found.
- **ReFoRCE on BIRD:** ReFoRCE is Spider 2.0 SOTA (35.83% Snow / 36.56% Lite), but its BIRD performance is not reported in the extracted sources.
- **Updated SQLCoder family (2025):** Defog's SQLCoder-70B is from Jan 2024; no 2025 successor evaluated on BIRD was found.
- **Inference cost vs. accuracy Pareto frontier for free tier:** Most SOTA methods (Agentar, CHASE, XiYan) rely on paid models or fine-tuned selectors. A systematic study of "what 7B open model + MCTS + voting can reach on Mini-Dev" is missing.
