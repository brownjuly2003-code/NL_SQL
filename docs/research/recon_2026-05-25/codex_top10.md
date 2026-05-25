## TOP-10 Progressive NL→SQL Projects

| # | Project | Type | Key idea (1 sentence) | Why progressive | BIRD/Spider score | Stars/Activity | Link |
|---|---|---|---|---|---|---|---|
| 1 | AskData + GPT-4o / Automatic Metadata Extraction | research/product | Автоматически строит missing metadata через profiling, query-log analysis и SQL-to-text generation. | Точно бьет в bottleneck NL_SQL: не генерация SQL, а восстановление скрытых business/domain facts. | BIRD EX dev 77.64 / test 81.95; R-VES 76.31; human 92.96 | Paper v1 2025-05-26, v2 2025-06-03; BIRD entry 2025-12-16 | https://arxiv.org/abs/2505.19988 |
| 2 | Agentar-Scale-SQL | research/model | Orchestrated test-time scaling: RL intrinsic reasoning + iterative refinement + diverse synthesis + tournament selection. | Самая сильная публично описанная scaling architecture на BIRD, полезна даже без fine-tune как routing/voting pattern. | BIRD EX dev 74.90 / test 81.67; R-VES 77.00 | arXiv v6 2025-12-10; HF model 8 commits, updated ~2026-01 | https://arxiv.org/abs/2509.24403 |
| 3 | PExA | research | Разбивает сложный запрос на параллельные atomic SQL "test cases", затем собирает финальный SQL из покрытых evidence. | Новый Spider 2.0-style подход: semantic coverage вместо одного monolithic generation pass. | Spider 2.0-Snow 70.20 | Submitted 2026-04-24; accepted ACL 2026; code/stars not verified | https://arxiv.org/abs/2604.22934 |
| 4 | XiYan-SQL | research/oss/product | Multi-generator ensemble + M-Schema + refiner + trained selector. | Практичный open Alibaba stack: M-Schema, SQL-specialized QwenCoder, MCP server, training framework. | BIRD EX dev 73.34 / test 75.63; R-VES 71.41; Spider test 89.65 | GitHub ~1k stars, 163 commits; 2025-11 BIRD-CRITIC update | https://github.com/XGenerationLab/XiYan-SQL |
| 5 | Contextual-SQL | oss/research | Open local Text-to-SQL BIRD pipeline centered on contextual few-shot/schema retrieval. | High BIRD score with open implementation; useful comparator for local/free-ish pipelines. | BIRD EX dev 73.50 / test 75.63; R-VES 70.02 | Blog/repo activity 2025; stars unverified | https://github.com/ContextualAI/bird-sql |
| 6 | ReFoRCE | oss/research | Database compression + LLM schema linking + self-refinement + majority vote + execution-guided column exploration. | Best stealable Spider 2.0 agent loop; column exploration is directly portable to SQLite Mini-Dev. | Spider 2.0-Snow current 62.89 with o3; Lite 55.21; paper reports 35.83/36.56 earlier | GitHub 138 stars, 38 commits; 2025-07 schema-link update | https://github.com/Snowflake-Labs/ReFoRCE |
| 7 | Arctic-Text2SQL-R1 | research/model | SQL-specialized Qwen-based models trained with GRPO and execution/syntax rewards. | Strong open SQL fine-tune family; proves simple verifiable rewards work well for SQL. | BIRD single-model: 32B test 73.84, 14B 72.22, 7B 70.43 | Paper 2025-05-22; blog 2025-05-29; 7B HF model open | https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B |
| 8 | Databricks RLVR 32B | research/industry | Qwen2.5-Coder-32B trained with reinforcement learning from verifiable execution rewards. | Shows RLVR can beat agentic systems in single-model mode; important ceiling signal for future free/open models. | BIRD single-model test 73.56 no self-consistency / 75.68 with self-consistency | arXiv 2025-09-25; Databricks research/blog 2025 | https://arxiv.org/abs/2509.21459 |
| 9 | OmniSQL | research/model | Synthesizes large-scale high-quality Text-to-SQL data, then trains 7B/14B/32B SQL models. | Data-centric path: better synthetic supervision, not just bigger agents. | BIRD EX 32B dev 69.23 / test 72.05; 7B dev 69.04 / test 67.97 | arXiv 2025-03-04; stars unverified | https://arxiv.org/abs/2503.02240 |
| 10 | WrenAI | oss/product | Semantic context layer/MDL compiles governed business definitions for Text-to-SQL/Text-to-chart agents. | Most relevant product-side idea: make business semantics explicit instead of relying on raw schema RAG. | No public BIRD/Spider score verified | ~15.1k stars; active 2026-05 releases/scans | https://github.com/Canner/WrenAI |

## Applicability to NL_SQL (D:/NL_SQL)

1. **AskData** — yes: steal automatic metadata extraction from SQLite profiling — value distributions, join candidates, enum meanings, generated column/table descriptions. Highest no-paid/no-fine-tune upside, directly targets your human-expert gap.

2. **Agentar-Scale-SQL** — maybe: не копировать paid scaling volume, но взять staged scaling pattern — дешёвые diverse drafts → critique → tournament только на hard/ambiguous cases.

3. **PExA** — yes: генерировать малые "coverage probes" по NL-интенту, исполнять их, кормить наблюдаемые row/column evidence в финальный SQL prompt. Портируется без fine-tune.

4. **XiYan-SQL** — yes: m-schema уже есть; следующий steal — entity-aware example selection (избегает literal match overfitting) и refiner/selector разделение.

5. **Contextual-SQL** — maybe: использовать как regression comparator для local-style retrieval и few-shot packing; точный gain требует code inspection.

6. **ReFoRCE** — yes: добавить deferred column exploration только при vote disagreement или execution mismatch; cheap, no fine-tune, прямо применимо к SQLite Mini-Dev.

7. **Arctic-Text2SQL-R1** — maybe/no для current free-tier: fine-tune сейчас не нужен, но взять reward taxonomy для critique labels: syntax-valid, execution-valid, result-shape-valid, semantic-risk.

8. **Databricks RLVR** — no immediate без fine-tune; yes как future recipe если NL_SQL создаст verified Mini-Dev/train corrections из 15 ошибок.

9. **OmniSQL** — maybe: генерировать synthetic hard variants вокруг 15 failures, но только если каждый synthetic SQL исполним и верифицирован.

10. **WrenAI** — yes: добавить небольшой semantic layer для metrics, date windows, canonical joins, synonyms и forbidden joins; может двинуть 92.5% → 93-95% без paid models.

## Sources searched

- https://bird-bench.github.io/
- https://spider2-sql.github.io/
- https://github.com/bird-bench/mini_dev
- Queries: `BIRD benchmark leaderboard Text-to-SQL 2025 CHASE-SQL score EX`, `BIRD Mini-Dev leaderboard AskData GPT-4o 81.95 2025 text-to-SQL`, `Spider 2.0 leaderboard text-to-SQL 2025`, `Agentar-Scale-SQL arxiv 2025 BIRD text-to-SQL GitHub`, `CHASE-SQL arxiv 2410.01943 BIRD 76.02 GitHub`, `XiYan-SQL GitHub stars last commit 2026 BIRD 75.63`, `ReFoRCE text-to-SQL GitHub stars last commit 2025`, `Snowflake Arctic-Text2SQL-R1 BIRD 73.84 2025 HuggingFace`, `Databricks RLVR 32B BIRD 75.68 text-to-SQL July 2025`, `OmniSQL GitHub BIRD 72.05 text-to-SQL 2025 stars`, `Vanna AI GitHub stars last commit 2026 text-to-SQL`, `WrenAI GitHub stars last commit 2026 text-to-SQL semantic layer`, `Defog SQLCoder GitHub stars last commit 2025 text-to-SQL benchmark`, `Contextual-SQL GitHub BIRD 75.63 text-to-SQL 2025 stars`

## Gaps / unknowns

- GitHub exact latest commit dates не верифицированы для каждого репо из indexed pages; использованы видимые GitHub/HF activity, release/news dates или paper dates.
- Vanna AI популярен (~23.4k stars) но archived на 2026-03-29; исключён из TOP-10, несмотря на product relevance.
- SQLCoder/Defog имеет ~3.9k stars и sql-eval activity в 2025, но current BIRD/Spider SOTA не верифицирован; исключён как исторически важный, не progressive-current.
- CHASE-SQL архитектурно важен, но текущий BIRD score 76.02 уже не топ, и public code/stars не верифицированы.
- Spider 2.0 leaderboard быстро меняется в 2026; несколько top систем без public paper/code, поэтому приоритет PExA/ReFoRCE как inspectable.
