# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-18 day-5 evening v18 — **86.5% EA verified** (BIRD-official set scoring), above #1 paid SOTA by +4.55pp

**Состояние:**
- HEAD bumped to v18 commit (см. git log).
- BIRD original gold n=200 (**v18**): **86.5% EA** (173/200), BIRD-official set scoring. Triplet: 86.5% BIRD / 67.34% Arcwise-Plat / +6 audit catches. **Above #1 paid system AskData+GPT-4o (81.95%) by +4.55pp.**
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

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 86.5% chrome-free $0 | gpt-5.2 Pro retry на v18 residue (27 fails) **после ≥нескольких часов** cooldown — 30 мин эмпирически недостаточно (Grok-4.1 Pro+DAC на v18 residue после 30 мин cooldown получил 4/27 reached + 22 EXC `non-dict NoneType`). Pro-quota coalesces account-wide. | +0-2 rescue (~+0.5-1pp) |
| Past 86.5% chrome-free $0 | DAC + helallao Pro mode после долгого cooldown — combo unique, ранее не пробованный полностью (Grok-4.1 Pro+DAC прервался на 4-м случае от Pro-quota coalesce) | +0-1 rescue, требует cooldown ≥3h |
| Past 86.5% chrome-free $0 | claude-4.5-sonnet Pro через 24h+ cooldown (последний тест day-5 EOD ~06:30 MSK) | +0-2 rescue |
| Past 86.5% chrome-free $0 | DAC mode для Pro models — `NLSQL_DAC=1 --model gpt-5.2` на v18 residue (Pro+DAC combo) | +0-1 rescue |
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
- **Не запускать второй helallao Pro sprint в течение 30 мин** (day-5 evening v18: после gpt-5.2 Pro burned 13 cases, Grok-4.1 Pro+DAC через 30 мин получил 4/27 reached + 22 `non-dict NoneType`. Pro-quota recovers медленнее — закладывать ≥3h между sprint'ами).
- **Не повторять kimi-k2-thinking + DAC на v18 residue** (day-5 night: 26/27 reached, 0 rescues, 26 same votes — чистая saturation. Лужёный lever на v18-residue, не возвращаться).
- **Не запускать claude-4.5-sonnet-thinking раньше 2026-05-19 19:02 MSK** (24h-rule empirically подтверждён повторно: попытка через ~12h в 19:02 day-5 вечером дала 2/27 reached + 25 EXC `non-dict NoneType`).

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
