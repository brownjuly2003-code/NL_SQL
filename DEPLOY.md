# Deployment — Hugging Face Space (Docker)

The public demo runs on a Hugging Face Space with a Docker runtime (free tier):
<https://liovina-nl-sql.hf.space>. Cold start ~30 s, then interactive.

## Deploy policy: only what git tracks, then prune

The deploy publishes **exactly the files git tracks** (`git ls-files`), never the
working tree. Working-kitchen files — internal notes, audits, `.env`, scratch
reports — are gitignored and a repo-hygiene CI gate fails if any slip into the
index, so they cannot reach the Space. The upload also **prunes** the Space: files
removed from the repo are deleted on the host, not left behind from an earlier push.

The deploy script itself (`.deploy_hf.py`) is repo-local (it reads a local token
and Mistral key by path) and is intentionally not committed. It:

1. computes the file set from `git ls-files` minus a publish-exclude list
   (`tests/`, `.github/`, `docs/research/`, `reviews/`, `eval/baselines/`,
   `eval/reports/`, `scripts/autotune/`);
2. drops anything the hygiene detector flags;
3. scans the bytes of the resulting set for tunnel clients and refuses to upload if any
   are found (see below);
4. uploads via `huggingface_hub`, then prunes remote files no longer present;
5. supports `--self-test` (a gate that runs before upload) and `--dry-run`.

The Space hosts the **app**, not the research record. Eval reports and baselines are
260 files / 31 MB the app never reads; they stay in this repo, which is public, and are
excluded from the upload set. `--self-test` asserts that exclusion and fails if it is
removed, so the rule is executable rather than a comment.

## No tunnel clients on the Space

The GPU research harness (`scripts/autotune/`, Colab and Kaggle notebooks) downloads the
`cloudflared` binary to expose a fine-tuned model from a Colab session. That is fine in a
repo and wrong on a Space: Hugging Face's abuse-handler scans Space contents, and a tunnel
client shipped on free compute matches an abuse rule regardless of what it is for. This
Space was paused under `rule: Cloudflared` minutes after the first deploy that carried
those notebooks.

So the harness is excluded by path, **and** the deploy scans every file it is about to
upload for tunnel markers (`cloudflared`, `ngrok`, `localtunnel`, …) and aborts on a hit —
the path rule only knows the files that broke once, the content scan covers the rest.
`--self-test` proves the scanner is not vacuous by planting a marker in a throwaway file
and requiring it to be caught.

## What ships to the Space

The Space is **SQLite-only** — `psycopg` is pruned from its `requirements.txt`, so
the Postgres path (see README) is not present there; it is for local/CI use. The
Space carries a subset of the BIRD Mini-Dev databases (the three largest exceed
GitHub's 100 MB/file limit and are gitignored):

| DB | size | shipped |
|---|---|---|
| `chinook` | 1 MB | ✅ |
| `bird_california_schools` | 11 MB | ✅ |
| `bird_debit_card_specializing` | 34 MB | ✅ |
| `bird_financial` | 68 MB | ✅ |
| `bird_formula_1` | 22 MB | ✅ |
| `bird_student_club` | 2.6 MB | ✅ |
| `bird_superhero` | 0.2 MB | ✅ |
| `bird_thrombosis_prediction` | 7 MB | ✅ |
| `bird_toxicology` | 2.6 MB | ✅ |
| `bird_card_games` | 250 MB | ❌ over 100 MB/file |
| `bird_codebase_community` | 460 MB | ❌ over 100 MB/file |
| `bird_european_football_2` | 571 MB | ❌ over 100 MB/file |

The registry in `src/nl_sql/db/registry.py` skips DBs whose SQLite file isn't on
disk, so the deployed UI's selector lists only the 9 shipped databases. All 11
BIRD slices are present locally for eval. `chroma_data/` is committed (~58 MB) so
the app doesn't re-embed schema chunks on cold start.

## Secret

The Space needs one secret — `MISTRAL_API_KEY` — set in the Space's Settings →
Variables and secrets. `pydantic-settings` reads it from the environment.

## Updating

Re-run the local deploy script; it re-uploads the tracked set and prunes. CI (tests
+ repo-hygiene) gates `main` before any deploy is worth doing.
