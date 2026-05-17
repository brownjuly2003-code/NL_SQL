# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> удаляешь этот файл (или переписываешь под следующий sprint).

## Контекст на 2026-05-17 late-night

- HEAD `fcd7ec3` + v9 sprint (см. SESSION_HANDOFF.md)
- BIRD Mini-Dev n=200: **80.0% EA** (160/200), per tier 91.0/76.8/67.6 (v9 = v8 + gpt-oss-20b voting +2 rescues qids 571 moderate + 1232 challenging)
- **Live demo:** <https://liovina-nl-sql.hf.space> RUNNING, headline 80.0% / 200
- 270 pytest pass, ruff + mypy strict clean (55 source files)
- Streamlit UI editorial monochrome + EN/RU (закрыто 2026-05-13)
- Portfolio screenshots: `docs/ui-2026-05-17-{en,ru}.png` (local Streamlit) + `docs/ui-live-en.png` (live HF)
- P2.B + P0 deploy closed автономно 2026-05-17

## P1 — оставшийся портфолио-материал

1. ~~Screenshots EN+RU local Streamlit~~ ✓ закрыто 2026-05-17.
2. **Короткий live-URL ролик** (`D:\AutoReel\` шаблон ИЛИ Playwright video record):
   - shot A: hero (headline 80.0% + metric block)
   - shot B: sample-click → SQL + answer render
   - shot C: EN→RU toggle
   - **Источник: live URL** (`https://liovina-nl-sql.hf.space`), не localhost — memory `feedback_real_product_over_mockup`.

## P2/P3 — quality push past 80.0% ($0 budget)

Остаток **40 фейлов** (после v9). gpt-oss-20b voting (free tier, lightweight) использован на 13/20 ранее-unattempted residue — +2 rescues, TPM 8K режет на 7/20 с long prompts. Residue после v9 ещё содержит ~28 unattempted llama-3.3-70b (TPD cooldown) + 7 gpt-oss-20b TPM-blocked.

| Эксперимент | Статус | Ожидание |
|---|---|---|
| Selective `fewshot_top_k=5` on residue | **✓ done v7** (+0.5pp, qid=1500 simple) | — |
| Cross-Groq voting (llama3.3-70b + qwen3) | **✓ done v8** (+1.5pp, qids 219+352+366) | — |
| Mistral-large voting on residue | **✗ negative** (TPD/TPM limits — 18 attempted, all same; structural failures unanimous across Mistral models) | — |
| Wide-schema retry on row_count_off | **✗ negative** (0/20 rescues с critique tоо) | — |
| codestral fewshot_top_k=7 | **✗ negative** (0/45, top_k=5 насыщает) | — |
| gpt-oss-120b throttled voting | **✗ TPM limits** (0/24 rescues, prompts 8.5K > 8K TPM gives 413; первая попытка с fewshot=5 ранее дала +1 rescue qid=571, но воспроизвести не вышло — fewshot=3 теряет critical context для cases) | — |
| GraceKelly: GPT-5.4 via Perplexity bridge | **OPEN** (P3.D) | +1-3pp ортогональный к Sonnet. **Гейт:** Chrome profile свободен. |
| Question rephrasing through Sonnet → re-feed | **OPEN** (P3.E) | +0-3pp. **Гейт:** GraceKelly bridge live. |
| row_count_off через explicit JOIN-path hint (custom schema-linker) | **research-grade** (P3.F) | +5-10pp ceiling lift, дни-недели работы. |
| llama-3.3-70b TPD reset retry | **OPEN** | TPD resets ~24h. На v8-residue ещё 30 unattempted; ожидаемо +0-2pp. |

**Не повторять:**
- Anthropic API direct — out of $0 budget.
- Wide-schema retry — saturated (повторно подтверждено в 2026-05-17 night).
- Column-count critique — empirically бесполезен (0/19 mismatch).
- Same-model self-consistency — plateau.
- Mistral-large voting — 2026-05-17 EOS+night зафиксирован negative.
- codestral fewshot_top_k=7 — 0/45 на v7-residue, top_k=5 саtuрated.
- gpt-oss-120b voting — TPM 8K жёстко режет, prompts с critique=10K+; нужны без-critique runs (но они теряют lift signal).

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
