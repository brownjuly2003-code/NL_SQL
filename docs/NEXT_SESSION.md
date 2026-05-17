# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> удаляешь этот файл (или переписываешь под следующий sprint).

## Контекст на 2026-05-17 next-day (post-DAC v11)

- HEAD `aede599` + DAC sprint (см. SESSION_HANDOFF.md, top section)
- BIRD original gold n=200 (**v11**): **81.0% EA** (162/200), per tier 92.5/76.8/70.6
- Lift trace v10 → v11: divide-and-conquer prompt env-gated NLSQL_DAC=1, +1 rescue qid 1036 challenging (european_football_2 build-up-play above-average teams, DAC adds GROUP BY for de-duplication that gold expressed via DISTINCT)
- v10 baseline (на которой проводился corrected-gold rescore): 80.5% EA, per tier 92.5/76.8/67.6
- Arcwise-Plat-SQL (corrected gold, 199/200 overlap): **67.34%** (134/199), per tier 80.6/65.3/47.1
- Arcwise-Plat full: **61.81%** (123/199), per tier 73.1/60.2/44.1
- Transitions vs BIRD original (sql-only): **+6 gained / -32 lost**
- Methodology doc: `docs/corrected_gold_evaluation.md`
- Rescore artefacts: `scripts/rescore_arcwise.py`, `eval/reports/2026-05-17/arcwise_rescored.json`
- DAC artefacts: `src/nl_sql/agent/prompts/generate_sql_dac.txt`, env gate `NLSQL_DAC=1` в `src/nl_sql/agent/nodes/generate_sql.py`, residue report `eval/reports/2026-05-17/dac-retry-on-v10-residue.json`, merged v11 report `eval/reports/2026-05-17/hybrid-vote-critique-selfcon-sonnet-fewshot5-groq4-mschema-dac-v11.json`
- **Live demo:** <https://liovina-nl-sql.hf.space> RUNNING (нет redeploy — rescore чисто на измерении, pred stack unchanged)
- 270 pytest pass, ruff + mypy strict clean (55 source files)
- M-Schema render: `render_m_schema()` в `src/nl_sql/agent/nodes/_support.py`, gated env `NLSQL_M_SCHEMA=1` (default OFF; глобально ломает baseline на ~25pp т.к. парсер теряет null/distinct/flags — использовать ТОЛЬКО на residue retry layer поверх voting stack)
- BIRD SOTA research → `docs/bird_sota_research.md` (top-10 leaderboard, free-tier ceilings, Jin et al. annotation-error finding)
- Streamlit UI editorial monochrome + EN/RU (закрыто 2026-05-13)
- Portfolio screenshots: `docs/ui-2026-05-17-{en,ru}.png` (local) + `docs/ui-live-en.png` (live HF)

## P1 — оставшийся портфолио-материал

1. ~~Screenshots EN+RU local Streamlit~~ ✓ закрыто 2026-05-17.
2. **Короткий live-URL ролик** (`D:\AutoReel\` шаблон ИЛИ Playwright video record):
   - shot A: hero (headline 80.5% + metric block)
   - shot B: sample-click → SQL + answer render
   - shot C: EN→RU toggle
   - **Источник: live URL** (`https://liovina-nl-sql.hf.space`), не localhost — memory `feedback_real_product_over_mockup`.

## P1.5 — corrected-gold портфолио narrative (just-closed)

Stress-test на Arcwise-Plat (Jin et al., CIDR/VLDB 2026) выполнен. Три числа
для портфолио (см. `docs/corrected_gold_evaluation.md`):

- 80.5% on published BIRD (leaderboard-comparable)
- 67.34% on Arcwise-Plat-SQL (honest noise-floor)
- +6 qids (672, 1029, 1144, 1247, 1251, 1254) где наш pred правильнее BIRD gold

**Что делать дальше с этой темой:**
- Можно опционально загрузить в HF Space UI «Methodology» tab или README block,
  но без чрезмерной детализации (резюме + ссылка на docs/).
- Можно сравнить наши 67.34% с published corrected-gold числами 16 систем из
  Jin et al. — но они опубликовали только график (`materials/ex.png`), не
  таблицу. Если найдём числа — добавим в `docs/corrected_gold_evaluation.md`.

## P2/P3 — quality push past 80.5% ($0 budget)

Остаток **39 фейлов** (после v10). M-Schema +1 (qid 1525 simple). Кандидаты на дальнейший lift (CHASE-SQL/XiYan technique stack из `docs/bird_sota_research.md`):

| Эксперимент | Ожидание | Cost | Risk |
|---|---|---|---|
| **Pairwise Sonnet tournament** на residue (вместо plurality vote) | +1-2pp | 3h | low |
| **Value-retrieval grounding** (BM25 по DB cell values, инжектить как evidence) | +1-2pp | 4h | medium |
| **Divide-and-conquer prompting** на residue retry (NLSQL_DAC=1) | ✓ done v11 (+0.5pp, qid 1036 challenging) | — |
| **Corrective self-consistency** (CSC-SQL: top-2 result clusters → Sonnet merge-revise) | +0.7-3pp | 4h | medium |
| Audit rules в generate_sql.txt | ✗ 0/0 на residue retry, прогон 2026-05-17 |  |  |
| Evidence-hoist (split Hint выше schema) | ✗ 0/0 на residue retry, прогон 2026-05-17 |  |  |
| FK explicit injection | ✗ FK уже в chunker.py, hypothesis отпала |  |  |
| llama-3.3-70b TPD retry | ~28 unattempted, cooldown ~hr |  |  |
| qid 990 eval bug fix | -1pp net (regression на 959, 989) → defer до большего буфера |  |  |

**Backlog:** evidence/M-Schema attempts уже null на retry — следующий null может означать что нужен full n=200 rerun (час+ codestral live).

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
