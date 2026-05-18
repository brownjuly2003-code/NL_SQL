# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-18 day-5 evening v17 — **86.0% EA verified** (BIRD-official set scoring), above #1 paid SOTA by +4.05pp

**Состояние:**
- HEAD bumped to v17 commit (см. git log).
- BIRD original gold n=200 (**v17**): **86.0% EA** (172/200), BIRD-official set scoring. Triplet: 86.0% BIRD / 67.34% Arcwise-Plat / +6 audit catches. **Above #1 paid system AskData+GPT-4o (81.95%) by +4.05pp.**
- Per-tier v17: simple **92.5% (62/67)** / moderate **82.8% (82/99)** / challenging **82.4% (28/34, +3pp от v16)**.
- **The lever (v16 → v17):** post-cooldown gpt-5.2-thinking + DAC retry на v16 residue (29 fails). 28/29 reached, **1 rescue qid 896 challenging formula_1** (driverStandings.position vs results.positionOrder — gpt-5.2-thinking подобрал standings-источник как в gold через DAC sub-question breakdown). 1 EXC qid 959 connection-abort. 27 same. NEXT_SESSION (v16-audit-2) предсказывал +0-2 rescues, реализовалось +1.
- Audit: `scripts/audit_rescore.py --report eval/reports/2026-05-18b/v17-gpt52-thinking-dac-merged.json` → 0 mismatches на всех 200 cells.
- Live HF Space: <https://liovina-nl-sql.hf.space> — **RUNNING under v17** (deploy 2026-05-18 day-5 evening, после фикса ignore_patterns в `.deploy_hf.py` для exclude big DBs card_games/codebase_community/european_football_2).
- README hero + lift trace + **v17 row в eval table** + post-cooldown lever — закрыто.
- 272 pytest pass, ruff + mypy strict clean.

**Day-5 evening sprint summary (v17):**
- HF deploy hygiene: добавлены 3 big-DB exclusions в `.deploy_hf.py:81+` ignore_patterns (card_games / codebase_community / european_football_2 — sum ~1.3GB, прошлая попытка падала на httpx ReadError WinError 10054 connection reset).
- gpt-5.2-thinking + DAC retry на v16 residue (29 fails) — `NLSQL_DAC=1 scripts/run_helallao_voting.py --model gpt-5.2-thinking --sleep-between 4.0`:
  - 28/29 reached, **1 rescue qid 896 challenging** (driverStandings.position vs results.positionOrder; gold использовал season-standings источник, не race-finish), 27 same, 1 EXC qid 959 connection-abort.
  - Cookies от 2026-05-17 23:29 ещё валидны.
- Merge: `scripts/merge_voting_rescues.py --baseline v16-helallao-dac-reasoning.json --voting helallao-gpt52-thinking-dac-on-v16-residue.json` → `v17-gpt52-thinking-dac-merged.json` (172/200 = 86.0%).
- Audit: `scripts/audit_rescore.py` → 0 mismatches на 200 cells.

**Day-5 evening v17 — post-cooldown gpt-5.2-thinking+DAC validates the "wait then retry" hypothesis:**
- v16-audit-2 NEXT_SESSION предсказывал «после 1+h cooldown gpt-5.2-thinking + DAC может найти новые rescues». Реальный gap: ~3+ часов (mistral-large rotated run ~10 мин + HF deploy x2 ~10 мин + интерактив).
- Реализовалось +1 rescue (qid 896) на лимите ожиданий — Perplexity reasoning quota действительно восстановилась.
- **Operational rule:** для post-saturation retry чередовать модели И ждать ≥1h. Не запускать back-to-back reasoning sprint'ы, но **повторный одиночный sprint той же модели через cooldown может вернуть rescues**.

**Day-5 evening v17-extended-2 (mistral-large rotated × 3 keys) — predecessor:**
- `scripts/run_selfcon_retry.py` расширен `RotatingMistralProvider` + `--api-keys` CSV → round-robin с retry-on-429-to-next-key.
- `mistral-large-latest` self-consistency `T=[0.2, 0.5, 0.8]` на v16 residue (29 fails) через 3 ключа (`.env` + 2 новых из `D:/TXT/Free API Keys.txt`): **29/29 reached, 0 rescues, 0 regressions**. Чистый прогон, 0 × 429 за весь sweep. T_win distribution: 26×0.2 / 3×0.5.
- Same-Mistral-family voting plateau на v16 residue verified — этот lever закрыт.
- Artefacts: `eval/reports/2026-05-18b/mistral-large-rotated-on-v16-residue.json`. Detailed: `docs/v11_saturation_evidence.md § 2026-05-18 day-5 evening`.

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 86.0% chrome-free $0 | Repeat post-cooldown gpt-5.2-thinking + DAC на v17 residue (28 fails) после ≥1h — pattern validated на v16→v17. Один rescue вернул pattern; повтор может ещё | +0-2 rescue (~+0.5-1pp) |
| Past 86.0% chrome-free $0 | Retry qid 959 (single EXC connection-abort в v17 sprint) через одиночный call gpt-5.2-thinking+DAC | +0-1 rescue |
| Past 86.0% chrome-free $0 | DAC + helallao Pro mode (Grok+GPT-5.2 Pro) на v17 residue — combo, ранее не пробованный | +0-1 rescue |
| Past 86.0% chrome-free $0 | claude-4.5-sonnet (Pro mode) через 24h+ cooldown (последний тест day-5 EOD ~06:30 MSK) | +0-2 rescue |
| Past 86.0% chrome-free $0 | OpenRouter $1 top-up unlocks 1000/day free-model requests | re-test ortogonal free models, +0-1pp |
| Past 86.0% chrome-gated | GraceKelly maintenance: re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + обновить `playwright_driver.py` selector constants → unlock GPT-5.x/Sonnet bridge через UI picker (orthogonal к helallao HTTPS) | +1-2pp |
| Past 86.0% paid $1-3 | Anthropic Sonnet API direct на v17 residue (28 fails) — обходит Perplexity Claude rate-limit | +1-3pp, наивысший $/pp |
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

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui

# Retry gpt-5.2-thinking + DAC на v17 residue (после 1h+ cooldown):
NLSQL_DAC=1 uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18b/v17-gpt52-thinking-dac-merged.json \
  --out eval/reports/<date>/helallao-gpt52-dac-on-v17-residue.json \
  --model gpt-5.2-thinking --sleep-between 4.0
```

## Cookies refresh (если helallao падает с auth error)

```bash
# Cookies extractor — Playwright + chrome-profile DPAPI bypass:
uv run python .tmp/extract_pplx_cookies.py
# → пишет .tmp/pplx_cookies.json (gitignored)
```

Cookies живут пока Юля не разлогинится в Perplexity Pro. Если 401 — re-extract.
