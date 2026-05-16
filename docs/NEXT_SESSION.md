# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> удаляешь этот файл (или переписываешь под следующий sprint).

## Контекст на 2026-05-17

- HEAD `298614f` (после 3ca3612 + docs:refresh + HF deploy session)
- BIRD Mini-Dev n=200: **77.0% EA** (154/200), per tier 88.1/74.7/61.8
- 270 pytest pass (+20 за scalar label classifier + 3 drift guards), ruff + mypy strict clean
- Streamlit UI переписан в editorial monochrome + EN/RU; scalar metric labels гуманизированы
- Portfolio screenshots EN/RU в `docs/ui-2026-05-17-{en,ru}.png` привязаны в README hero
- **Live demo на HF Spaces:** <https://liovina-nl-sql.hf.space> (deploy headless через `.deploy_hf.py`, see § P0)
- 2026-05-12 audit P1 backlog закрыт (build_index sample-size drift, CI lint scope, pinned requirements, BM25 cleanup в methodology)
- GraceKelly Sonnet bridge доказан рабочим (9 rescues / 0 regressions)

## ~~P0 — Streamlit Cloud deploy~~ **CLOSED 2026-05-17**

Live: <https://liovina-nl-sql.hf.space> (HF Spaces, Docker runtime, free
tier). Headless deploy через `huggingface_hub.HfApi`: `.deploy_hf.py`
создаёт Space `liovina/nl-sql` с `space_sdk=docker`, прокидывает
`MISTRAL_API_KEY` через `add_space_secret`, заливает 214 MB кода + данных
с auto-LFS, генерирует HF README frontmatter (`sdk: docker, app_port:
7860`) + Dockerfile (`python:3.12-slim`, `pip -r requirements.txt`,
`streamlit run app/streamlit_app.py --server.port 7860`).

Streamlit Cloud не пошёл (требует Gmail OAuth, у Юлии не открывается),
Fly.io/Railway/Render не пошли (sign-up через email OAuth). HF — у
Юлии уже залогинен (`liovina`, token в `~/.cache/huggingface/token`),
поэтому весь deploy ушёл headless без единого клика.

Repush после правок: повторить `uv run python .deploy_hf.py` — `exist_ok`
+ idempotent upload_folder корректно перезаписывают Space.

## P1 — портфолио-материалы под новый UI

Хороший shot нового UI = sellable артефакт. Конкретно:

1. ~~**Один screenshot EN + один RU** под hero-section какого-нибудь
   проектного проф-сайта или LinkedIn. 1440×900 viewport, default DB
   `bird_california_schools`, без открытых expanders. Сохранить под
   `docs/ui-2026-05-13-{en,ru}.png` и привязать в README.~~ **Закрыто
   2026-05-17:** `docs/ui-2026-05-17-{en,ru}.png` сняты через Playwright
   headless Streamlit, привязаны в README hero-секции.
2. **Короткий AutoReel-ролик** (`D:\AutoReel\`) с тремя shots:
   (a) headline + metric block,
   (b) sample-click → answer render,
   (c) language toggle EN→RU.
   Memory `feedback_real_product_over_mockup` говорит: реальная запись
   экрана > HTML-template для проектов с live demo. Если P0 закрыт и
   live URL есть — записывай live URL, не localhost.

## P2 — quality push past 77% (если есть желание)

Остаток 46 фейлов: 22 row_count_off + 14 filter_or_value + 6 order_by_off
+ 4 errors. Все «потолочные» — codestral + Sonnet согласуются на
неверном результате. Реальные рычаги:

| Эксперимент | Ожидание | Стоимость |
|---|---|---|
| **GraceKelly: GPT-5.4 на остатке через Perplexity bridge** | +1-3pp; ортогональный к Sonnet, может закрыть другие фейлы | $0 wall, ~50 мин |
| **BIRD train fewshot expansion** (top_k=5 на failures with `enable_grounded_critique`) | +0-2pp; раньше top_k=5 давал -1pp при глобальном применении, но selective может сыграть | $0 wall, 5 мин |
| **Question rephrasing through Sonnet → re-feed pipeline** | +0-3pp; BIRD-style формализация вопроса, потом codestral пытается ещё раз | $0 wall, ~50 мин |
| **Hard fail: row_count_off через explicit JOIN-path hint** | +5-10pp ceiling lift, но требует custom schema-linker (research-grade work, не sprint) | дни-недели |

**Не пытаться повторять:**
- Anthropic API direct — out of $0 budget.
- Wide-schema retry — уже подтверждено saturated.
- Column-count critique — empirically бесполезен (0/19 mismatch).
- Same-model self-consistency — plateau.

## Закрытые тейлы для следующей сессии

- `audit_codex_12_05_26.md` ещё не закрыт по P1 пунктам:
  - sample-size `build_index.py` vs runtime mismatch (открыт)
  - CI lint app/scripts (открыт)
  - wide dependency ranges в `requirements.txt` (открыт)
  Все три — P1 medium, не блокеры; брать вместе с P0 deploy если будет
  CI-time.

## Что НЕ делать

- Не редизайнить UI повторно. Текущий редизайн принят и зафиксирован.
- Не коммитить `chroma_data/` byte-level изменения от смок-запусков
  (они в working tree после каждого Streamlit-run, оставляй
  uncommitted — реальные перестроения индекса делаются через
  `scripts/build_index.py` и тогда commit'ятся осознанно).
- Не запускать GraceKelly `dry-run -> hybrid` без подтверждения, что
  Chrome-профиль свободен (memory `feedback_user_chrome_assumption`).
