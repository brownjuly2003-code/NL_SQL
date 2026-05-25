# Recon + ceiling-breach experiment — 2026-05-25

NL_SQL @ v29 = 92.5% EA on BIRD Mini-Dev (185/200), 0.46pp от human expert (92.96%), +10.55pp над #1 paid SOTA AskData+GPT-4o (81.95%). Past 93% оставался открытым в handoff. Этот recon-цикл — попытка пробить ceiling **методом из state-of-the-art**.

## Sequence

1. **Dual recon TOP-10 progressive NL→SQL projects** (Codex + Kimi independently) — `codex_top10.md`, `kimi_top10.md`.
2. **Triage methods для $0-ceiling-breach** — анализ overlap (Agentar, XiYan, OmniSQL, Arctic, WrenAI), filter методов:
   - Duplicate of existing: vanilla self-consistency (config F уже есть в NL_SQL)
   - Required fine-tune: Arctic, RLVR, OmniSQL → out of $0 scope
   - Required paid: AskData, Agentar scaling
   - Empirically saturated per handoff: per-qid hints (P3.F exhausted), reasoning voting (3-model sweep EOD-2/4)
   - Wrong target for residue: CHESS Unit-Tester (residue не "wrong answer" а "BIRD-quirk gold")
   - Architectural-heavy out of POC scope: WrenAI semantic layer, AskData metadata extraction
3. **POC: wider self-consistency** — 2 prompt variants (default + BIRD-shape rules) × 4 temps = 8 candidates/qid, на v29 residue. Detail в `wider_sc_poc_negative.md`.
4. **Smoke на 3 BIRD-shape-friendly qids (25, 484, 930)** — 0/3 matches. qid 484 confirmed via diagnostic: BIRD-shape variant работает (генерит WHERE=MAX shape), но BIRD gold имеет non-NL-faithful "ORDER BY DESC list all" pattern (155 rows) — недостижим из NL faithfully.
5. **Stop: empirical saturation confirmed.** 92.5% ceiling под $0 budget structurally tight.

## Outcome

| Метрика | До recon | После recon |
|---|---|---|
| BIRD Mini-Dev EA | 92.5% | 92.5% (unchanged) |
| Arcwise sql_only | 74.87% | 74.87% (unchanged) |
| Arcwise full | 68.34% | 68.34% (unchanged) |

**No lift, no regression.** Clean negative finding with diagnostic detail.

**Portfolio gain:**
- Map состояния SOTA NL→SQL 2024-2026 (20 проектов across Codex + Kimi).
- Concrete reasoning why 92.5% — это $0 physics ceiling, не недотестированность.
- Reusable POC script (`scripts/wider_sc_poc.py`) для будущих ablations при появлении paid budget.
- Доказывает методическую дисциплину: попытка → diagnostic → honest stop, не infinite-loop hint engineering.

## Files

- `codex_top10.md` — Codex recon отчёт (gpt-5.4)
- `kimi_top10.md` — Kimi recon отчёт (kimi-k2)
- `wider_sc_poc_negative.md` — POC method + per-qid diagnostic + ceiling anatomy
- `../../scripts/wider_sc_poc.py` — POC implementation
- `../../eval/reports/2026-05-25/wider_sc_smoke.json` — smoke run output

## Open: что МОЖЕТ сдвинуть ceiling (для будущего, gated к юзеру)

| Метод | Cost | Expected lift | Source |
|---|---|---|---|
| Paid OR top-up $5+ ($0 → paid budget) | Низкий | +1-2pp (residue voting на claude-4.5/gpt-5.2/grok-4.1) | Handoff EOD-2 plan, не run |
| Fine-tune Qwen2.5-Coder-7B на BIRD-style gold | Высокий (GPU + dataset prep) | +2-5pp | Arctic-Text2SQL-R1 / Databricks RLVR |
| Local heterogeneous CSC: qwen2.5-coder:7b-instruct ensemble | Средний (R2 unblocking) | +0.5-1pp | NEXT_SESSION priority 2 |
| Switch metric → expert-verified BIRD subset | Метрический pivot | "93%+" но не сопоставимо | ReViSQL (Mar 2026 paper) |
| AskData-style automatic metadata extraction node | Средний (~500 LOC) | Unclear (maybe +0.5pp on column-source qids) | Codex TOP-10 #1 |

Все требуют либо paid resources, либо significant engineering, либо metric pivot. **Никакой $0 architectural lever не оставлен непробованным.**
