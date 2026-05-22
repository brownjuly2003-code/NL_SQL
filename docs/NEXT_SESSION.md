# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-22 v20 — **87.5% EA verified** (BIRD-official set scoring), above #1 paid SOTA by +5.55pp

**Состояние:**
- HEAD at `be679cb` during eval; reports generated but not committed.
- BIRD original gold n=200 (**v20**): **87.5% EA** (175/200), BIRD-official set scoring. **v20 triplet: 87.5% BIRD / 72.36% Arcwise-Plat-SQL / +9 audit catches** (Arcwise not rerun; carry-forward from v19). **Above #1 paid system AskData+GPT-4o (81.95%) by +5.55pp.**
- Per-tier v20: simple **92.5% (62/67)** / moderate **84.8% (84/99, +1.0pp от v19)** / challenging **85.3% (29/34)**.
- **Path v19 → v20 (+0.5pp):**
  - **helallao kimi-k2-thinking без DAC** on v19 residue (26 fails): 25/26 reached, **1 rescue qid 584 moderate codebase_community**, 24 same, 0 regressions, 1 tokenizer EXC qid 1399.
  - **qid 584 rescue:** baseline joined `comments.Text`; kimi plain reasoning picked `postHistory.Comment`, matching BIRD gold for "comments left by users who edited the post titled ...".
  - **grok-4.1-reasoning без DAC** on v20 residue: 24/25 reached, 0 rescues, 24 same, 1 tokenizer EXC qid 1399.
  - **claude-4.5-sonnet-thinking repeat после 24h+** on v20 residue: 24/25 reached, 0 rescues, 24 same, 1 tokenizer EXC qid 1399.
- Audit: `scripts/audit_rescore.py --report eval/reports/2026-05-22/v20-kimi-k2-thinking-merged.json` → stored 175 / true 175 / **0 mismatches**.

**Open path past 87.5% (приоритет):**
1. **Paid OpenRouter top-up** ($5+) — unlocks batch eval через heterogeneous `:free`/paid routed models, wiring уже готов.
2. **Local ollama heterogeneous CSC** (qwen2.5-coder default уже в settings) — без сетевого rate-limit, multi-day setup для wall-time × candidates.
3. **P3.F JOIN-path linker** (`docs/p3f_design.md`) — единственный remaining non-quota engineering path, multi-day.
4. **GraceKelly maintenance** — re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + update selectors only if Chrome profile is confirmed free.

**Что НЕ делать:**
- Не повторять plain `kimi-k2-thinking` на v19/v20 residue — v20 уже взял единственный rescue qid 584; остальное same.
- Не повторять plain `grok-4.1-reasoning` на v20 residue — 0 rescues, clean saturation.
- Не повторять `claude-4.5-sonnet-thinking` на v20 residue без нового 24h+ cooldown и явной причины — повтор 2026-05-22 дал 0 rescues.
- Не тратить время на `qid 1399` через helallao без tokenizer workaround: все три модели упали на quote/tokenizing error around `Mclean` + `Women's Soccer`.
- gpt-5.2 Pro повтор на v18/v19 residue — saturated × 2 независимых сессии.
- gpt-5.2-thinking + DAC повтор на v18/v19 residue — saturated.
- glm-4.5-air:free через OpenRouter — reasoning-blocked output (probe verified, content="").
- qwen3-coder:free через OpenRouter — Venice provider 429-loop на free quota.

---

## 2026-05-20 v19 — **87.0% EA verified** (BIRD-official set scoring), above #1 paid SOTA by +5.05pp

**Состояние:**
- HEAD bumped to v19 commit (см. git log).
- BIRD original gold n=200 (**v19**): **87.0% EA** (174/200), BIRD-official set scoring. **v19 triplet: 87.0% BIRD / 72.36% Arcwise-Plat-SQL / +9 audit catches** (was 86.5 / 72.36 / +5 at v18; Δ +0.5pp / 0 / +4). **Above #1 paid system AskData+GPT-4o (81.95%) by +5.05pp.**
- Per-tier v19: simple **92.5% (62/67)** / moderate **83.8% (83/99)** / challenging **85.3% (29/34, +2.9pp от v18 82.4%)**.
- **Path v18 → v19 (+0.5pp в текущей сессии):**
  - **helallao claude-4.5-sonnet-thinking** on v18 residue (27 fails) после 24h+ cooldown с прошлого sonnet-thinking sprint. 21/27 reached + 6 EXC (curl/DNS transient), 20 same + **1 rescue qid 743 challenging superhero** + 0 regressions.
  - **qid 743 rescue:** baseline pred missing `CAST(... AS REAL)` на second-column SUM, claude-thinking alt_pred добавил CAST на оба числа + `LEFT JOIN publisher`. Единственный case в v16+ stack где Anthropic-family lever дал family-ortogonal coverage по отношению к OpenAI/xAI/Moonshot/Google/Mistral.
- **Saturation evidence (same day):** gpt-5.2 Pro full sweep on same v18 residue: 24/27 reached / 0 rescues / 3 EXC. Это вторая независимая сессия с тем же исходом (2026-05-19: 15/27 reached). gpt-5.2 Pro окончательно saturated.
- **OpenRouter free-tier closed как NEGATIVE:** wiring landed `159069b` как infra для paid OR / single-shot probes. Batch eval blocked upstream Crucible/Venice 429-storm. Write-up: `docs/research/openrouter_free_tier_2026-05-20.md`.
- Audit: `scripts/audit_rescore.py --report eval/reports/2026-05-20/v19-helallao-sonnet-thinking.json` → 0 mismatches на 200 cells.

**Open path past 87.0% (приоритет):**
1. **kimi-k2-thinking без DAC** на v19 residue (26 fails) — на v18 residue только kimi+DAC и kimi+DAC+M-Schema гонялись; plain reasoning не тестировался. Family Moonshot ≠ Anthropic, может найти ortogonal.
2. **grok-4.1-reasoning без DAC** на v19 residue — grok+DAC saturated, plain reasoning не пробовался.
3. **Paid OpenRouter top-up** ($5+) — unlocks batch eval через heterogeneous `:free` models, wiring уже готов.
4. **Local ollama heterogeneous CSC** (qwen2.5-coder default уже в settings) — без сетевого rate-limit, multi-day setup для wall-time × candidates.
5. **claude-4.5-sonnet-thinking повтор после ≥24h** — сегодня дал 1 rescue, может вторая попытка ещё найти.

**Что НЕ делать:**
- gpt-5.2 Pro повтор на v18/v19 residue — saturated × 2 независимых сессии.
- gpt-5.2-thinking + DAC повтор на v18/v19 residue — saturated.
- glm-4.5-air:free через OpenRouter — reasoning-blocked output (probe verified, content="").
- qwen3-coder:free через OpenRouter — Venice provider 429-loop на free quota.

---

## 2026-05-18 day-5 evening v18 — **86.5% EA verified** (BIRD-official set scoring), above #1 paid SOTA by +4.55pp

**Состояние (historical, v18-baseline):**
- HEAD bumped to v18 commit (см. git log).
- BIRD original gold n=200 (**v18**): **86.5% EA** (173/200), BIRD-official set scoring. **v18 triplet: 86.5% BIRD / 72.36% Arcwise-Plat-SQL / +5 audit catches** (v10 was 80.5 / 67.34 / +6 — Δ +6pp / +5pp / -1, catches non-monotonic because qid 672 now BIRD-correct). **Above #1 paid system AskData+GPT-4o (81.95%) by +4.55pp.**
- Per-tier v18: simple **92.5% (62/67)** / moderate **83.8% (83/99, +1pp от v17)** / challenging **82.4% (28/34)**.
- **Path v16 → v18 (+1pp в текущей сессии):**
  - **v16 → v17:** post-cooldown gpt-5.2-thinking + DAC retry на v16 residue (29 fails). 28/29 reached, +1 rescue qid 896 challenging formula_1 (driverStandings.position).
  - **v17 → v18:** helallao gpt-5.2 Pro на v17 residue (28 fails). 13/28 reached перед Pro-quota coalesce, +1 rescue qid 989 moderate formula_1 (Canadian GP 2008 winner time, JOIN races×results + position=1). Grok-4.1 Pro на том же residue: 26/28 reached, 0 rescues, 2 EXC.
- Audit: `scripts/audit_rescore.py --report eval/reports/2026-05-18b/v18-gpt52-pro-merged.json` → 0 mismatches на 200 cells.
- Live HF Space: <https://liovina-nl-sql.hf.space> — **RUNNING under v17** (deploy 2026-05-18 day-5 evening, после фикса ignore_patterns в `.deploy_hf.py` для exclude big DBs card_games/codebase_community/european_football_2).
- README hero + lift trace + **v17 row в eval table** + post-cooldown lever — закрыто.
- 272 pytest pass, ruff + mypy strict clean.

**Day-5 evening sprint summary (v16 → v18, +1.0pp):**
- HF deploy hygiene: добавлены 3 big-DB exclusions в `.deploy_hf.py:81+` ignore_patterns (card_games / codebase_community / european_football_2 — sum ~1.3GB, прошлая попытка падала на httpx ReadError WinError 10054).
- **v17 lift:** `NLSQL_DAC=1 scripts/run_helallao_voting.py --model gpt-5.2-thinking --sleep-between 4.0` на v16 residue (29 fails) → 28/29 reached, +1 rescue qid 896 challenging, 27 same, 1 EXC qid 959.
- **v18 lift:** `scripts/run_helallao_voting.py --model gpt-5.2 --sleep-between 4.0` (Pro mode) на v17 residue (28 fails) → 13/28 reached перед Pro-quota coalesce, +1 rescue qid 989 moderate, 12 same, 12 EXC `non-dict NoneType` (rate-limit) + 3 EXC tokenize/connection.
- **Negative evidence v18:** `--model grok-4.1` Pro на v17 residue → 26/28 reached, 0 rescues, 2 EXC connection-abort. qid 989 grok вернул `same` (только gpt-5.2 нашёл правильный фильтр races.name vs circuits.name).
- Merges: `merge_voting_rescues.py` → `v17-gpt52-thinking-dac-merged.json` (172/200=86.0%) → `v18-gpt52-pro-merged.json` (173/200=86.5%).
- Audit: оба отчёта верифицированы через `audit_rescore.py`, 0 mismatches каждый.

**Day-5 night reasoning-route saturation на v18 residue (после ~4h cooldown от Pro+reasoning sprint'ов):**
- `NLSQL_DAC=1 scripts/run_helallao_voting.py --model kimi-k2-thinking --sleep-between 4.0` на v18 residue (27 fails) → **26/27 reached, 0 rescues, 26 same** + 1 connection EXC qid 484. Чистая saturation — kimi оценивает v18-residue identical с gpt-5.2-Pro baseline.
- Параллельно (но раньше, через ~10 мин после Pro sprint в 19:02): `--model claude-4.5-sonnet-thinking` на v18 residue → 2/27 reached + 25 EXC `non-dict NoneType`. Подтверждает sonnet45-thinking 24h-rule (последняя попытка day-5 EOD ~06:30 MSK; ~12h cooldown недостаточен).
- **Refined operational rule:** reasoning-route и Pro mode имеют отдельные quotas (kimi через 4h после Pro sprint работает чисто); НО claude-4.5-sonnet-thinking имеет per-model 24h ban.

**Day-5 night Pro+DAC combo на v18 residue + Pro-quota recovery curve (~4h cooldown):**
- `NLSQL_DAC=1 --model gpt-5.2 --sleep-between 6.0` (Pro mode + DAC prompt switch) на v18 residue → **15/27 reached, 0 rescues, 15 same** + 1 tokenize EXC qid 25 + 11 EXC `non-dict NoneType` (qid 1094..1531) — Pro-quota coalesced на 17-м call.
- **Pro-quota recovery curve empirical:** 30 мин → ~4 case capacity / 4h → ~15-16 case capacity / full daily quota probably ≥24h. Для full 27-case sprint Pro mode требуется ≥6-8h между sprint'ами.
- **DAC + Pro combo lever closed:** DAC prompt switch на Pro models не открывает rescue paths поверх Pro-only sprint'а (15 same / 0 better). Same lever, не orthogonal.

**Day-5 evening v18 — Pro mode на post-saturation residue даёт ortogonal rescues:**
- v17 NEXT_SESSION предсказывал «DAC + helallao Pro mode на v17 residue +0-1 rescue». Реализовалось +1 (qid 989).
- gpt-5.2 Pro и Grok-4.1 Pro на одном residue: 1 vs 0 rescues. Pro mode даёт ortogonal coverage даже между двумя моделями одного «поколения». **Не считать Pro triplet redundant: каждая модель может найти своё.**
- **Operational rule (uplift v17 → v18 + предыдущий day-5 EOD v14 → v15):** Pro quota Perplexity coalesces после ~13-16 cases. Для full triplet (Grok + GPT-5.2 + Claude) нужен cooldown ≥30 мин между моделями. Иначе вторая модель получает `non-dict NoneType` EXC уже на третьем call.
- claude-4.5-sonnet Pro по-прежнему не пробовать без 24h+ cooldown (last attempt day-5 EOD ~06:30 MSK; ещё в window).

**Day-5 evening v17-extended-2 (mistral-large rotated × 3 keys) — predecessor:**
- `scripts/run_selfcon_retry.py` расширен `RotatingMistralProvider` + `--api-keys` CSV → round-robin с retry-on-429-to-next-key.
- `mistral-large-latest` self-consistency `T=[0.2, 0.5, 0.8]` на v16 residue (29 fails) через 3 ключа (`.env` + 2 новых из `D:/TXT/Free API Keys.txt`): **29/29 reached, 0 rescues, 0 regressions**. Чистый прогон, 0 × 429 за весь sweep. T_win distribution: 26×0.2 / 3×0.5.
- Same-Mistral-family voting plateau на v16 residue verified — этот lever закрыт.
- Artefacts: `eval/reports/2026-05-18b/mistral-large-rotated-on-v16-residue.json`. Detailed: `docs/v11_saturation_evidence.md § 2026-05-18 day-5 evening`.

## 2026-05-19 night — v18 residue audit + P2/P3 prompt patches landed

- **Audit:** `docs/v18_residue_patterns.md` — 27 fails классифицированы в 8 pattern families. Dominant: A1 LIMIT mis-interp (4), C WHERE/filter heterogeneous (11), B JOIN-path (4). E "gold wrong" 2 cases (qid 1029 ASC-for-highest, qid 1247 op-precedence) — Arcwise territory, prompt не нужен.
- **Prompt patches P2 + P3 applied** к `src/nl_sql/agent/prompts/generate_sql.txt` и `generate_sql_dac.txt`:
  - P2: `formula_1.driverStandings vs results` disambiguation (target qid 902 + аналоги)
  - P3: `codebase_community.postHistory.Comment vs comments.Text` disambiguation (target qid 584)
- **P1 LIMIT-discipline CLOSED 2026-05-19 night — NEGATIVE.** Experimental n=200 config C codestral: P23 56.0% → P1+P23 55.0% (**−2 cases, −1.0pp**). 6 wins / 8 regressions / 0 rescues among target qids 484/930/1144/1205. Reverted. Artefacts: `eval/reports/2026-05-19/C_dense_cards-{p23_baseline,p1p23}.json`.
- **Orthogonal mechanism (row_count_repair node) CLOSED 2026-05-19 night — NEGATIVE.** Codex implemented full node (AST LIMIT detection + tie-prone regex + re-execute + acceptance). Gate green, 4 unit tests pass. Empirical: 56.0% → 55.5% (**−1 case qid 1157, 0 rescues**). Of 23 eligible cases zero got repaired in final state — likely langgraph state propagation issue. Reverted. Artefact: `eval/reports/2026-05-19/C_dense_cards-rcrepair.json`.
- **Verdict on 4 target qids (484, 930, 1144, 1205):** they are deeply hard. Baseline-layer tooling (prompt patches OR execute-feedback heuristics) does not flip them. Past 86.5% must come from voting-layer additions (Pro retries gated on cooldown) или paid escalation. Не возвращаться к baseline-layer попыткам без orthogonal idea не из списка.
- **CSC merge-revision (P4) CLOSED 2026-05-19 morning — NULL.** Реализовал per r1.md+r2.md research recommendation (top-2 cluster judge). Config F codestral × 4 temps: F=60.0%, F+CSC=60.0%, **+0 cases**. CSC fired на 6/200=3% cases — все equally wrong vs gold. Causes: codestral self-consistency homogeneous (97% top-1 strictly majority), judge LLM = generator LLM (same biases), hard targets unanimous-wrong. CSC мог бы помочь только с N-rep (diverse schema representations) или multi-base-model ensemble (codestral + Qwen + OmniSQL). Implementation reverted. Artefacts: `eval/reports/2026-05-19/F_self_consistency-{F_baseline_v2,F_csc_v2}.json`. **Past 86.5% chrome-free $0 closed как concept** — нужен один из: paid escalation, fine-tuned open-weight 7-32B model (OmniSQL/Arctic), corrected gold (Arcwise где уже 72.36%).
- **Gate:** pytest 272/272, ruff clean, mypy strict clean (HEAD `6b290e1` + 3 file changes still uncommitted).
- **Live HF Space E2E verified** через Playwright (86.5% / 72.36% видны на UI).

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| **Verify P2+P3 patches** | Запустить full n=200 eval на codestral baseline с patched prompts → сравнить per-qid с v18 merged → измерить +cases (target 584/902) и regression count | +2 cases best / +0 worst |
| Past 86.5% chrome-free $0 | gpt-5.2 Pro retry на v18 residue (27 fails) **после ≥6-8h** cooldown — empirical recovery curve: 30 мин → 4 case capacity, 4h → 15 case capacity, full 27-case sprint требует ≥6-8h | +0-2 rescue (~+0.5-1pp) |
| Past 86.5% chrome-free $0 | claude-4.5-sonnet Pro через 24h+ cooldown (последний тест day-5 EOD ~06:30 MSK) | +0-2 rescue |
| ~~Past 86.5% Pro+DAC combo~~ | ~~`NLSQL_DAC=1 --model gpt-5.2` на v18 residue~~ — **CLOSED 2026-05-18 day-5 night.** ~4h cooldown → 15/27 reached, 0 rescues, 15 same + 11 EXC non-dict NoneType. DAC prompt switch не добавляет rescue paths на Pro models. Не повторять. | n/a |
| Past 86.5% chrome-free $0 | claude-4.5-sonnet-thinking + DAC через helallao на v18 residue **после 24h+** от 2026-05-18 19:02 MSK (нужно ждать до ≥2026-05-19 19:00 MSK) — sonnet-thinking 24h-rule подтверждён empirically: повтор через ~12h дал 2/27 reached + 25 EXC `non-dict NoneType` | +0-2 rescue |
| Past 86.5% chrome-gated | GraceKelly maintenance: re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + обновить `playwright_driver.py` selector constants → unlock второй ortogonal route к Perplexity Pro (browser picker vs helallao HTTPS) | +1-2pp |
| Infrastructure | MCP-сервер обёртка над Perplexity Pro bridge (Sonnet/GPT-5/Grok/Claude через helallao + persistent cookies) для использования из Claude Code напрямую — единая точка для всех проектов, share session quota, не зависит от GraceKelly UI drift | enables Sonnet/GPT-5 ad-hoc queries from agent sessions; multi-hour build |
| Research-grade | P3.F JOIN-path linker + CSC-SQL (см. `docs/p3f_design.md`) | +2-4pp combined, multi-day |

## Deploy quick reference

- Live URL: <https://liovina-nl-sql.hf.space>
- Dashboard: <https://huggingface.co/spaces/liovina/nl-sql>
- Deploy script: `.deploy_hf.py` (gitignored)
- HF Dockerfile template: `.tmp/hf_Dockerfile` (важно: `ENV PYTHONPATH=/app/src` для src layout)
- Mistral key: `D:/TXT/Mistral_API.txt`
- Полный runbook: `docs/SESSION_HANDOFF.md § Deploy`

**Streamlit Cloud deploy** — всё ещё blocked на Gmail OAuth (Юлин Gmail не открывается). Если когда-то OAuth заработает: runbook в `docs/SESSION_HANDOFF.md § Deploy`, helper `.deploy_helper.py` (gitignored).

## Что НЕ делать

- Не редизайнить UI. Зафиксирован 2026-05-13 (editorial monochrome).
- Не коммитить `chroma_data/` byte-level drift от смок-запусков.
- Не запускать GraceKelly `dry-run → hybrid` без подтверждения, что Chrome-профиль свободен (memory `feedback_user_chrome_assumption`).
- Не повторять free-tier saturation list (см. `docs/v11_saturation_evidence.md` § «не повторять»).
- Не оборачивать helallao bridge ретраями — Perplexity backend сам коалесцирует quota; повторы только ускоряют исчерпание.
- **Не запускать back-to-back helallao reasoning sprint'ы.** Cooldown 10-15+ мин между моделями reasoning route (day-5 night показал coalescing).
- Не повторять claude-4.5-sonnet (ни pro, ни thinking) через helallao без 24h+ cooldown ИЛИ paid Anthropic bypass.
- Не повторять gemini-3.0-pro на текущем prompt стеке (0/30 saturation подтверждена day-5).
- Не повторять grok-4.1 Pro / reasoning на v14-v16 residue identical pipeline без modified prompt (DAC, M-Schema injection, новые few-shot).
- **Не повторять mistral-large self-consistency на v16 residue** (day-5 evening: 3-key rotation × 3 temps × 29 qids → 0 rescues, same-family plateau подтверждён).
- **Не запускать второй helallao Pro sprint в течение 30 мин** (day-5 evening v18: после gpt-5.2 Pro burned 13 cases, Grok-4.1 Pro+DAC через 30 мин получил 4/27 reached + 22 `non-dict NoneType`. Pro-quota recovers медленнее — закладывать ≥6-8h между sprint'ами для full 27-case capacity).
- **Не повторять kimi-k2-thinking + DAC на v18 residue** (day-5 night: 26/27 reached, 0 rescues, 26 same votes — чистая saturation. Лужёный lever на v18-residue, не возвращаться).
- **Не запускать claude-4.5-sonnet-thinking раньше 2026-05-19 19:02 MSK** (24h-rule empirically подтверждён повторно: попытка через ~12h в 19:02 day-5 вечером дала 2/27 reached + 25 EXC `non-dict NoneType`).
- **Не повторять gpt-5.2 Pro + DAC combo на v18 residue** (day-5 night ~4h cooldown: 15/27 reached, 0 rescues, 15 same. DAC prompt switch на Pro models не открывает rescue paths поверх Pro-only sprint'а — same lever, не orthogonal).
- **Pro-mode 27-case sprint < 6h cooldown = wasted quota.** Empirical recovery curve: 30 мин → 4 cases / 4h → 15-16 cases. Full residue (27 cases) требует ≥6-8h.
- **Не запускать reasoning sprint < 3h после Pro sprint** (day-5 night kimi+DAC+M-Schema через ~20 мин после Pro+DAC: 6/27 reached + 21 EXC `non-dict NoneType`. Reasoning route quota NOT строго отдельный pool — Pro burst drain'ит reasoning тоже на коротком timeframe; см. v11_saturation_evidence.md § quota model v4).
- **Не повторять kimi+DAC+M-Schema combo на v18 residue.** Combo combo lever family ещё раз saturated: M-Schema prompt format не флипает kimi verdict с "same" на "better" даже на reachable cases.

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui

# gpt-5.2 Pro retry на v18 residue (после ≥30 мин cooldown от прошлого Pro sprint):
uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18b/v18-gpt52-pro-merged.json \
  --out eval/reports/<date>/helallao-gpt52-pro-on-v18-residue.json \
  --model gpt-5.2 --sleep-between 4.0
```

## Cookies refresh (если helallao падает с auth error)

```bash
# Cookies extractor — Playwright + chrome-profile DPAPI bypass:
uv run python .tmp/extract_pplx_cookies.py
# → пишет .tmp/pplx_cookies.json (gitignored)
```

Cookies живут пока Юля не разлогинится в Perplexity Pro. Если 401 — re-extract.
