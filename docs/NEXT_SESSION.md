# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> удаляешь этот файл (или переписываешь под следующий sprint).

## Контекст на 2026-05-17 EOS

- HEAD `e0ea5ad` (после 9370070 + P2.B fewshot5-residue lift + HF Dockerfile fix)
- BIRD Mini-Dev n=200: **77.5% EA** (155/200), per tier 89.6/74.7/61.8 (v7 = v6 + selective fewshot_top_k=5 on residue, +1 rescue qid=1500)
- **Live demo:** <https://liovina-nl-sql.hf.space> RUNNING, headline 77.5% / 200
- 270 pytest pass, ruff + mypy strict clean (55 source files)
- Streamlit UI editorial monochrome + EN/RU (закрыто 2026-05-13)
- Portfolio screenshots: `docs/ui-2026-05-17-{en,ru}.png` (local Streamlit) + `docs/ui-live-en.png` (live HF)
- P2.B + P0 deploy closed автономно 2026-05-17

## P1 — оставшийся портфолио-материал

1. ~~Screenshots EN+RU local Streamlit~~ ✓ закрыто 2026-05-17.
2. **Короткий live-URL ролик** (`D:\AutoReel\` шаблон ИЛИ Playwright video record):
   - shot A: hero (headline 77.5% + metric block)
   - shot B: sample-click → SQL + answer render
   - shot C: EN→RU toggle
   - **Источник: live URL** (`https://liovina-nl-sql.hf.space`), не localhost — memory `feedback_real_product_over_mockup`.

## P2 — quality push past 77.5% ($0 budget)

Остаток **45 фейлов** (после fewshot5-residue v7): 22 row_count_off + 14 filter_or_value + 6 order_by_off + 3 errors. Все «потолочные» — codestral + Sonnet согласуются на неверном результате.

| Эксперимент | Статус | Ожидание |
|---|---|---|
| Selective `fewshot_top_k=5` on residue | **✓ done v7** (+0.5pp, qid=1500 simple) | — |
| Mistral-large voting on residue | **✗ negative** (free tier 429 rate-limit, 7/7 attempted = same; structural failures unanimous across Mistral models) | — |
| GraceKelly: GPT-5.4 via Perplexity bridge | **OPEN** (P2.A) | +1-3pp ортогональный к Sonnet, $0 wall, ~50 мин. **Гейт:** Chrome profile свободен (memory `feedback_user_chrome_assumption`). |
| Question rephrasing through Sonnet → re-feed | **OPEN** (P2.C) | +0-3pp BIRD-style формализация. **Гейт:** GraceKelly bridge live. |
| row_count_off через explicit JOIN-path hint (custom schema-linker) | **research-grade** (P2.D) | +5-10pp ceiling lift, дни-недели работы. |

**Не повторять:**
- Anthropic API direct — out of $0 budget.
- Wide-schema retry — saturated (0 rescues в 2026-05-13).
- Column-count critique — empirically бесполезен (0/19 mismatch).
- Same-model self-consistency — plateau.
- Mistral-large voting — 2026-05-17 EOS зафиксирован negative (rate-limit + structural agreement с codestral).

## Что НЕ делать

- Не редизайнить UI. Зафиксирован 2026-05-13.
- Не коммитить `chroma_data/` byte-level drift от смок-запусков.
- Не запускать GraceKelly `dry-run → hybrid` без подтверждения, что Chrome-профиль свободен (memory `feedback_user_chrome_assumption`).
- Не пробовать Mistral-large снова на residue без throttling — free tier даёт ≤2 req/sec, скрипту нужен `--sleep-between` arg.

## Quick start если хочется быстрого win

```bash
# Repush HF Space после правок (idempotent, ~90s до RUNNING):
uv run python .deploy_hf.py

# Gate:
uv run pytest -q && uv run ruff check src tests scripts app && uv run mypy --strict src

# Local Streamlit (cache-warm UI):
make ui
```

## Deploy quick reference

- Live URL: <https://liovina-nl-sql.hf.space>
- Dashboard: <https://huggingface.co/spaces/liovina/nl-sql>
- Deploy script: `.deploy_hf.py` (gitignored)
- HF Dockerfile template: `.tmp/hf_Dockerfile` (важно: `ENV PYTHONPATH=/app/src` для src layout)
- Mistral key: `D:/TXT/Mistral_API.txt`
- Полный runbook: `docs/SESSION_HANDOFF.md § Deploy — DONE`
