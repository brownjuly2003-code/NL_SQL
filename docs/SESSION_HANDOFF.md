# NL_SQL — Session Handoff (2026-05-10, late)

> Read this first when picking up. It's the single source of truth for
> "where we stopped" and "what to do next". When you take action, update
> this file before you stop again.

---

## Current state in 30 seconds

- **Repo:** `D:\NL_SQL\` on `main`
- **HEAD:** see `git log -1 --oneline` (most recent: stage 4 LangGraph pipeline)
- **Tests:** 131/131 passing, ruff clean, mypy strict clean (42 src files)
- **Stages closed (autonomous): 1, 2, 3, 4, 5, 9** + provider adapter expanded with Groq
- **Stages waiting: 6+** (eval harness)
- **Hard budget:** still $0. All live providers tested are free-tier.

Live signals:
- Schema recall@5 on Chinook (`mistral-embed`) = **5/5 (100%)** — `scripts/smoke_schema_recall.py`
- Full pipeline on Chinook (`codestral-latest` + `mistral-large-latest`) = **5/5 succeeded** — `scripts/smoke_pipeline.py`

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

### 4. Stage 4 caveats (NEW)

- **`fewshot_qsql` collection has zero records** — pipeline runs with
  `fewshot_top_k=0` for now. Stage 6 (eval) will populate from BIRD
  *train* split (NEVER dev — see `03_eval_methodology.md` §5).
- **Business-hint glossary is empty** — `to_chunks(..., business_hints={})`
  is wired but no glossary file. Add when prompt eval shows the LLM
  missing domain terms.
- **`mistral-large-latest` caption rate-limited under load** — graceful
  fallback to error sentence; consider switching caption to Groq's free
  llama-3.3-70b if rate-limit becomes a recurring smoke issue.
- **No few-shot in pipeline.** `PipelineConfig.fewshot_top_k` defaults to 3
  but `smoke_pipeline.py` passes 0 because the index has none.

## Next session — recommended order

### Step A — Stage 6: eval harness (5-8h)

`src/nl_sql/eval/`:
- `runner.py` — orchestrates ablation matrix per `03_eval_methodology.md` §4
- `metrics/execution_accuracy.py` — order-insensitive result comparison
- `metrics/schema_recall.py` — recall@k on retrieved tables vs gold
- `report.py` — HTML report writer

First milestone: baseline EA on 50 BIRD examples, configuration A only
(full_schema). Number doesn't matter — just need the harness working.

After harness: build the few-shot pool from BIRD *train* split (separate
download — current bundle has Mini-Dev only; train split needs its own
HF dataset or curated subset).

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
│   └── agent/                    ← LangGraph 6 nodes + state + prompts
├── tests/                        ← 131 tests, all green
├── scripts/
│   ├── download_data.py          ← chinook + bird-mini-dev (gdown)
│   ├── build_index.py            ← live: build chroma_data/ from db
│   ├── smoke_schema_recall.py    ← live: recall@5 sanity on chinook
│   ├── smoke_pipeline.py         ← live: full 6-node pipeline on chinook
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
HEAD:   stage 4 LangGraph pipeline (see git log)
Branch: main
Tests:  131/131 passing
Lint:   ruff clean
Type:   mypy strict clean (42 src files)
Live:   Mistral OK (codestral + embed + large), Groq OK,
        GitHub Models 401, Ollama not installed
Data:   Chinook + 11 BIRD DBs downloaded; chroma_data/ has chinook indexed
Stages: 1, 2, 3, 4, 5, 9 done. 6+ next.
Smoke:  schema recall@5 = 5/5 on Chinook
        full pipeline   = 5/5 on Chinook
Budget: $0 hard constraint, all live providers free-tier.
```
