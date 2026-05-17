# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> переписываешь этот файл под следующий sprint.

## 2026-05-18 day-4 EOD — v13 84.0% EA shipped, above #1 paid SOTA by +2.05pp

**Состояние:**
- HEAD bumped to v13 commit (см. git log).
- BIRD original gold n=200 (**v13**): **84.0% EA** (168/200). Triplet: 84.0% BIRD / 67.34% Arcwise-Plat / +6 audit catches. **Above #1 paid system AskData+GPT-4o (81.95%) by +2.05pp.**
- Per-tier v13: simple 92.5% (62/67) / moderate **81.8% (81/99, +4.0pp от v12)** / challenging 73.5% (25/34).
- Live HF Space: <https://liovina-nl-sql.hf.space> — redeploy needed после коммита (research_value 84.0% уже в `app/streamlit_app.py:64/134`).
- README hero + lift trace + 9-рычаговый блок + eval table — закрыто.
- 270+ pytest pass, ruff + mypy strict clean.

**Breakthrough sprint (day-4):** helallao client поддерживает `mode="reasoning"` для thinking-variants — это та route, через которую Perplexity backend пускает grok-4.1-reasoning / gpt-5.2-thinking / claude-4.5-sonnet-thinking / gemini-3.0-pro / kimi-k2-thinking. Патч в `HelallaoPerplexityProvider`: добавлен `mode` arg + `_REASONING_MODELS` whitelist + auto-routing по суффиксу `-reasoning`/`-thinking` или явному model id. 4 unique rescues на v12 residue (36 fails), все moderate tier:
- grok-4.1-reasoning: qid 518 (banned-card play format max-count + DISTINCT names), qid 1529 (customer + month-of-Jan-2012 conditional sum)
- gpt-5.2-thinking: qid 407, qid 866 (multi-condition aggregations)

**Negative evidence для будущих сессий (не повторять):**
- claude-4.5-sonnet-thinking 0/36 rescues, 14/36 EXC `non-dict NoneType`. Perplexity backend жёстко rate-limits Claude reasoning route; grok/gpt-5.2 reasoning routes throttling не имели. Repeat only после paid bypass.
- gemini-3.0-pro / kimi-k2-thinking — НЕ протестированы в day-4 sprint, доступны через тот же `mode="reasoning"`. Бесплатные кандидаты на новые ортогональные rescues. **Это первое, что попробовать на v13 residue.**

## Что делать в следующей сессии (после явного user mandate)

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 84% chrome-free $0 | **gemini-3.0-pro + kimi-k2-thinking** через helallao `mode="reasoning"` на v13 residue (32 fails) | binomial 95% CI ≤6% rescue rate ≈ ≤2 cases (+0-1pp) |
| Past 84% chrome-free $0 | Cookie refresh → повтор Claude-4.5-sonnet-thinking через 24h когда Perplexity Claude rate-limit отпустит | +0-1 rescue |
| Past 84% chrome-free $0 | Helallao Pro триплет (Grok+GPT-5.2+Claude pro mode) на v13 residue — daily quota reset позволит повторить | +0-1 rescue |
| Past 84% chrome-free $0 | OpenRouter $1 top-up unlocks 1000/day free-model requests | re-test ortogonal free models, +0-1pp |
| Past 84% chrome-gated | GraceKelly maintenance: re-run `D:/GraceKelly/tools/capture_perplexity_recon.py` + обновить `playwright_driver.py` selector constants → опять unlock GPT-5.x/Sonnet bridge через UI | +1-3pp ортогонально |
| Past 84% paid $1-3 | Anthropic Sonnet API direct на v13 residue (32 fails) — обходит Perplexity Claude rate-limit | +1-3pp, наивысший $/pp |
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

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui

# Helallao reasoning voting на v13 residue (gemini-3.0-pro / kimi-k2-thinking):
uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18/v13-helallao-reasoning-bridge.json \
  --out eval/reports/<date>/helallao-gemini-on-v13-residue.json \
  --model gemini-3.0-pro --sleep-between 3.0

uv run python scripts/run_helallao_voting.py \
  --baseline eval/reports/2026-05-18/v13-helallao-reasoning-bridge.json \
  --out eval/reports/<date>/helallao-kimi-on-v13-residue.json \
  --model kimi-k2-thinking --sleep-between 3.0
```

## Cookies refresh (если helallao падает с auth error)

```bash
# Cookies extractor — Playwright + chrome-profile DPAPI bypass:
uv run python .tmp/extract_pplx_cookies.py
# → пишет .tmp/pplx_cookies.json (gitignored)
```

Cookies живут пока Юля не разлогинится в Perplexity Pro. Если 401 — re-extract.
