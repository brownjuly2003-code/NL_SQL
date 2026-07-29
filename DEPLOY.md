# Deployment — Hugging Face Space (Docker)

The public Space is <https://liovina-nl-sql.hf.space>, but it is not currently a
live demo. The Hugging Face API reports `PAUSED` / `Flagged as abusive`
(`Cloudflared`) since 2026-07-22. Restoring or retiring the deployment is an
owner-authorized closure action; the policy below describes the safe publish
path if restoration is chosen. **Do not re-deploy under an active flag** — wait
until Hugging Face clears the pause, then publish once to prune strays.

## Deploy script (tracked)

The clean-clone-safe entry point is **`scripts/deploy_hf.py`**. It is committed,
needs no local kitchen paths, and authenticates only from the process
environment:

| Variable | Role |
|---|---|
| `HF_TOKEN` | Hugging Face write token for `HfApi` |
| `MISTRAL_API_KEY` | Value written as the Space secret (never read from a file path) |

Remote mutation requires an **explicit** `--apply`. With no flags the script
prints usage and exits nonzero without touching the network.

### Local verification (no network, no credentials)

```powershell
# From a clean clone / this repo root:
.venv/Scripts/python.exe scripts/deploy_hf.py --self-test
.venv/Scripts/python.exe scripts/deploy_hf.py --dry-run

# Focused tests (also no network):
.venv/Scripts/python.exe -m pytest tests/scripts/test_deploy_hf.py -q
```

### Publish (owner-authorized only)

```powershell
$env:HF_TOKEN = "<write token>"          # process env only
$env:MISTRAL_API_KEY = "<mistral key>"   # process env only
.venv/Scripts/python.exe scripts/deploy_hf.py --apply
```

On `--apply` the script: runs the local safety gate → requires both env vars →
skips `create_repo` when the Space already exists → sets the Space secret →
uploads only the filtered tracked set → uploads a generated HF-frontmatter
`README.md` → prunes remote files that are no longer in the expected set.

## Deploy policy: only what git tracks, then prune

The deploy publishes **exactly the files git tracks** (`git ls-files`), never the
untracked working tree. Before `--apply`, every publish source plus `README.md`
must match `HEAD`; the script materializes and re-scans the complete staging tree
before it creates an HF client or changes a secret. Working-kitchen files —
internal notes, audits, `.env`, scratch reports — are gitignored and a
repo-hygiene CI gate fails if any slip into the index, so they cannot reach the
Space. The upload also **prunes** the Space: files removed from the repo (or
excluded from the publish set) are deleted on the host, not left behind from an
earlier push.

`scripts/deploy_hf.py` does the following:

1. computes the file set from `git ls-files` minus a publish-exclude list
   (`tests/`, `.github/`, `docs/research/`, `reviews/`, `eval/baselines/`,
   `eval/reports/`, `scripts/autotune/`);
2. drops anything the hygiene detector (`scripts/check_repo_hygiene.py`) flags;
3. excludes the repository `README.md` from bulk upload (an HF-frontmatter
   version is generated, tunnel-marker terms are sanitized, and it is uploaded
   separately);
4. scans the **bytes** of every publish file for tunnel clients and refuses to
   upload if any are found (see below);
5. requires every source to exist and match `HEAD`, then stages and scans the
   complete upload before any remote-capable client is created;
6. defines the expected remote tree as exactly that staged set plus the generated
   `README.md`, then prunes every other remote path;
7. supports `--self-test` and `--dry-run` as strictly local modes.

Source-only deployment metadata (`DEPLOY.md`, `docs/PROJECT_CLOSURE.md`, and
`scripts/deploy_hf.py`) is also excluded from the app host: these files document
the tunnel signatures and are not runtime dependencies.

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
upload for tunnel markers (`cloudflared`, `trycloudflare`, `ngrok`, `localtunnel`,
`bore.pub`, `serveo.net`, `pinggy`, `loca.lt`) in binary chunks with overlap, and aborts
on a hit — the path rule only knows the files that broke once, the content scan covers
the rest. `--self-test` proves the scanner is not vacuous by planting a marker in a
throwaway file and requiring it to be caught.

## What ships to the Space

The Space is **SQLite-only** — `psycopg` is pruned from its `requirements.txt`, so
the Postgres path (see README) is not present there; it is for local/CI use. The
tracked root `Dockerfile` (`python:3.13-slim`, `libgomp1`, `PYTHONPATH=/app/src`,
Streamlit on `0.0.0.0:7860`) is part of the publish set. The Space carries a subset
of the BIRD Mini-Dev databases (the three largest exceed GitHub's 100 MB/file limit
and are gitignored):

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

The Space needs one secret — `MISTRAL_API_KEY` — set via `scripts/deploy_hf.py
--apply` from the process environment (or manually in the Space's Settings →
Variables and secrets). `pydantic-settings` reads it from the environment on the
host. The deploy script never reads or prints local credential file paths.

## Updating

1. Confirm the Space is no longer paused/flagged (owner + HF moderation).
2. Run `--self-test` / `--dry-run` locally.
3. Run `--apply` with `HF_TOKEN` and `MISTRAL_API_KEY` in the environment only.

CI (tests + repo-hygiene) gates `main` before any deploy is worth doing.
Pushing to GitHub does **not** update the Space; publish is a separate
`--apply` step.
