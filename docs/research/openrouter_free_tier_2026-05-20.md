# OpenRouter free-tier — batch-eval capacity probe (2026-05-20)

## TL;DR

Free-tier OpenRouter работает для **одиночных probe-запросов**, но **не пригоден** для NL_SQL batch eval (n=20+). Heterogeneous-CSC через `:free` модели — заблокирован upstream rate-limits, не нашим pipeline. Wiring закоммичен как инфраструктура для будущего paid OR key / BYOK.

## Контекст

Memory note 2026-05-19 закрыла free-tier headroom: P1 LIMIT-discipline −1pp, row_count_repair −0.5pp, CSC merge-revision +0 (homogeneous codestral SC saturated). Open backlog: «heterogeneous multi-model CSC (multi-day)» + «paid voting layer».

Гипотеза: подключить OpenRouter как доп. провайдер, выбрать non-Mistral `:free` модель, добавить её голос в CSC и пробить 50% threshold на котором codestral-only застрял.

## Probe — 2026-05-20

OR API key взят из `D:\TXT\Free API Keys.txt`. Кандидаты из live free pool (24 модели на дату):

| Model | Probe result | Verdict |
|---|---|---|
| `z-ai/glm-4.5-air:free` | reasoning model: 2186 reasoning_tokens съели весь бюджет, `content=""`, `finish_reason=length` | REJECT — reasoning-blocked output |
| `qwen/qwen3-coder:free` | 429 от провайдера Venice, retry_after=23-29s loop | REJECT — провайдер не отдаёт квоту free-tier |
| `deepseek/deepseek-v4-flash:free` | **Probe (n=1) → valid JSON+SQL, корректный LIMIT/OFFSET** | PROMOTED to default |

Smoke20 на `deepseek/deepseek-v4-flash:free` через `scripts/eval_baseline.py --config C --provider openrouter`:

```
EA (final):    0.0%
Validity:      95.0%
Schema rec@k:  5.0%
Wall time:     62.1s (20 examples, latency P50 = 2.1s)
```

20/20 случаев = `pipeline_exception` со словом `429`:

```
chat.completions failed for model=deepseek/deepseek-v4-flash:free:
Error code: 429 — 'deepseek/deepseek-v4-flash:free is temporarily
rate-limited upstream. Please retry shortly, or add your own key to
accumulate your rate limits.' provider_name=Crucible
```

## Root cause

OpenRouter `:free` модели проксируют запросы к нескольким upstream-провайдерам (Crucible, Venice, Cloudflare, Featherless, и т.д.) у каждого свой жёсткий free-tier rate-limit. Pipeline делает 2-3 LLM calls × 20 кейсов = ~50 запросов в первую минуту. Этого достаточно чтобы выбить ВСЕХ upstream-провайдеров одной модели; OR не ротирует автоматически.

`https://openrouter.ai/settings/integrations` подсказывает BYOK как обход: подключить свой Anthropic / OpenAI / Google ключ к OR — но это не даёт «бесплатной» гетерогенности, эти ключи и так есть напрямую (и в RAG-проекте используются).

## Что закоммичено как infrastructure

- `src/nl_sql/llm/providers/openrouter.py` — provider class, OpenAI-compatible chat_complete
- `src/nl_sql/config/settings.py` — `openrouter_model` default = `deepseek/deepseek-v4-flash:free`, `openrouter_api_key` Field
- `src/nl_sql/llm/providers/factory.py` — `case "openrouter":` branch
- `scripts/eval_baseline.py` — `--provider openrouter` choice
- `tests/test_provider_factory.py` — 2 теста (build + missing-key)

## Когда станет полезным

1. **Paid OR credit** ($5+ депозит снимает большинство upstream rate-limits на `:free`).
2. **BYOK** — если когда-то будет смысл маршрутизировать платные ключи через OR для логирования / pricing arbitrage. На NL_SQL irrelevant.
3. **Single-shot rescue calls** — например прогнать 4 hard qids (484/930/1144/1205) через одиночные probe-запросы к разным моделям, без batch. Это уже работает (probe verified).

## Что НЕ делать

- Не запускать `eval_baseline.py --provider openrouter --n 200` без paid OR — гарантированный 429-storm.
- Не добавлять retry-with-backoff в `OpenRouterProvider` для обхода — это не наша зона ответственности, и upstream-квота не зависит от частоты запросов, она дневная.
- Не подключать OR в CSC voting на текущем codestral pipeline — heterogeneity не достижима через free.

## Open

Backlog `heterogeneous multi-model CSC (multi-day)` остаётся открытым. Реалистичные пути:
1. Paid OR top-up — оценить стоимость на n=200 (≈$0.5-2 в зависимости от модели).
2. Локальный inference второй модели (ollama qwen2.5-coder или deepseek-coder) — heterogeneity без сетевого rate-limit, но wall-time × количество кандидатов.
3. Использовать уже подключённые провайдеры (groq/gh-models) с другой моделью семейства — частично гетерогенно.

Решение по пути — за пользователем.
