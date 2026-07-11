# Backlog

Single living tracker for code/eval work items. Supersedes the scattered per-audit
lists — new findings land here with a status so nothing rots undone.

Status: ✅ done · ⛔ gated (needs a human decision or an external host) · 🔎 won't-fix (verified)

## Done (2026-07-11)

Security / public surface
- ✅ AST guard: `SELECT … INTO` denied; `pg_sleep_for/until`, `set_config`, `setval` banned; adversarial tests per vector.
- ✅ Streamlit `Sentence` renderer HTML-escaped (stored-XSS class closed).
- ✅ API: rate limit unconditional (anonymous bucketed by IP); key via `Settings` (`.env` honoured); `secrets.compare_digest`; 500s redacted to a `trace_id`; `truncated` surfaced in `AskResponse`.

Metric integrity
- ✅ BIRD rescue hints gated behind `PipelineConfig.enable_bird_rescue_hints` (default **off**); product path no longer serves canned per-question answers. `eval_baseline.py --bird-rescue-hints` applies them to the single-run — measured at 62.5%, *not* the archive's 94.0% (see the audit section below).
- ✅ Reproducible single-run measured and committed (config E, codestral — `eval/baselines/reproducible_n200.json`; 57.5% as measured then, 58.0% after the comparator fix below).
- ✅ Metric split into labelled tiers in README + methodology §13, each marked by whether it runs in the product. (Corrected in the third pass below: the tiering claimed the hints flag reproduced 94.0%. It does not — it yields 62.5%.)
- ✅ Machine-readable artifacts synced: v31 report summary 185/0.925 → 188/0.94; `/eval/latest` serves the reproducible baseline (not a stale 60.5%); FastAPI description honest; regression test pins `overall == recompute(records)`.

Postgres path
- ✅ Read-only made real: `postgresql_readonly` execution option (was a no-op `SET` inside an open transaction); DSN normalised to `psycopg` v3 (path had never run under psycopg2). Loader `scripts/load_postgres.py`; registry registers PG from `NL_SQL_PG_DSN`. Live PG16 proof in CI (`tests/test_postgres_readonly.py`).

Docs / hygiene / CI
- ✅ README/DEPLOY truthful: Langfuse + vcr.py claims removed; unused langfuse compose service dropped; DEPLOY.md rewritten for the real HF Space (tracked-only + prune).
- ✅ CWD-independent paths (`nl_sql.paths`); `ProviderName` synced with the factory (+`perplexity`, +`gracekelly`).
- ✅ Nine voting scripts on the unsafe comparator frozen in `scripts/archive/` + CI gate (`check_no_raw_compare.py`).
- ✅ CI: mypy over `src app scripts`; coverage floor (`--cov-fail-under=85`, currently 91%); aligned on Python 3.13.
- ✅ `docs/SESSION_HANDOFF.md` un-tracked (kitchen); eval trace moved into methodology §13.

## Done (2026-07-11, second pass — the Postgres claim, actually run)

- ✅ **PG data load + PG-backed eval.** `codebase_community` (StackExchange-mini, 741 646 rows, 385 MB) loaded into a live Postgres 16 from BIRD's own PG dump via `scripts/extract_pg_dump_slice.py` (the dump ships all eleven databases in one `public` schema; the slice keeps one). Row counts verified against SQLite table by table. The product pipeline then ran on BIRD's **Postgres gold**: **49.0% EA (24/49)** vs 44.9% on SQLite for the same questions, 100% validity, 88% agreement between engines — the engine ports. Artefact: `eval/baselines/postgres_codebase_community_n49.json`; method: `docs/03_eval_methodology.md` §14.
- ✅ **Two product bugs that only a live Postgres could expose** (both invisible on SQLite):
  - `execute_readonly` ran statements through `exec_driver_sql`, which hands the driver an empty parameter set — psycopg (`pyformat`) then parsed `%` as a placeholder and killed every `LIKE '%x%'` and every `%` modulo, *including BIRD's gold* (qids 586/587 couldn't even be scored). Now executed on a DBAPI cursor with no parameters, so neither `%` (psycopg) nor `:__` (SQLAlchemy `text()`) is interpreted; driver exceptions are re-wrapped into `sqlalchemy.exc` so error classification is unchanged.
  - `_normalise_cell` never converted `Decimal` → `float` (its docstring claimed it did), so Postgres `numeric` results (`AVG`, `SUM`, any division) skipped the float-tolerance grid and correct answers scored misses. Cost 4 EA points on the PG run (40.8% → 49.0%).
- ✅ SQLite headline unaffected by *these two* fixes: re-measured n=200 → still 57.5% at the time. (A third comparator bug, found in the audit below, later moved it to 58.0%.)

## Done (2026-07-11, third pass — adversarial audit of the fixes themselves)

The code written during the two passes above had not itself been reviewed. Five real defects, all found by reading it back — the first one by *running* the command the docs told reviewers to run:

- ✅ **The docs claimed a number the command does not produce.** README, methodology §13 and this backlog all said the hint-assisted tier reproduces with `eval_baseline.py --config E --n 200 --bird-rescue-hints`. Run it: **62.5%** (125/200), not 94.0%. The 94.0% artefact (`eval/reports/2026-05-26/v31-v30-plus-p3f-q37-merged.json`) is a *merge of ~20 runs* — its own `sql_model` field lists codestral + Sonnet 4.6 + GPT-5.2 + Grok-4.1 + Kimi-K2 + Llama-4-Scout + Qwen3 + gpt-oss voting across Groq/OpenRouter/Perplexity bridges, plus archive-rescore, plus the hints. Presenting that as "the pipeline with hints on" both overstated what the flag does and *understated* what the number cost. Tiers are now four, each labelled reproducible-or-archive, and the two reproducible ones carry the numbers their commands actually print.
- ✅ **The rate limit could be dodged with one header.** `require_api_key` bucketed on `X-API-Key` even when *no* key was configured — which is exactly the keyless public deploy the limiter was added to protect. The header is then unauthenticated, caller-controlled input: a fresh random key per request minted a fresh bucket, so the 60/min limit never fired, and `_hits` grew without bound (an OOM vector driven by remote input). It now buckets on the header only when a key is configured, and therefore verified; otherwise it falls back to the client IP. Stale buckets are swept once per window.
- ✅ **One accented byte in `X-API-Key` returned 500 instead of 401.** `secrets.compare_digest` raises `TypeError` on a `str` holding any codepoint above 127, and Starlette decodes headers as latin-1. Keys are compared as bytes now.
- ✅ **The comparator scored correct answers as misses (int vs float).** `_hashable` quantised floats onto the tolerance grid but passed ints through untouched: gold `5` hashed to `5`, pred `5.0` to `5_000_000`, and the set comparison called it a mismatch. That is *stricter than BIRD's own scorer*, which sets raw Python tuples — where `5 == 5.0` collapses — and it contradicted the apples-to-apples claim in the docstring. The ordered path compares through a tolerance and always got these right, so one (gold, pred) pair scored two different ways depending on whether gold had `ORDER BY`. Every number — int, float, and (post-`_normalise_cell`) Decimal — now shares one grid. Re-measured: **SQLite n=200 → 58.0% (116/200), up from 57.5%**; the recovered question is a `challenging` one (41.2% → 44.1%). Postgres n=49 unchanged (49.0%), SQLite control n=49 unchanged (44.9%), Chinook still 100%. The fix is monotone — it can only merge buckets that were wrongly split — so no previously-passing question can regress.
- ✅ **Engine leak on the hot path.** `DatabaseSpec.make_engine()` called `create_engine` on *every* invocation — once per `/ask`, once per eval question — so no pool was ever reused and none disposed, while `connect()`'s docstring promised reuse. On Postgres that opens a fresh backend per question and walks straight into `max_connections` under sustained load. Engines are built once per spec and pooled now (`dispose_engines()` clears the cache). Paired fix: the SQLite statement-timeout progress handler is disarmed on the way out — pooled connections get handed to the next caller (schema introspection never arms one of its own), and a handler left behind carries an already-expired deadline that would interrupt that caller's first non-trivial query.

## In progress — lifting the reproducible number (2026-07-11)

The reproducible single-run is the only number that matters here: 58.0% at the
start of this pass. Every step below is measured on the same n=200 BIRD Mini-Dev
slice, config E, codestral, hints off.

| Step | EA | Δ | Verdict |
|---|---:|---:|---|
| Baseline (after the comparator fix) | 58.0% | — | — |
| **Question + `evidence` moved to the top of the prompt** | **61.0%** | **+3.0** | ✅ kept |
| + BIRD's `database_description/*.csv` in the schema block | 59.5% | −1.5 | ❌ gated off |
| + self-consistency (config F: 4 candidates at T=0.2–0.8, execution voting) | 58.0% | −3.0 | ❌ not taken |
| **+ few-shot from BIRD train (k=3)** | **61.5%** | **+0.5** | ✅ kept — **the product number** |

The few-shot result is one question, which is noise on n=200 — but it is worth
keeping for a reason that has nothing to do with the delta: **the product was
already running with it.** `api/main.py` builds its pipeline with
`fewshot_top_k=3`, while config E hard-coded 0 despite being named
`E_dense_fewshot_repair`. The eval harness was measuring a pipeline the product
does not run, and undercounting itself. Now the command in the README and the
live demo evaluate the same thing.

Self-consistency is worth a word, because it is the technique everyone reaches
for. Config F turns *repair off* (`Repair fired: 0/200`) on the theory that
voting replaces it, and samples at T=0.2–0.8. Both halves hurt: every candidate
is worse than the greedy pass, and the vote does not recover the difference. F
tops out at its own first pass (58.0%), while E's first pass is 59.5% and repair
carries it to 61.0%. Diversity through *temperature* does not pay on codestral.
Diversity through *different models* did — that is what took the archive to
85.5% — and it is now blocked on provider keys, not on code:
`scripts/ensemble_providers.py` is written and waiting (Groq 403, GitHub Models
401, OpenRouter's free tier 429).

**What the two results say together.** The win did not come from telling the
model something new — `evidence` was always in the prompt. It came from moving it
out of the middle, where models attend least: it sat after the schema block and
the few-shot block. The project's own residue analysis had said so
(`docs/kimi_v9_residue_analysis.md:27`) and nobody had acted on it.

The column-descriptions result is the same mechanism running backwards. They are
real information — BIRD's own gloss on its cryptic identifiers — and feeding them
is standard practice in BIRD systems. But they add thousands of characters per
table, the schema block swells, and the question drifts back toward the middle.
The information gained did not pay for the attention lost. Loader and renderer
are kept and tested; the flag is off. The version worth trying is column-level:
retrieve descriptions only for the columns a question plausibly touches.

Rule of thumb this pass earned: **space at the top of the prompt is a scarce
resource, and any lever that lengthens the prompt must pay for the room it takes.**

## Gated (needs a decision or an external host)

- ⛔ **Sustained-load benchmark.** The data-migration half is done (above); a throughput/latency run under sustained load still wants a host that isn't the Windows dev box.
- ⛔ **Space cleanup + git history.** `SESSION_HANDOFF.md` is un-tracked now, so future deploys won't republish it; removing it from the live Space and any git-history rewrite are force/deploy actions — owner's call.
- ⛔ **External pen-test of the public API.** Self-attestation is not a substitute; needs an outside pass.

## Won't-fix (verified)

- 🔎 `execution_accuracy._hashable` float-vs-float bucket boundaries — 0 set-mismatch across v22–v31 baselines; O(n²) replacement not justified. (This verdict looked only at float-vs-float. The int-vs-float half of the same function *was* broken — see the audit section above.)
- 🔎 `cache.py` miss/fill race — fires only under parallel eval workers, which aren't used.
- 🔎 Chasing BIRD annotation-quirk residue above 94% — saturation shown by 3-model reasoning sweeps.
