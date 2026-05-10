# NL_SQL — Session Handoff (2026-05-10, evening)

> Read this first when picking up. It's the single source of truth for
> "where we stopped" and "what to do next". When you take action, update
> this file before you stop again.

---

## Current state in 30 seconds

- **Repo:** `D:\NL_SQL\` on `main`
- **HEAD:** see `git log -1 --oneline` (most recent: stage 3 schema indexer)
- **Tests:** 102/102 passing, ruff clean, mypy strict clean (29 src files)
- **Stages closed (autonomous): 1, 2, 3, 5, 9** + provider adapter expanded with Groq
- **Stages waiting: 4, 6+** (LangGraph pipeline + eval harness)
- **Hard budget:** still $0. All live providers tested are free-tier.

Live recall@5 on Chinook with `mistral-embed` = **5/5 (100%)** on the
hand-picked smoke set. See `scripts/smoke_schema_recall.py`.

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

Then say something like: *"Продолжай stage 4 — LangGraph pipeline."*

## What's done (just to anchor)

| Stage | Module | Tests | Notes |
|---|---|---|---|
| 1 | `src/nl_sql/api/`, `src/nl_sql/config/`, `src/nl_sql/llm/providers/` | 21 | FastAPI /healthz, 4 providers, factory |
| 2 | `src/nl_sql/db/`, `scripts/`, `docker-compose.yml` | 10 | read-only role, registry, download script. Chinook + 11 BIRD DBs downloaded + registered. |
| 3 | `src/nl_sql/schema_index/` | 27 | introspector → chunker → indexer (Chroma) → retriever (FK 1-hop, table_budget). Live recall@5 = 100% on Chinook (smoke). |
| 5 | `src/nl_sql/execution/` | 31 | sqlglot AST guard, 3-layer defence, error taxonomy |
| 9 | `src/nl_sql/render/` | 14 | deterministic chart picker, no LLM |

Live API status (with keys from `.env`):
- Mistral `codestral-latest` — works, ~3s/req, free tier
- Mistral `mistral-embed` — works (used in stage 3 live recall test)
- Groq `llama-3.3-70b-versatile` — works, sub-second, free tier
- GitHub Models `openai/gpt-4o-mini` — **401 Unauthorized** (PAT lacks
  `models:read` scope; see "Open issues" below)

## Open issues — fix early next session

### 1. ~~BIRD Mini-Dev download is broken~~ — FIXED

Now downloads via Google Drive (gdown). HuggingFace `birdsql/bird_mini_dev`
is the canonical source for the 500-question JSON but **does not host the
SQLite databases** — only the questions split. The full bundle (questions
+ 11 SQLite DBs, 800 MB) lives on Google Drive (file id
`13VLWIwpw5E3d5DUkMvzw7hvHE67a4XkG`). Aliyun OSS mirror is firewalled in
some regions (TLS reset on handshake). `scripts/download_data.py
bird-mini-dev` handles the full pipeline: download → SHA256 → unzip with
`minidev/` prefix-strip + `__MACOSX/` skip.

Result: `data/bird_mini_dev/MINIDEV/dev_databases/<db>/<db>.sqlite` for
all 11 BIRD DBs; `get_default_registry()` auto-registers them as `bird_<db>`.

### 2. GitHub Models PAT needs `models:read` scope (UNCHANGED)

Current PAT is a fine-grained one (`github_pat_11ATTW6JA0...`) but not
provisioned with `models:read` permission. To use GitHub Models as the
frontier slot in the bakeoff, generate a new fine-grained PAT at
<https://github.com/settings/tokens?type=beta> and pick "Models — Read"
under Account permissions.

**Not blocking anything**: `Groq llama-3.3-70b` is the active default
frontier and works fine for the bakeoff.

### 3. Ollama is not installed yet (UNCHANGED)

Local slot wired but no `ollama` binary on this machine. To enable for
stage 11 bakeoff: `winget install Ollama.Ollama` then `ollama pull
qwen2.5-coder:7b-instruct`.

### 4. Stage 3 indexer caveats

- **`fewshot_qsql` collection has zero records** — we never built a
  few-shot pool. Stage 4 will populate it from BIRD train (NOT dev — see
  leakage prevention in `03_eval_methodology.md` §5).
- **Business-hint glossary is empty** — `to_chunks(..., business_hints={})`
  is wired but no glossary file yet. Add per-DB hints when stage 4 prompt
  evaluation shows the LLM missing domain terms ("active customer", "top",
  etc.).
- **No re-index on schema change** — `build_index.py --reset` drops the
  collection wholesale; partial schema reload not implemented.

## Next session — recommended order

The architecture (`02_architecture_v2.md`) defines stages; here's the
*concrete next-step* sequence factoring in what we know now.

### Step A — Stage 4: LangGraph pipeline (4-6h)

Add `langgraph` to deps. Build `src/nl_sql/agent/`:

```
agent/
├── graph.py              # StateGraph wiring
├── state.py              # PipelineState TypedDict
├── nodes/
│   ├── context_builder.py  # uses retrieve_context() — already wired
│   ├── generate_sql.py     # codestral via MistralProvider.generate
│   ├── validate.py         # uses execution.guards.validate_sql
│   ├── repair_once.py      # one-shot retry with error context
│   ├── execute.py          # uses execution.runner.execute_validated
│   ├── format.py           # render.picker.pick_format
│   └── explain_trace.py    # mistral-large-latest for NL caption
└── prompts/
    ├── generate_sql.txt
    └── explain.txt
```

Note: `context_builder` already has working primitives — just wire
`retrieve_context()` from `nl_sql.schema_index` into the node. Don't
re-implement retrieval there.

Smoke test: 5 hand-picked Chinook questions through the full graph,
inspect output. Don't tune prompts yet — get a baseline.

### Step B — Stage 6: eval harness (5-8h)

`src/nl_sql/eval/`:
- `runner.py` — orchestrates ablation matrix per `03_eval_methodology.md` §4
- `metrics/execution_accuracy.py` — order-insensitive result comparison
- `metrics/schema_recall.py` — recall@k on retrieved tables vs. gold
- `report.py` — HTML report writer

First milestone: baseline EA on 50 BIRD examples, configuration A only
(full_schema). Number doesn't matter — we just need the harness working.

### Step C — Hard checkpoint (week 3 of original roadmap)

Per `02_architecture_v2.md §11` step 7: if EA < 35% → scope-down
protocol (`§12`). If ≥ 35%, continue tuning loop.

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
│   └── schema_index/             ← introspect → chunk → index → retrieve
├── tests/                        ← 102 tests, all green
├── scripts/
│   ├── download_data.py          ← chinook + bird-mini-dev (via gdown)
│   ├── build_index.py            ← live: build chroma_data/ from db
│   ├── smoke_schema_recall.py    ← live: recall@5 sanity on chinook
│   └── sql/postgres_init.sql     ← read-only role for postgres
├── data/                         ← gitignored
│   ├── chinook/Chinook.sqlite    ← 1 MB, downloaded
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

# Run server (no live DB attached yet — just /healthz)
uv run uvicorn nl_sql.api.main:app --reload --port 8123

# Run tests / lint / type
uv run pytest
uv run ruff check src tests scripts
uv run mypy src

# Download datasets
uv run python scripts/download_data.py chinook        # works
uv run python scripts/download_data.py bird-mini-dev  # works (via gdown)

# Build schema index (live Mistral embed calls)
uv run python scripts/build_index.py --db chinook
uv run python scripts/build_index.py --db all   # all 12 DBs

# Smoke recall@5 (live; needs index built first)
uv run python scripts/smoke_schema_recall.py
```

## Things to NOT redo

- Don't recreate the provider Protocol — it's settled and 4 implementations
  conform to it.
- Don't re-implement retrieval inside the LangGraph node — call
  `retrieve_context()` from `nl_sql.schema_index`.
- Don't add Prometheus / OpenTelemetry / Redis — explicit cuts in v2.
- Don't have the LLM emit Vega-Lite — chart picker is deterministic.
- Don't expand schema-RAG to 4 collections without a baseline EA number first.
- Don't use HuggingFace `birdsql/bird_mini_dev` — it has questions only,
  not the SQLite DBs. Use Google Drive bundle via `download_data.py`.
- Don't rotate Mistral accounts to bypass quotas — diskcache + throttle is plan.

## Final state for memory

```
HEAD:   stage 3 schema indexer (see git log)
Branch: main
Tests:  102/102 passing
Lint:   ruff clean
Type:   mypy strict clean (29 src files)
Live:   Mistral OK, Groq OK, GitHub Models 401, Ollama not installed
Data:   Chinook + 11 BIRD DBs downloaded; chroma_data/ has chinook indexed
Stages: 1, 2, 3, 5, 9 done. 4, 6+ next.
Budget: $0 hard constraint, all live providers free-tier.
```
