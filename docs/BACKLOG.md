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
- ✅ BIRD rescue hints gated behind `PipelineConfig.enable_bird_rescue_hints` (default **off**); product path no longer serves canned per-question answers. `eval_baseline.py --bird-rescue-hints` reproduces the hint-assisted number.
- ✅ Reproducible single-run measured and committed (config E, codestral, 57.5% — `eval/baselines/reproducible_n200.json`).
- ✅ Three-tier metric in README + methodology §13 (57.5% product / 85.5% voting / 94.0% hint-assisted), each labelled by whether it runs in the product.
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
- ✅ SQLite headline unaffected by both fixes: re-measured n=200 → still 57.5%.

## Gated (needs a decision or an external host)

- ⛔ **Sustained-load benchmark.** The data-migration half is done (above); a throughput/latency run under sustained load still wants a host that isn't the Windows dev box.
- ⛔ **Space cleanup + git history.** `SESSION_HANDOFF.md` is un-tracked now, so future deploys won't republish it; removing it from the live Space and any git-history rewrite are force/deploy actions — owner's call.
- ⛔ **External pen-test of the public API.** Self-attestation is not a substitute; needs an outside pass.

## Won't-fix (verified)

- 🔎 `execution_accuracy._hashable` float bucketing — 0 set-mismatch across v22–v31 baselines; O(n²) replacement not justified.
- 🔎 `cache.py` miss/fill race — fires only under parallel eval workers, which aren't used.
- 🔎 Chasing BIRD annotation-quirk residue above 94% — saturation shown by 3-model reasoning sweeps.
