# Deployment — Streamlit Community Cloud

The fastest free path to a public demo. ~5 minutes after the repo
is on GitHub.

## What's shipped in the repo

The deployed version intentionally carries a subset of the BIRD
Mini-Dev databases, not all 11:

| DB | size | source | shipped |
|---|---|---|---|
| `chinook` | 1 MB | Chinook sample | ✅ |
| `bird_california_schools` | 11 MB | BIRD Mini-Dev | ✅ |
| `bird_debit_card_specializing` | 34 MB | BIRD Mini-Dev | ✅ |
| `bird_financial` | 68 MB | BIRD Mini-Dev | ✅ |
| `bird_formula_1` | 22 MB | BIRD Mini-Dev | ✅ |
| `bird_student_club` | 2.6 MB | BIRD Mini-Dev | ✅ |
| `bird_superhero` | 0.2 MB | BIRD Mini-Dev | ✅ |
| `bird_thrombosis_prediction` | 7 MB | BIRD Mini-Dev | ✅ |
| `bird_toxicology` | 2.6 MB | BIRD Mini-Dev | ✅ |
| `bird_card_games` | 250 MB | BIRD Mini-Dev | ❌ — over GitHub 100 MB/file limit |
| `bird_codebase_community` | 460 MB | BIRD Mini-Dev | ❌ — over GitHub 100 MB/file limit |
| `bird_european_football_2` | 571 MB | BIRD Mini-Dev | ❌ — over GitHub 100 MB/file limit |

The three excluded DBs are gitignored. The registry in
`src/nl_sql/db/registry.py` skips DBs whose SQLite file isn't on
disk, so the deployed UI's database selector only lists the 9
shipped databases.

`chroma_data/` is also committed (~3 MB) so the app doesn't have
to re-embed the schema chunks on first cold start. Orphan chunks
for the three excluded DBs are harmless — the registry never
asks for them.

## Steps

1. **Create a public GitHub repo.** Name suggestion: `NL_SQL` or
   `nl-sql-portfolio`. Do not initialise with a README — we already
   have one.

2. **Push the local main branch:**
   ```powershell
   git remote add origin https://github.com/<your-username>/<repo>.git
   git push -u origin main
   ```
   Repo size will be ~150 MB. The push takes a minute or two.

3. **Sign in to <https://share.streamlit.io>** with the same
   GitHub account.

4. **New app:**
   - Repository: pick the repo you just pushed.
   - Branch: `main`.
   - Main file path: `app/streamlit_app.py`.
   - App URL: defaults to
     `https://<your-username>-<repo>-app-streamlit-app-<hash>.streamlit.app`.
     You can rename via the dashboard later.

5. **Set the secret:**
   - In the Streamlit Cloud app dashboard → "Settings" → "Secrets".
   - Add the API key in TOML format:
     ```toml
     MISTRAL_API_KEY = "your-key-here"
     ```
   - Streamlit Cloud injects every key in this TOML as an
     environment variable, which `pydantic-settings` picks up.
   - Click "Save". The app reboots automatically.

6. **First load.**
   The cold start is ~30 seconds — Streamlit Cloud installs the
   `ui` extra deps (streamlit, plotly, pandas), reads the prebuilt
   Chroma index, and warms the LLM provider. Subsequent loads are
   sub-second.

## Updating

Push to `main` → Streamlit Cloud auto-redeploys. No manual step.

## Why not Vercel

Streamlit is a long-running Tornado/WebSocket server with stateful
per-session memory. Vercel's serverless model gives you ~10-second
function executions with no persistent process — every page-reload
would lose `st.session_state` and every user keystroke would race
against a cold start. The hacks that "work" run Streamlit in a
container behind Vercel's edge layer, which trades all of Vercel's
strengths for none of Streamlit's. Streamlit Community Cloud is
the natively-supported home for this app.
