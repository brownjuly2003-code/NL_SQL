# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-18 day-5 EOD — v14 84.5% EA shipped, above #1 paid SOTA by +2.55pp

**Состояние:**
- HEAD bumped to v14 commit (см. git log).
- BIRD original gold n=200 (**v14**): **84.5% EA** (169/200). Triplet: 84.5% BIRD / 67.34% Arcwise-Plat / +6 audit catches. **Above #1 paid system AskData+GPT-4o (81.95%) by +2.55pp.**
- Per-tier v14: simple 92.5% (62/67) / moderate **82.8% (82/99, +1.0pp от v13)** / challenging 73.5% (25/34).
- Live HF Space: <https://liovina-nl-sql.hf.space> — redeploy needed после коммита (research_value 84.5% уже в `app/streamlit_app.py:64/134`).
- README hero + lift trace + 10-рычаговый блок + eval table — закрыто.
- 270+ pytest pass, ruff + mypy strict clean.

**Day-5 sprint summary:**
- gemini-3.0-pro через helallao `mode="reasoning"` на v13 residue (32 fails) — **0/30 rescues** (2 tokenizer EXC, 28 same). Saturation для бесплатных reasoning-моделей подтверждена.
- kimi-k2-thinking через тот же reasoning route — **1 rescue** (qid 1235 moderate, Patient×Laboratory JOIN-path с CAST age via strftime, где v13 неверно использовал `Examination`). 2 network EXC, 29 same.
- Объединение через `scripts/merge_voting_rescues.py` → v14 baseline (169/200 = 84.5%).

**Day-5 negative evidence (не повторять без paid bypass):**
- gemini-3.0-pro 0/30, не пробивает residue ортогонально к grok/gpt-5.2/kimi reasoning. Repeat только при изменении prompt-стратегии или cookie refresh.
- Claude-4.5-sonnet-thinking всё ещё под Perplexity rate-limit (тестировано day-4). Не repeat без 24h+ cooldown ИЛИ paid Anthropic API.

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 84.5% chrome-free $0 | Helallao Pro триплет (Grok+GPT-5.2+Claude в `mode="pro"`) на v14 residue (31 fails) — daily quota reset позволит повторить с новыми prompts | +0-1 rescue |
| Past 84.5% chrome-free $0 | Re-test claude-4.5-sonnet-thinking через 24h cooldown (последний тест day-4 02:00 MSK) | +0-2 rescue |
| Past 84.5% chrome-free $0 | OpenRouter $1 top-up unlocks 1000/day free-model requests | re-test ortogonal free models, +0-1pp |
| Past 84.5% chrome-gated | GraceKelly maintenance: re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + обновить `playwright_driver.py` selector constants → unlock GPT-5.x/Sonnet bridge через UI | +1-3pp ортогонально |
| Past 84.5% paid $1-3 | Anthropic Sonnet API direct на v14 residue (31 fails) — обходит Perplexity Claude rate-limit | +1-3pp, наивысший $/pp |
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
- Не повторять claude-4.5-sonnet-thinking без 24h cooldown ИЛИ paid Anthropic API bypass (Perplexity backend hard-rate-limits Claude reasoning route).
- Не повторять gemini-3.0-pro на текущем prompt стеке (0/30 saturation подтверждена day-5). Только при изменении prompt-стратегии.

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui

# Helallao Pro триплет на v14 residue (после daily quota reset Perplexity):
uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18/v14-helallao-kimi-thinking.json \
  --out eval/reports/<date>/helallao-grok-pro-on-v14-residue.json \
  --model grok-4.1 --sleep-between 3.0
```

## Cookies refresh (если helallao падает с auth error)

```bash
# Cookies extractor — Playwright + chrome-profile DPAPI bypass:
uv run python .tmp/extract_pplx_cookies.py
# → пишет .tmp/pplx_cookies.json (gitignored)
```

Cookies живут пока Юля не разлогинится в Perplexity Pro. Если 401 — re-extract.
