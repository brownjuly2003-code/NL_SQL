# NL_SQL — Session Handoff (2026-05-10, stage 6 configs A+C+E live)

> Read this first when picking up. It's the single source of truth for
> "where we stopped" and "what to do next". When you take action, update
> this file before you stop again.

---

## Current state in 30 seconds

- **Repo:** `D:\NL_SQL\` on `main`
- **HEAD:** see `git log -1 --oneline` (stage 6 configs A+C+E live)
- **Tests:** 174/174 passing, ruff clean, mypy strict clean (49 src files)
- **Stages closed (autonomous): 1, 2, 3, 4, 5, 6 (configs A + C + E), 9** + provider adapter expanded with Groq
- **Stages waiting: 6 (config D, optional B)**, then 7+
- **Hard budget:** still $0. All live providers tested are free-tier.

Live signals:
- Schema recall@5 on Chinook (`mistral-embed`) = **5/5 (100%)** — `scripts/smoke_schema_recall.py`
- Full pipeline on Chinook (`codestral-latest` + `mistral-large-latest`) = **5/5 succeeded** — `scripts/smoke_pipeline.py`
- All 12 DBs indexed in Chroma (86 chunks, `chroma_data/`) via `scripts/build_index.py --db all`.

### Ablation A vs C vs E (50 BIRD Mini-Dev SQLite, codestral-latest, seed=0)

| Config | Final EA | 1st-pass EA | Simple | Moderate | Challenging | Validity | Recall@k | Empty | P50 | P95 | Wall | Repair fired |
|--------|----------|-------------|--------|----------|-------------|----------|----------|-------|------|-------|------|--------------|
| A (full_schema)  | 46.0% | 46.0% | 57.1% | 45.5% | **35.7%** |  96.0% | 98.0% |  6.0% | 1.3s | 37.1s | 413s | n/a |
| C (dense+FK, no fewshot, no repair) | 46.0% | 46.0% | 64.3% | 50.0% | 21.4% | **100.0%** | 98.0% | 12.0% | 2.4s |  5.6s | **150s** | n/a |
| E (= C + repair_once)               | **50.0%** | **50.0%** | 64.3% | **54.5%** | 28.6% | 100.0% | 98.0% | 10.0% | 3.0s |  8.2s | 188s | **0/50** |

- **C → E gives +4pp BUT repair_once fired 0 times.** That gap is
  non-determinism noise from codestral at `temperature=0` (same retrieval,
  same prompt template, same evidence string — only the conditional edge
  in the graph differs, and it never triggered). Without diskcache or a
  fixed cassette ablations smaller than ~5pp at n=50 are not signal.
- **Repair is dormant under dense retrieval.** Config C already hits 100%
  validity, so there are no INVALID_SQL outcomes for repair_once to fix.
  EMPTY_RESULT routes to format (per arch §3 retry policy), not to repair.
  → Until config D shows validity dropping below 100%, the repair branch
  is unobserved cost.
- **A → C: overall EA tied at 46.0%** but per-difficulty tells the real
  engineering story: dense retrieval gains +7.2pp simple / +4.5pp moderate,
  loses 14.3pp challenging. Multi-join challenging questions get pruned by
  top-5 + 1-hop FK budget. Bumping `schema_top_k` or `fk_hops` is the
  cheapest first lever to test.
- **Validity 100%** under C and E (vs 96% under A) — pruned schema gives
  the LLM less surface area to hallucinate DML/PRAGMA/etc.
- **Wall time:** C is 2.7× faster than A; E is 1.25× slower than C
  (longer prompts when the repair branch is *available* even if unused —
  not a real explanation; this is mostly Mistral rate-limit jitter at the
  free tier).
- **Above the week-3 hard checkpoint of EA ≥ 35%** → continue tuning loop, no scope-down.
- Reference: GPT-4 zero-shot on Mini-Dev SQLite = 47.8% (BIRD leaderboard).
- Artefacts: `eval/reports/2026-05-10/{A_full_schema,C_dense_cards,E_dense_fewshot_repair}.json` + `index.html`.

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
| 6 (A+C+E) | `src/nl_sql/eval/` | 43 | dataset loader, EA + Schema Recall@k, full_schema (A) / dense+FK (C) / dense+FK+repair (E) runners, JSON+HTML report. `disable_repair` knob added to `run_pipeline`. First-pass vs final EA correctly isolated when repair fires. Live A vs C vs E baseline in `eval/reports/2026-05-10/`. |
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

### 5. Stage 6 caveats

- **Configurations B and D are still stubbed** (raise `NotImplementedError`).
  D needs BIRD *train* split for fewshot pool; B (BM25) likely doesn't
  ship — A→C already showed dense retrieval doesn't move overall EA, so
  a separate BM25 row is low value unless the report needs it for
  completeness.
- **No diskcache yet.** Each eval call hits Mistral live, so re-running
  the same 50 examples doubles API spend AND re-rolls the codestral
  non-determinism (E showed +4pp over C at temperature=0 with literally
  identical execution paths — that gap is noise, not signal). Adding
  `(provider, model, prompt_hash) → response` cache per §6.2 makes
  ablations comparable; until then small deltas (<5pp at n=50) aren't
  signal.
- **No CI smoke-eval cassettes.** `03_eval_methodology.md` §6.1 wants
  vcr.py-style replay; not wired up. Live runs only for now.
- **Schema Recall@k = 98% in all three configs** — same 1 question miss
  from the regex-based `extract_gold_tables` (likely a CTE alias edge).
  Worth fixing if recall ever becomes the actual bottleneck.
- **Repair is dormant under config E.** 0/50 fires. Validity is already
  100% under dense retrieval; without invalid SQL there's nothing to
  fix. The repair-success-rate column will only be meaningful once
  config D introduces fewshot SQL that occasionally trips the validator.

## Next session — recommended order

### Step A — Diskcache + re-run for clean comparison

The C→E +4pp gap at temperature=0 is noise — same execution path, repair
never fired. Until each `(provider, model, prompt_hash)` is cached, every
run re-rolls codestral's tiny non-determinism. Add `diskcache` per
`02_architecture_v2.md §6.5` to the LLM provider wrapper, then re-run A
and C and E. With cache, second runs cost $0 + are deterministic, so the
ablation rows actually compare apples to apples.

### Step B — Investigate the challenging-tier regression

A→C lost 14.3pp on challenging questions while gaining on simple/moderate.
This is the single most actionable signal in the report. Plausible
hypotheses (in order of cheapness to test):
- `schema_top_k=5` is too tight on multi-join questions → bump to 8 and
  re-run config C.
- `fk_hops=1` cuts off transitive joins → bump to 2 (still bounded by
  `table_budget`).
- The retriever scores the question against table cards, not against
  table+column matches — adding a column-level fallback might help.
Document whichever lever moves the number.

### Step C — BIRD train split + config D

1. Download BIRD *train* (separate from Mini-Dev — it's hosted at the
   same Google Drive root, ~9 428 examples).
2. Embed into Chroma `fewshot_qsql` as `BirdExample` records.
3. Add CI test `test_no_dev_in_fewshot` using `is_in_dev_split` from
   `eval/dataset.py`.
4. `run_config_d` is a code clone of `run_config_c` with
   `fewshot_top_k=3`. Run on same 50 examples, seed=0.

If config D's validity drops below 100%, repair will start firing under
E and the repair-success-rate column will become meaningful.

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
HEAD:   stage 6 config E: dense + FK + repair_once (see git log)
Branch: main
Tests:  174/174 passing
Lint:   ruff clean
Type:   mypy strict clean (49 src files)
Live:   Mistral OK (codestral + embed + large), Groq OK,
        GitHub Models 401, Ollama not installed
Data:   Chinook + 11 BIRD DBs downloaded; chroma_data/ has all 12 DBs indexed
        (86 chunks)
Stages: 1, 2, 3, 4, 5, 6 (configs A + C + E), 9 done. 6 (D, optional B) next.
Smoke:  schema recall@5 = 5/5 on Chinook
        full pipeline   = 5/5 on Chinook
Eval:   A on 50 BIRD = 46.0% EA, validity 96%, 413s wall
        C on 50 BIRD = 46.0% EA, validity 100%, 150s wall
        E on 50 BIRD = 50.0% EA, validity 100%, repair fired 0/50, 188s wall
        (C→E +4pp = codestral non-determinism noise; repair dormant
         until validity drops below 100%)
        — `eval/reports/2026-05-10/{A,C,E}_*.json` + `index.html`
Budget: $0 hard constraint, all live providers free-tier.
```
