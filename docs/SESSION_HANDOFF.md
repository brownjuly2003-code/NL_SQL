# NL_SQL — Session Handoff (2026-05-10, stage 6 baseline live)

> Read this first when picking up. It's the single source of truth for
> "where we stopped" and "what to do next". When you take action, update
> this file before you stop again.

---

## Current state in 30 seconds

- **Repo:** `D:\NL_SQL\` on `main`
- **HEAD:** see `git log -1 --oneline` (stage 6 eval harness committed)
- **Tests:** 169/169 passing, ruff clean, mypy strict clean (49 src files)
- **Stages closed (autonomous): 1, 2, 3, 4, 5, 6 (config A only), 9** + provider adapter expanded with Groq
- **Stages waiting: 6 (configs B–E)**, then 7+
- **Hard budget:** still $0. All live providers tested are free-tier.

Live signals:
- Schema recall@5 on Chinook (`mistral-embed`) = **5/5 (100%)** — `scripts/smoke_schema_recall.py`
- Full pipeline on Chinook (`codestral-latest` + `mistral-large-latest`) = **5/5 succeeded** — `scripts/smoke_pipeline.py`
- Eval harness baseline (config A, 50 BIRD Mini-Dev SQLite, codestral-latest, seed=0):
  - **EA = 46.0%** (simple 57.1% / moderate 45.5% / challenging 35.7%)
  - Validity = 96.0%, Schema Recall@k = 98.0% (k = full schema), Empty-result = 6.0%
  - Latency P50 = 1.3s, P95 = 37s (Mistral free-tier rate-limit backoff on 2 calls)
  - Tokens P50 = 4 742, P95 = 10 055; wall time 413s
  - **Above the week-3 hard checkpoint of EA ≥ 35%** → continue tuning loop, no scope-down.
  - Reference: GPT-4 zero-shot on Mini-Dev SQLite = 47.8% (BIRD leaderboard).
  - Artefacts: `eval/reports/2026-05-10/A_full_schema.json` + `index.html`.

## How to start the next session

```powershell
# 1. Sanity check the repo is still green
uv run ruff check src tests scripts
uv run mypy src
uv run pytest

# 2. Read this file + 02_architecture_v2.md + 03_eval_methodology.md
#    Those three docs are the spec; everything below is workflow.

# 3. Pick the next deliverable from "Next session" section below.
```

Then say: *"Продолжай stage 6 — eval harness."*

## What's done (just to anchor)

| Stage | Module | Tests | Notes |
|---|---|---|---|
| 1 | `src/nl_sql/api/`, `src/nl_sql/config/`, `src/nl_sql/llm/providers/` | 21 | FastAPI /healthz, 4 providers, factory |
| 2 | `src/nl_sql/db/`, `scripts/`, `docker-compose.yml` | 10 | read-only role, registry, download script. Chinook + 11 BIRD DBs downloaded + registered. |
| 3 | `src/nl_sql/schema_index/` | 27 | introspector → chunker → indexer (Chroma) → retriever (FK 1-hop, table_budget). Live recall@5 = 100% on Chinook. |
| 4 | `src/nl_sql/agent/` | 29 | LangGraph 6-node pipeline + repair_once + structured-output JSON parser + 5/5 live smoke on Chinook. |
| 5 | `src/nl_sql/execution/` | 31 | sqlglot AST guard, 3-layer defence, error taxonomy |
| 6 (cfg A) | `src/nl_sql/eval/` | 38 | dataset loader, EA + Schema Recall@k metrics, full_schema runner, JSON+HTML report writer. Live baseline: see `eval/reports/<date>/`. |
| 9 | `src/nl_sql/render/` | 14 | deterministic chart picker, no LLM |

Live API status (with keys from `.env`):
- Mistral `codestral-latest` — works, ~3-13s/req depending on prompt size, free tier
- Mistral `mistral-embed` — works (stages 3 + 4 live)
- Mistral `mistral-large-latest` — works for caption (hit a 429 once on the 5th smoke question; explain_trace falls back gracefully)
- Groq `llama-3.3-70b-versatile` — works, sub-second, free tier
- GitHub Models `openai/gpt-4o-mini` — **401 Unauthorized** (PAT lacks `models:read` scope)

## Open issues

### 1. BIRD Mini-Dev download — FIXED (Google Drive via gdown)

`scripts/download_data.py bird-mini-dev` works. 11 SQLite DBs in
`data/bird_mini_dev/MINIDEV/dev_databases/` and registered as `bird_<db>`.

### 2. GitHub Models PAT needs `models:read` scope (UNCHANGED)

Current PAT lacks `models:read`. To enable, generate a new fine-grained PAT
at <https://github.com/settings/tokens?type=beta> with "Models — Read".
Not blocking — Groq is the active default frontier.

### 3. Ollama is not installed yet (UNCHANGED)

`winget install Ollama.Ollama` then `ollama pull qwen2.5-coder:7b-instruct`.
Not blocking until stage 11 bakeoff.

### 4. Stage 4 caveats (UNCHANGED but now scoped to non-A configs)

- **`fewshot_qsql` collection has zero records** — config D needs BIRD
  *train* split (NEVER dev — see `03_eval_methodology.md` §5). Config A
  doesn't use fewshot, so this isn't blocking the first eval number.
- **Business-hint glossary is empty** — `to_chunks(..., business_hints={})`
  is wired but no glossary file. Optional ablation in §7.2.
- **`mistral-large-latest` caption rate-limited under load** — graceful
  fallback to error sentence; consider switching caption to Groq's free
  llama-3.3-70b if rate-limit becomes recurring under full eval load.

### 5. Stage 6 caveats (NEW)

- **Only configuration A is implemented.** B/C/D/E exist as enum members
  and `run_config_*` stubs that raise `NotImplementedError`. Adding them
  is mechanical (config C ≈ existing pipeline minus repair, config E =
  full pipeline) — see `runner.py` for the slot.
- **No diskcache yet.** Each eval call hits Mistral live, so re-running
  the same 50 examples doubles the API spend. `03_eval_methodology.md`
  §6.2 calls for `(provider, model, prompt_hash) → response` cache; add
  before scaling to 250 dev split.
- **No CI smoke-eval cassettes.** `03_eval_methodology.md` §6.1 wants
  vcr.py-style replay; not wired up. Live runs only for now.

## Next session — recommended order

### Step A — Configurations C/D/E

Implement runner equivalents that build the existing LangGraph pipeline
with the right `PipelineConfig`. Config C wires retrieval+FK already in
place; D needs the few-shot pool; E flips repair on. Track each new
config alongside A in the same HTML report.

Order of operations:
1. `eval/runner.run_config_c` — reuses `build_pipeline` with
   `fewshot_top_k=0`, then strips repair via `repair_attempted=True`
   in the initial state (the cheapest "no-repair" knob without changing
   the graph).
2. BIRD *train* split download → `data/bird_train/` + index into Chroma
   `fewshot_qsql` (CI test `test_no_dev_in_fewshot` to enforce hygiene).
3. `run_config_d` once the few-shot pool exists.
4. `run_config_e` last — uses the full pipeline as-is.

### Step B — Hard checkpoint (week 3 of original roadmap)

Per `02_architecture_v2.md` §11 step 7: if EA < 35% → scope-down protocol
(`§12`). If ≥ 35%, continue tuning loop.

## Key files map (for orientation)

```
D:\NL_SQL\
├── docs/
│   ├── 00_task.md                ← постановка
│   ├── 01_architecture.md        ← v1 historical
│   ├── 02_architecture_v2.md     ← ACTIVE BASELINE
│   ├── 03_eval_methodology.md    ← central artifact
│   └── SESSION_HANDOFF.md        ← you are here
├── src/nl_sql/
│   ├── api/main.py               ← FastAPI + /healthz
│   ├── config/settings.py        ← pydantic-settings
│   ├── llm/providers/            ← 4 providers + Protocol + factory
│   ├── db/                       ← read-only connection + registry
│   ├── execution/                ← sqlglot guards + runner + errors
│   ├── render/                   ← deterministic format/chart picker
│   ├── schema_index/             ← introspect → chunk → index → retrieve
│   ├── agent/                    ← LangGraph 6 nodes + state + prompts
│   └── eval/                     ← BIRD loader, EA + recall metrics, runner, HTML report
├── tests/                        ← 169 tests, all green
├── scripts/
│   ├── download_data.py          ← chinook + bird-mini-dev (gdown)
│   ├── build_index.py            ← live: build chroma_data/ from db
│   ├── smoke_schema_recall.py    ← live: recall@5 sanity on chinook
│   ├── smoke_pipeline.py         ← live: full 6-node pipeline on chinook
│   ├── eval_baseline.py          ← live: configuration A on N BIRD examples → JSON+HTML
│   └── sql/postgres_init.sql     ← read-only role for postgres
├── data/                         ← gitignored
│   ├── chinook/Chinook.sqlite    ← 1 MB
│   └── bird_mini_dev/MINIDEV/    ← 800 MB, 11 sqlite DBs + 500 questions
├── chroma_data/                  ← gitignored, persistent vector store
├── pyproject.toml                ← uv-managed
├── docker-compose.yml            ← optional postgres + langfuse profiles
├── Makefile                      ← make install/lint/format/type/test/serve
├── .env                          ← gitignored (Mistral + GitHub + Groq keys)
└── .env.example                  ← committed, full template
```

## Quick reference — commands

```powershell
# Install / sync deps
uv sync --extra dev

# Tests / lint / type
uv run pytest
uv run ruff check src tests scripts
uv run mypy src

# Download datasets
uv run python scripts/download_data.py chinook
uv run python scripts/download_data.py bird-mini-dev

# Build schema index (live Mistral embed)
uv run python scripts/build_index.py --db chinook
uv run python scripts/build_index.py --db all

# Schema recall@5 smoke
uv run python scripts/smoke_schema_recall.py

# Full pipeline smoke (5 hand-picked Chinook questions, live Mistral)
uv run python scripts/smoke_pipeline.py
uv run python scripts/smoke_pipeline.py --question "..." --verbose

# Eval baseline (config A, N BIRD examples; live Mistral codestral)
uv run python scripts/eval_baseline.py --n 50 --seed 0
uv run python scripts/eval_baseline.py --n 5 --db bird_california_schools
```

## Things to NOT redo

- Don't recreate the provider Protocol — settled, 4 implementations conform.
- Don't re-implement retrieval inside a graph node — call
  `retrieve_context()` from `nl_sql.schema_index`.
- Don't re-implement format picking inside a graph node — call
  `pick_format()` from `nl_sql.render`.
- Don't add Prometheus / OpenTelemetry / Redis — explicit cuts in v2.
- Don't have the LLM emit Vega-Lite — chart picker is deterministic.
- Don't expand schema-RAG to 4 collections without a baseline EA number.
- Don't use HuggingFace `birdsql/bird_mini_dev` — questions only, no DBs.
  Use the Google Drive bundle via `scripts/download_data.py`.
- Don't rotate Mistral accounts to bypass quotas — diskcache + throttle.
- Don't write a 7th node — repair is conditional, validation triggers it.

## Final state for memory

```
HEAD:   stage 6 eval harness (see git log)
Branch: main
Tests:  169/169 passing
Lint:   ruff clean
Type:   mypy strict clean (49 src files)
Live:   Mistral OK (codestral + embed + large), Groq OK,
        GitHub Models 401, Ollama not installed
Data:   Chinook + 11 BIRD DBs downloaded; chroma_data/ has chinook indexed
Stages: 1, 2, 3, 4, 5, 6 (cfg A only), 9 done. 6 (B–E) next.
Smoke:  schema recall@5 = 5/5 on Chinook
        full pipeline   = 5/5 on Chinook
Eval:   config A on 50 BIRD = 46.0% EA (above 35% hard checkpoint)
        — `eval/reports/2026-05-10/A_full_schema.json`
Budget: $0 hard constraint, all live providers free-tier.
```
