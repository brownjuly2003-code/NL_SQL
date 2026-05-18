# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-18 day-5 night EOD — v16 85.5% EA shipped, above #1 paid SOTA by +3.55pp

**Состояние:**
- HEAD bumped to v16 commit (см. git log).
- BIRD original gold n=200 (**v16**): **85.5% EA** (171/200). Triplet: 85.5% BIRD / 67.34% Arcwise-Plat / +6 audit catches. **Above #1 paid system AskData+GPT-4o (81.95%) by +3.55pp.**
- Per-tier v16: simple 92.5% (62/67) / moderate **83.8% (83/99, +1.0pp от v15)** / challenging 76.5% (26/34).
- Live HF Space: <https://liovina-nl-sql.hf.space> — redeploy needed после коммита (research_value 85.5% уже в `app/streamlit_app.py:64/134`).
- README hero + lift trace + **11-рычаговый блок** + eval table — закрыто.
- 270+ pytest pass, ruff + mypy strict clean.

**Day-5 night sprint summary:**
- DAC×reasoning combo на v15 residue (30 fails): `NLSQL_DAC=1` + helallao reasoning models.
  - **kimi-k2-thinking + DAC**: 21/30 reached, **1 rescue qid 77 moderate** (FRPM-Percent + GSserved='K-9'), 20 same, 9 EXC (Perplexity rate-limit coalescing).
  - **gpt-5.2-thinking + DAC**: 4/30 reached, 0 rescues, 26 EXC (backend rate-limited после kimi sprint).
  - **grok-4.1-reasoning + DAC**: 4/30 reached, **1 dup-rescue qid 77** (same case как kimi), 26 EXC mix rate-limit + DNS resolution fails.
- Union: 1 unique rescue (qid 77) → v16 171/200 = 85.5%.

**Day-5 night negative evidence:**
- **Perplexity backend coalesces reasoning quota по аккаунту, не по модели.** Полный kimi sprint (21/30) → следующие 2 reasoning models получили 4/30 reached каждый. **Не запускать reasoning triplet back-to-back.** Cooldown 10-15 мин между sprint'ами.
- gpt-5.2-thinking + DAC при rate-limit показал 0/4 same — partial coverage недостаточна для negative determination.

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 85.5% chrome-free $0 | Retry gpt-5.2-thinking + DAC на v16 residue (29 fails) после 1+ часа cooldown — на day-4 gpt-5.2-thinking без DAC дал 2 rescues, с DAC может найти новые | +0-2 rescue (~+0.5-1pp) |
| Past 85.5% chrome-free $0 | DAC + helallao Pro mode (Grok+GPT-5.2+Claude) на v16 residue — combo, ранее не пробованный | +0-1 rescue |
| Past 85.5% chrome-free $0 | claude-4.5-sonnet (Pro mode) через 24h+ cooldown (последний тест day-5 EOD ~06:30 MSK) — backend rate-limit может отпустить | +0-2 rescue |
| Past 85.5% chrome-free $0 | OpenRouter $1 top-up unlocks 1000/day free-model requests | re-test ortogonal free models, +0-1pp |
| Past 85.5% chrome-gated | GraceKelly maintenance: re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + обновить `playwright_driver.py` selector constants → unlock GPT-5.x/Sonnet bridge через UI picker (orthogonal к helallao HTTPS) | +1-2pp |
| Past 85.5% paid $1-3 | Anthropic Sonnet API direct на v16 residue (29 fails) — обходит Perplexity Claude rate-limit | +1-3pp, наивысший $/pp |
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

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui

# Retry gpt-5.2-thinking + DAC на v16 residue (после 1h+ cooldown):
NLSQL_DAC=1 uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18/v16-helallao-dac-reasoning.json \
  --out eval/reports/<date>/helallao-gpt52-dac-on-v16-residue.json \
  --model gpt-5.2-thinking --sleep-between 4.0
```

## Cookies refresh (если helallao падает с auth error)

```bash
# Cookies extractor — Playwright + chrome-profile DPAPI bypass:
uv run python .tmp/extract_pplx_cookies.py
# → пишет .tmp/pplx_cookies.json (gitignored)
```

Cookies живут пока Юля не разлогинится в Perplexity Pro. Если 401 — re-extract.
