# NL_SQL — Session Handoff (2026-05-10, late)

> Read this first when picking up. It's the single source of truth for
> "where we stopped" and "what to do next". When you take action, update
> this file before you stop again.

---

## Current state in 30 seconds

- **Repo:** `D:\NL_SQL\` on `main`
- **HEAD:** `1c54040` (or whatever `git log -1 --oneline` shows)
- **Tests:** 75/75 passing, ruff clean, mypy strict clean (24 src files)
- **Stages closed (autonomous): 1, 2, 5, 9** + provider adapter expanded with Groq
- **Stages waiting: 3, 4, 6+** (deferred for live-API tuning, now unblocked)
- **Hard budget:** still $0. All live providers tested are free-tier.

```
git log --oneline:
1c54040 provider adapter: add Groq + chromadb dep; live keys verified
cebd7bf stages 2 + 5 + 9: target DBs, SQL guards, deterministic chart picker
5011131 stage 1: bootstrap + provider adapter (Mistral, GitHub Models, Ollama)
9f0f138 docs: switch bakeoff to $0 budget (GitHub Models for frontier slot)
afa1edb docs: initial NL_SQL portfolio demo baseline
```

## How to start the next session

Open `D:\NL_SQL\` and run:

```powershell
# 1. Sanity check the repo is still green
uv run ruff check src tests
uv run mypy src
uv run pytest

# 2. Read this file + 02_architecture_v2.md + 03_eval_methodology.md
#    Those three docs are the spec; everything below is workflow.

# 3. Pick the next deliverable from "Next session" section below.
```

Then say something like: *"Продолжай stage 3 — schema indexer. BIRD download fix через HuggingFace, Mistral + Groq уже работают по живому."*

That orients me in 1 message and I can resume.

## What's done (just to anchor)

| Stage | Module | Tests | Notes |
|---|---|---|---|
| 1 | `src/nl_sql/api/`, `src/nl_sql/config/`, `src/nl_sql/llm/providers/` | 21 | FastAPI /healthz, 4 providers, factory |
| 2 | `src/nl_sql/db/`, `scripts/`, `docker-compose.yml` | 10 | read-only role, registry, download script. Chinook real download verified. |
| 5 | `src/nl_sql/execution/` | 31 | sqlglot AST guard, 3-layer defence, error taxonomy |
| 9 | `src/nl_sql/render/` | 14 | deterministic chart picker, no LLM |

Live API status (with keys from `.env`):
- Mistral `codestral-latest` — works, ~3s/req, free tier
- Mistral `mistral-embed` — not yet hit live (will be in stage 3)
- Groq `llama-3.3-70b-versatile` — works, sub-second, free tier
- GitHub Models `openai/gpt-4o-mini` — **401 Unauthorized** (PAT lacks
  `models:read` scope; see "Open issues" below)

## Open issues — fix early next session

### 1. BIRD Mini-Dev download is broken

`scripts/download_data.py bird-mini-dev` 404s on the GitHub URL it had,
and the Aliyun fallback timed out from this network. The dataset is now
on HuggingFace at `huggingface.co/datasets/birdsql/bird_mini_dev` and
mirrored on Google Drive.

**Fix path:** add `huggingface_hub>=0.26` to deps and use:

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="birdsql/bird_mini_dev",
    repo_type="dataset",
    local_dir="data/bird_mini_dev",
    allow_patterns=["MINIDEV/**"],  # 500-example dev split + sqlite DBs
)
```

The HF dataset is public, no token needed.

After download, `data/bird_mini_dev/MINIDEV/dev_databases/<db>/<db>.sqlite`
should exist and `get_default_registry()` will auto-register them as
`bird_<db>` ids. (The current registry scans `data/bird_mini_dev/<db>/`
directly — adjust the glob to handle the `MINIDEV/dev_databases/` prefix
or set up a symlink in scripts.)

### 2. GitHub Models PAT needs `models:read` scope

Current PAT is a fine-grained one (`github_pat_11ATTW6JA0...`) but not
provisioned with `models:read` permission. To use GitHub Models as the
frontier slot in the bakeoff, generate a new fine-grained PAT at
<https://github.com/settings/tokens?type=beta> and pick "Models — Read"
under Account permissions.

**Not blocking anything**: `Groq llama-3.3-70b` is the active default
frontier and works fine for the bakeoff. GitHub Models is only useful
if we want a proprietary GPT-4-class reference in the comparison.

### 3. Ollama is not installed yet

The local slot `OllamaProvider` is wired but no `ollama` binary on this
machine. To enable the local slot in stage 11 bakeoff:

```powershell
# Install Ollama for Windows (https://ollama.com/download/windows)
winget install Ollama.Ollama

# Pull the model (4.7 GB, fits 16 GB RAM comfortably)
ollama pull qwen2.5-coder:7b-instruct

# Verify
ollama run qwen2.5-coder:7b-instruct "SELECT 1 AS answer;"
```

Not blocking anything until stage 11 (bakeoff). For stages 3/4/6 we use
Mistral only, and that's fine.

## Next session — recommended order

The architecture (`02_architecture_v2.md`) defines stages; here's the
*concrete next-step* sequence factoring in what we know now.

### Step A — fix BIRD download (30 min)

Per "Open issues §1" above. After: `uv run python scripts/download_data.py bird-mini-dev`
populates `data/bird_mini_dev/MINIDEV/`, and `get_default_registry()`
needs the path glob updated to match.

### Step B — Stage 3: schema indexer + Chroma (3-5h)

`src/nl_sql/schema_index/`:

- `introspector.py` — `introspect(engine) -> list[TableInfo]`. Walks
  SQLAlchemy `inspect(engine)` to get tables, columns, types,
  primary/foreign keys. Handle SQLite + Postgres dialects. For each
  column, sample 5 distinct values + count nulls + nunique (for
  business hint generation later).
- `chunker.py` — `to_chunks(tables) -> list[ChunkRecord]`. Per the v2
  arch §4: ONE chunk per table (name, description, all columns w/
  types and samples, FK list). No separate column collection.
- `indexer.py` — uses `chromadb.PersistentClient(path="chroma_data")`,
  builds two collections: `schema_chunks` and `fewshot_qsql`. Uses
  `MistralProvider.embed()` (already implemented) for vectors. FK
  graph is a Python dict-of-sets in memory, *not* a Chroma collection.
- `retriever.py` — `retrieve_context(question, registry_id) -> ContextBundle`
  hybrid BM25 + dense (chromadb's built-in is fine for v1). Returns
  retrieved tables + FK-traversed neighbours up to a budget.
- Tests: smoke schema recall@5 on Chinook (we know the schema, can
  hand-pick 5 questions and verify retrieved tables match expected).

`chromadb>=0.5` is already in deps. uv.lock has it.

### Step C — Stage 4: LangGraph pipeline (4-6h)

Add `langgraph` to deps. Build `src/nl_sql/agent/`:

```
agent/
├── graph.py              # StateGraph wiring
├── state.py              # PipelineState TypedDict
├── nodes/
│   ├── context_builder.py  # combines retrieve_schema + retrieve_examples
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

Smoke test: 5 hand-picked Chinook questions through the full graph,
inspect output. Don't tune prompts yet — get a baseline.

### Step D — Stage 6: eval harness (5-8h)

`src/nl_sql/eval/`:

- `runner.py` — orchestrates ablation matrix per `03_eval_methodology.md` §4
- `metrics/execution_accuracy.py` — order-insensitive result comparison
- `metrics/schema_recall.py` — recall@k on retrieved tables vs. gold
- `report.py` — HTML report writer

First milestone: baseline EA on 50 BIRD examples, configuration A only
(full_schema). Number doesn't matter — we just need the harness working.

### Step E — Hard checkpoint (week 3 of original roadmap)

Per `02_architecture_v2.md §11` step 7: if EA < 35% → scope-down protocol
(`§12`). If ≥ 35%, continue tuning loop.

## Key files map (for orientation)

```
D:\NL_SQL\
├── docs/
│   ├── 00_task.md                ← postановка (corrected after CX/KM)
│   ├── 01_architecture.md        ← v1 historical, has known-error banner
│   ├── 02_architecture_v2.md     ← ACTIVE BASELINE — read this first
│   ├── 03_eval_methodology.md    ← central artifact: ablation, metrics
│   └── SESSION_HANDOFF.md        ← you are here
├── reviews/
│   ├── _prompt.md                ← review request to CX+KM
│   ├── codex_review.md           ← Codex feedback (compact)
│   └── kimi_review.md            ← Kimi feedback (large, with reasoning trace)
├── src/nl_sql/
│   ├── api/main.py               ← FastAPI + /healthz
│   ├── config/settings.py        ← pydantic-settings, env-driven
│   ├── llm/providers/            ← 4 providers + Protocol + factory
│   ├── db/                       ← read-only connection + registry
│   ├── execution/                ← sqlglot guards + runner + errors
│   └── render/                   ← deterministic format/chart picker
├── tests/                        ← 75 tests, all green
├── scripts/
│   ├── download_data.py          ← Chinook works, BIRD broken (see §1)
│   └── sql/postgres_init.sql     ← read-only role for docker postgres
├── data/                         ← gitignored
│   └── chinook/Chinook.sqlite    ← 1 MB, downloaded + verified
├── pyproject.toml                ← uv-managed
├── docker-compose.yml            ← optional postgres + langfuse profiles
├── Makefile                      ← make install/lint/format/type/test/serve
├── .env                          ← gitignored, has Mistral + GitHub + Groq keys
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
uv run ruff check src tests
uv run mypy src

# Or use the Makefile (POSIX-ish)
make install lint type test
make serve  # uvicorn

# Download datasets
uv run python scripts/download_data.py chinook       # works
uv run python scripts/download_data.py bird-mini-dev # broken — see Open issues §1

# Smoke-test a provider live
uv run python -c "from nl_sql.llm.providers import GenerateRequest, build_provider; p=build_provider('mistral'); print(p.generate(GenerateRequest(prompt='SELECT 1', max_tokens=20)).text)"
```

## Things to NOT redo

- Don't recreate the provider Protocol — it's settled and 4 implementations
  conform to it.
- Don't add Prometheus / OpenTelemetry / Redis — explicit cuts in v2.
- Don't have the LLM emit Vega-Lite — chart picker is deterministic.
- Don't expand schema-RAG to 4 collections without a baseline EA number first.
- Don't rotate Mistral accounts to bypass quotas — diskcache + throttle is plan.

## Final state for memory

```
HEAD:   1c54040 (or current after this commit)
Branch: main
Tests:  75/75 passing
Lint:   ruff clean
Type:   mypy strict clean (24 src files)
Live:   Mistral OK, Groq OK, GitHub Models 401, Ollama not installed
Data:   Chinook downloaded; BIRD broken
Stages: 1, 2, 5, 9 done. 3, 4, 6+ next.
Budget: $0 hard constraint, all live providers free-tier.
```
