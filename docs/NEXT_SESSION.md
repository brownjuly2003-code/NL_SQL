# NL_SQL — следующая сессия

> Один лист, без воды. Берёшь, делаешь, обновляешь `SESSION_HANDOFF.md`,
> удаляешь этот файл (или переписываешь под следующий sprint).

## Контекст на 2026-05-13 EOS

- HEAD `329b251` (после aa2e245 + 1 commit этой сессии)
- BIRD Mini-Dev n=200: **77.0% EA** (154/200), per tier 88.1/74.7/61.8
- 247 pytest pass, ruff + mypy strict clean
- Streamlit UI переписан в editorial monochrome + EN/RU
- GraceKelly Sonnet bridge доказан рабочим (9 rescues / 0 regressions)

## P0 — Streamlit Cloud deploy

Это единственный реально blocking пункт для портфолио. Repo + data + deps
готовы; финальный кусок — login в Streamlit Cloud, которое требует Gmail
OAuth. У Юлии `uedomskikh@gmail.com` (см. memory `user_contacts_jobsearch`)
вместо `gemini.ge2026@gmail.com` — попробовать сначала её.

**Запасные варианты (если Streamlit Cloud режется на OAuth):**

1. **Hugging Face Spaces** — открытый альтернативный хост, поддерживает
   Streamlit, deploy через `git push` к их repo. Login через email или
   GitHub OAuth (последний у неё точно работает).
2. **Fly.io / Railway / Render** — Docker deploy из существующего
   `Dockerfile` (есть в repo). Fly.io free tier валит на 256MB RAM —
   проверь, у chroma_data 100MB index + Mistral SDK + Streamlit
   запускается в 400MB+ при первом query.
3. **VPS через её существующий хостинг.** Если у неё есть TimeWeb / любой
   другой VPS с 1GB+ — самый чистый путь.

Runbook на текущий Streamlit Cloud-вариант: `docs/SESSION_HANDOFF.md`
секция § Deploy + `.deploy_helper.py` (gitignored).

**Success criteria:** публичный URL, который открывается в инкогнито,
показывает headline `77.0% / 200`, sample-question click работает за
< 5 секунд (cache-warm), EN/RU toggle переключается мгновенно.

## P1 — портфолио-материалы под новый UI

Хороший shot нового UI = sellable артефакт. Конкретно:

1. **Один screenshot EN + один RU** под hero-section какого-нибудь
   проектного проф-сайта или LinkedIn. 1440×900 viewport, default DB
   `bird_california_schools`, без открытых expanders. Сохранить под
   `docs/ui-2026-05-13-{en,ru}.png` и привязать в README.
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
