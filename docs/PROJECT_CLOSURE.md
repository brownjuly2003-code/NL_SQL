# Project closure

Дата фиксации scope: 2026-07-27.
Обновление delivery disposition: 2026-07-30.

## Закрываемый scope

Финальный scope — Stages 1–10 из публичного README:

- RU/EN NL→SQL pipeline и четыре формата ответа;
- SQLite product path и проверенный PostgreSQL read-only path;
- AST guard, statement timeout, row cap, API auth/rate limit;
- reproducible BIRD baseline 61.5%, Chinook workload 60/60 и честно отделённые
  eval-only результаты;
- Streamlit UI, FastAPI surface, CI, docs;
- **clone-first** local smoke (9 shipped SQLite DB + prebuilt Chroma);
- **full-source local delivery** (все 12 SQLite DB + полный Chroma index) через
  `scripts/run_local_demo.py` и runbook [`LOCAL_DEMO.md`](../LOCAL_DEMO.md) со
  **своими** ключами владельца — **принятый текущий demo/delivery path**.

После финальной публикации этот scope feature-frozen. Улучшение benchmark score,
новые модели и исследовательские методы требуют нового отдельно
санкционированного проекта.

## Delivery disposition (owner decision, 2026-07-30)

Решение владельца **финально**:

- Hugging Face **не** является предлагаемым путём доставки;
- сервис запускается **локально** с ключами провайдера владельца;
- с точки зрения владельца продуктовый workflow и UI **не меняются**.

Реализованный HF tooling (`scripts/deploy_hf.py`, `DEPLOY.md`, Docker Space
publish path, hardening commits `712f986` / `8c2baf7`) **сохраняется** как
опциональная/историческая capability. Код не удаляется и не «переписывается
как будто его не было». Resume/restore/retire внешнего Space — только по
**явному** слову владельца; это не открытый local-first gap.

## Backlog disposition

- `docs/BACKLOG.md` остаётся living record, но секции прежнего research pass и
  `Next levers` теперь являются историей и `future`, а не активной очередью.
- CHESS/DAIL/CHASE/E-SQL, synthetic few-shot, query-plan CoT, новые generator
  keys и дальнейшие BIRD score campaigns закрыты как исследовательский scope.
- Sustained-load host и внешний pen-test переведены в `future operations`; они
  не являются незавершённым local-first product claim.
- Provider-neutral local embeddings — отдельный будущий архитектурный проект,
  не residual закрываемой версии.
- HF restore/retire остаётся **owner-authorized optional/historical** work, не
  обязательным gate для local-first delivery.

Ни один research-пункт не объявляется реализованным: он выведен из текущего
scope явно.

## Обязательные внешние closure gates

- closing commits опубликованы в `main`, CI зелёный на точном SHA;
- принято финальное решение о версии/tag/release для текущего `0.1.0`;
- **опционально / исторически (только по слову владельца):** Hugging Face Space
  `liovina/nl-sql` (с 2026-07-22 известен как `PAUSED` / `Flagged as abusive`,
  `Cloudflared`) либо восстановлен и проверен на closing SHA, либо публично
  снят с эксплуатации. Это **не** блокирует local-first delivery;
- публичные README / `LOCAL_DEMO.md` описывают local full-source как рекомендуемый
  path; claims про внешний host не опережают факт.

Push, release и любые deploy/Space mutations требуют явного разрешения владельца.

## Разбор локального WIP (2026-07-29)

- Финальные отчёты student base/tuned и оба Arcwise-рескора сохраняются в Git
  как публичные доказательства.
- Partial/retry/smoke-отчёты и локальные заметки в корне
  (`NL-SQL Explainer.html`, `bird_issues*.txt`) остаются на диске под точными
  правилами `.gitignore`.
- Runtime-churn Chroma и сгенерированный индекс за 2026-07-16 признаны
  избыточными после сравнения коллекций, размеров и top-5 retrieval; SQLite
  отличался только таблицей `acquire_write`. Исходные байты сохранены локально,
  рабочие файлы возвращены к `HEAD`.
- Это не меняет замороженный продуктовый scope и не разрешает push/deploy.

## Local-first docs alignment (2026-07-30)

- Launcher full-source demo: `34791cf` (`feat(local): add full-source demo launcher`).
- Scoped content commit: `3a3114f` (`docs(local): make full-source demo the delivery path`)
  — `README.md`, `LOCAL_DEMO.md`, contract tests, and public closure/backlog
  alignment under owner decision no-HF delivery.
- **Full quality gate verified** (independent Codex run, 2026-07-30, all exit 0):
  focused contract tests 11 passed; Ruff/format clean on launcher + docs tests;
  `scripts/run_local_demo.py --check` preflight OK (12 SQLite DBs + Chroma,
  `MISTRAL_API_KEY` present, value not printed); full Ruff/format/mypy clean
  (110 source files); full pytest 606 passed, 14 skipped, coverage 91.06%
  (required 85%); `check_repo_hygiene.py` and `check_no_raw_compare.py` OK;
  `git diff --check` exit 0. Windows pytest `atexit` `PermissionError` on
  `pytest-current` cleanup is known non-failing noise (process exit remained 0).
- **Local audit-closure scope is complete** with content commit `3a3114f`.
- Push / deploy / release remain **external owner gates** and were **not** performed.
