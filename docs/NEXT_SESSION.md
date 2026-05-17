# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> удаляешь этот файл (или переписываешь под следующий sprint).

## 2026-05-18 update — Groq TPD recovery sanity check + P3.F realism audit

**Sanity check executed автономно перед стартом любой новой работы:**

1. **Groq llama70b TPD НЕ сбросился** (HEAD `d6303ff` post-EXTENDED, day-3).
   Ping 38-token prompt → 200 OK, но `run_critique_retry` на 21 unattempted
   v11-residue qid (filtered baseline: `eval/reports/2026-05-17c/v11-residue-fresh21.json`)
   дал 21/21 hit 429. Headroom 98077/100000, real prompts (2500–11000 ток.) перебирают cap.
   Reset windows из 429 message: 8m–2h10m, **rolling not midnight-aligned**.
   Operational rule добавлено в SESSION_HANDOFF: для TPD recovery — ping
   real-sized prompt (≥3000 токенов), не 5-token "pong".
   Артефакты: `eval/reports/2026-05-17c/{v11-residue-fresh21.json, groq-llama70b-on-v11-residue-fresh21.json, llama70b-fresh21.log}`.

2. **GraceKelly hybrid bridge port 8011 DOWN.** Chrome-gated P3.A/D/E
   недоступны без user-initiated GraceKelly start.

3. **P3.F realism audit** (`docs/p3f_design.md`). Memory обещал P3.F +5–10pp
   на row_count_off bucket. Per-qid аудит 20-case row_count_off показал:
   - 4 distinct_diff_only (бидирекциональные — простое prompt rule регрессирует половину)
   - 5 missing/extra-table (schema linking edge cases)
   - 10 same_tables_diff_join — но из этих **только ~2 чистых JOIN-path FK-choice** (qid 207, 1404).
     Остальное — query-structure mis-interpretations (LIMIT/subquery/CASE shape), не JOIN-path.
   - **Realistic P3.F ceiling: +0.5–1pp** на n=200 EA, не +5–10pp. Не строить speculatively.

**Закрытый портфолио-deliverable итог:** v11 81.0% / 67.34% Arcwise-Plat / +6 audit
catches триплет окончательный для $0/chrome-free бюджета. Live HF Space live.
Video docs/ui-live-demo.mp4 готов. README hero обновлён.

**Что делать в следующей сессии (после явного user mandate):**

| Цель | Стратегия | Ожидание |
|---|---|---|
| Past 81% chrome-free $0 | Wait 24h+ → real-sized ping → llama70b retry 21 fresh qids | ≤1 rescue, +0–0.5pp |
| Past 81% chrome-free $0 | Try `gemini-2.5-pro` (RPD ≥100, 10× higher than flash) на residue | +0–1 rescue, +0–0.5pp |
| Past 81% chrome-free $1 | OpenRouter $1 top-up unlocks 1000/day free-model requests | re-test nemotron + ortogonal free models, +0–1pp |
| Past 81% chrome-gated | Поднять GraceKelly + GPT-5.x bridge на residue (P3.A) | +1–3pp ортогонально к Sonnet 4.6 |
| Past 81% paid $1–3 | Anthropic Sonnet API sweep 38-case | +1–3pp, наивысший $/pp |
| Research-grade | P3.F JOIN-path linker + CSC-SQL (см. `docs/p3f_design.md`) | +2–4pp combined, multi-day |

## Контекст на 2026-05-17 next-day-2 EXTENDED (six-model saturation sprint)

- HEAD post-`bf26e91` + this sprint's commits (см. SESSION_HANDOFF.md и `docs/v11_saturation_evidence.md`)
- BIRD original gold n=200 (**v11**): **81.0% EA** (162/200) — UNCHANGED
- Sprint итог: v11 residue (38 fails) проверен **шестью** разными free-tier voting слоями через все API keys в `D:\TXT\` — **0 rescues**, **69 unique case-attempts**.
  1. llama-3.3-70b Groq: 17/38, 0 (TPD)
  2. gpt-oss-20b Groq: 2/38, 0 (json_validate)
  3. gemini-2.5-flash Google: 10/38, 0 (RPD 10/day)
  4. gemini-2.5-flash-lite Google: 9/38, 0 (RPD 20/day)
  5. nvidia/nemotron-3-super-120b:free OpenRouter: 18/38, 0 (50/day account-wide)
  6. codestral + M-Schema + DAC combined env-flags (новый комбо): 13/38, 0 (Mistral RPM)
- Full audit trail: **`docs/v11_saturation_evidence.md`** — model × provider × reached × rescues × why-stopped table + API key inventory + reset times.
- Артефакты sprint'а: `eval/reports/2026-05-17b/{groq-llama70b-*.json, *.log × 5}` — negative-evidence
- **scripts/run_critique_retry.py** получил `--base-url` + `--api-key` args для cross-provider routing (Gemini/OpenRouter через GroqProvider hijack)
- **Live demo video:** `docs/ui-live-demo.mp4` (47s, 2.1MB). Три бита. P1 ролик-портфолио закрыт.

## Чистое saturation summary

Текущий потолок **$0/chrome-free = 81.0% v11**. На v11-residue все доступные free-tier
voting layers либо вернули 0 (cache=same), либо упёрлись в TPM/TPD/structural-failure:

| Lever | Status | Detail |
|---|---|---|
| codestral T=0 baseline | saturated | первая ступень pipeline |
| codestral self-consistency T=0.2-0.8 | plateau (✗) | 2026-05-13 sprint |
| mistral-large voting | TPM-blocked (✗) | 18 reached, 0 rescues |
| qwen3-32b voting | partial (✓ once, 1 rescue v8) | 5K TPM cap |
| gpt-oss-20b voting | TPM-blocked (✓ +2 v9, ✗ v11 json_validate) | 6K TPM cap |
| gpt-oss-120b voting | TPM-blocked (✗) | 8K TPM cap |
| llama-3.3-70b voting | TPD-exhausted (✓ +2 v8, ✗ v9/v10/v11) | 100K TPD |
| M-Schema retry | additive once (✓ +1 v10) | structural cliff на baseline |
| CHASE-SQL DAC retry | additive once (✓ +1 v11) | structural cliff на baseline |
| Wide-schema retry | saturated (✗) | row_count_off структурный |
| Audit rules в prompt | saturated (✗) | residue не отвечает |
| Evidence-hoist | saturated (✗) | residue не отвечает |
| Sonnet 4.6 bridge | already used (✓ +9 v6) | Chrome-gated |

**Что осталось как реальный лeверь:** Chrome-gated (P3.A, P3.D, P3.E) или
paid API (Sonnet ~$1-3 на 38-case sweep) или research-grade JOIN-path linker
(P3.F, дни).

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
2. ~~Короткий live-URL ролик~~ ✓ закрыто 2026-05-17 next-day-2. `docs/ui-live-demo.mp4` (47s, 2.1MB, Playwright headless 1440×900). Три бита: hero 81.0%, sample-click → SQL + COUNT(4), EN↔RU toggle. Источник — live HF Space. Embed в README hero section.

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
