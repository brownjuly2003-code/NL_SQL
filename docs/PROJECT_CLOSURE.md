# Project closure

Дата фиксации scope: 2026-07-27.

## Закрываемый scope

Финальный scope — Stages 1–10 из публичного README:

- RU/EN NL→SQL pipeline и четыре формата ответа;
- SQLite product path и проверенный PostgreSQL read-only path;
- AST guard, statement timeout, row cap, API auth/rate limit;
- reproducible BIRD baseline 61.5%, Chinook workload 60/60 и честно отделённые
  eval-only результаты;
- Streamlit UI, FastAPI surface, CI, docs и clone-first local setup.

После финальной публикации этот scope feature-frozen. Улучшение benchmark score,
новые модели и исследовательские методы требуют нового отдельно
санкционированного проекта.

## Backlog disposition

- `docs/BACKLOG.md` остаётся living record, но секции прежнего research pass и
  `Next levers` теперь являются историей и `future`, а не активной очередью.
- CHESS/DAIL/CHASE/E-SQL, synthetic few-shot, query-plan CoT, новые generator
  keys и дальнейшие BIRD score campaigns закрыты как исследовательский scope.
- Sustained-load host и внешний pen-test переведены в `future operations`; они
  не являются незавершённым local-first product claim.
- Provider-neutral local embeddings — отдельный будущий архитектурный проект,
  не residual закрываемой версии.

Ни один research-пункт не объявляется реализованным: он выведен из текущего
scope явно.

## Обязательные внешние closure gates

- closing commits опубликованы в `main`, CI зелёный на точном SHA;
- принято финальное решение о версии/tag/release для текущего `0.1.0`;
- Hugging Face Space `liovina/nl-sql`, который с 2026-07-22 имеет состояние
  `PAUSED` / `Flagged as abusive` (`Cloudflared`), либо восстановлен и проверен
  на closing SHA, либо публично снят с эксплуатации;
- после решения по Space публичные README/DEPLOY claims совпадают с фактом.

Push, release и deploy/Space mutations требуют явного разрешения владельца.

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
