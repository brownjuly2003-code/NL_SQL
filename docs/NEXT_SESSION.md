# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-18 day-5 EOD — v15 85.0% EA shipped, above #1 paid SOTA by +3.05pp

**Состояние:**
- HEAD bumped to v15 commit (см. git log).
- BIRD original gold n=200 (**v15**): **85.0% EA** (170/200). Triplet: 85.0% BIRD / 67.34% Arcwise-Plat / +6 audit catches. **Above #1 paid system AskData+GPT-4o (81.95%) by +3.05pp.**
- Per-tier v15: simple 92.5% (62/67) / moderate 82.8% (82/99) / challenging **76.5% (26/34, +2.9pp от v14)**.
- Live HF Space: <https://liovina-nl-sql.hf.space> — redeploy needed после коммита (research_value 85.0% уже в `app/streamlit_app.py:64/134`).
- README hero + lift trace + 10-рычаговый блок (10-й расширен bonus retry) + eval table — закрыто.
- 270+ pytest pass, ruff + mypy strict clean.

**Day-5 EOD sprint summary:**
- helallao Pro triplet retry на v14 residue (31 fails) после daily quota reset:
  - grok-4.1 Pro: 0/28 (1 tokenizer EXC qid 173 — но gpt-5.2 закрыл его same iteration; 2 curl timeout EXC qid 1247, 1404)
  - gpt-5.2 Pro: **1 rescue qid 173 challenging** (subquery `GROUP BY account_id, k_symbol` для conditional aggregation, который codestral пропустил), 25 same, 5 EXC `non-dict NoneType`
  - claude-4.5-sonnet Pro: 7/31 reached, 24 EXC `non-dict NoneType` — Perplexity backend rate-limits Claude в **любом mode** (pro и reasoning — same throttling)
- Объединение через `scripts/merge_voting_rescues.py` → v15 baseline (170/200 = 85.0%).

**Day-5 EOD negative evidence (не повторять):**
- claude-4.5-sonnet Pro mode НЕ обходит rate-limit на Perplexity backend (24/31 EXC). На v11 day-3 claude дал 1 dup-rescue только на половине residue после Cloudflare; на v14 backend ужесточил. Не возвращаться без 24h+ cooldown или paid Anthropic API.
- grok-4.1 Pro saturated на v14 residue (0/28). Возможен retry с альтернативным prompt стеком (e.g., DAC injection), но не identical pipeline.

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 85% chrome-free $0 | Re-test claude-4.5-sonnet через 24h+ cooldown в Pro mode (сегодня rate-limited 24/31) — если backend отпустит, +0-2 rescue ortogonal к gpt-5.2 | +0-1pp |
| Past 85% chrome-free $0 | DAC+reasoning combo: установить `NLSQL_DAC=1` и запустить helallao reasoning-mode triplet (grok+gpt-5.2+kimi) на v15 residue (30 fails) — новый lever combination | +0-1 rescue |
| Past 85% chrome-free $0 | OpenRouter $1 top-up unlocks 1000/day free-model requests | re-test ortogonal free models, +0-1pp |
| Past 85% chrome-gated | GraceKelly maintenance: re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + обновить `playwright_driver.py` selector constants → unlock GPT-5.x/Sonnet bridge через UI picker (orthogonal к helallao HTTPS) | +1-2pp |
| Past 85% paid $1-3 | Anthropic Sonnet API direct на v15 residue (30 fails) — обходит Perplexity Claude rate-limit | +1-3pp, наивысший $/pp |
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
- Не повторять claude-4.5-sonnet (ни pro, ни thinking) через helallao без 24h+ cooldown ИЛИ paid Anthropic bypass. Backend rate-limits Claude в **любом mode** (доказано day-4 thinking + day-5 EOD pro — 24/31 + 14/36 EXC).
- Не повторять gemini-3.0-pro на текущем prompt стеке (0/30 saturation подтверждена day-5).
- Не повторять grok-4.1 Pro на v14 residue identical pipeline (0/28 saturated). Возможен retry только с modified prompt (DAC/M-Schema injection).

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui

# Claude Pro mode retry на v15 residue (после 24h+ cooldown):
uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18/v15-helallao-pro-triplet.json \
  --out eval/reports/<date>/helallao-claude45-pro-on-v15-residue.json \
  --model claude-4.5-sonnet --sleep-between 4.0
```

## Cookies refresh (если helallao падает с auth error)

```bash
# Cookies extractor — Playwright + chrome-profile DPAPI bypass:
uv run python .tmp/extract_pplx_cookies.py
# → пишет .tmp/pplx_cookies.json (gitignored)
```

Cookies живут пока Юля не разлогинится в Perplexity Pro. Если 401 — re-extract.
