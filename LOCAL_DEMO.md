# Локальный запуск NL→SQL (full-source)

Рекомендуемый способ **доставки и демо** — полный исходный checkout на
локальной машине владельца, со **своими** ключами провайдера. UI, Streamlit-режим
и продуктовый pipeline те же, что в приложении; Hugging Face не нужен для
запуска.

Launcher: [`scripts/run_local_demo.py`](scripts/run_local_demo.py)

- все **12** SQLite-баз (полный registry);
- полный Chroma-индекс (`schema_chunks` + few-shot);
- штатный Streamlit UI на loopback `127.0.0.1` (порт по умолчанию `8501`);
- генератор по умолчанию: `mistral` / `codestral-latest`;
- ключ только из gitignored `.env` или из окружения процесса — **не** из CLI.

HF publish/filter/upload/prune и `scripts/deploy_hf.py` — **опциональный
исторический** tooling. Он не вызывается локальным launcher'ом и не является
активным путём доставки.

## Два уровня checkout

| Уровень | Что в дереве | Когда хватает |
|---|---|---|
| **Clone-first** | **9** небольших SQLite DB + prebuilt `chroma_data/` | быстрый smoke UI (`streamlit run app/streamlit_app.py`) |
| **Full-source local** | **все 12** SQLite DB + Chroma, покрывающий те же 12 id | `scripts/run_local_demo.py` (рекомендуемый full demo) |

Чистый git-клон **не** равен full-source: три крупные BIRD-базы не едут в GitHub
из-за лимита размера. На уже подготовленной машине (все 12 + полный индекс)
шаги download/reindex повторять не нужно.

## Требования

- Windows PowerShell 5.1 или новее (команды ниже совместимы с 5.1);
- Python 3.13;
- `uv`;
- собственный `MISTRAL_API_KEY` (embeddings всегда идут через Mistral).

```powershell
python --version
uv --version
```

## Быстрый запуск (full-source)

### 1. Корень репозитория

Выполняйте команды из **корня клона** (каталог, где лежат `app/`, `scripts/`,
`pyproject.toml`). Конкретный путь зависит от вашей машины.

```powershell
# Пример (подставьте свой путь к клону):
# Set-Location C:\path\to\NL_SQL
```

### 2. Зависимости

```powershell
uv sync --extra dev --extra ui
```

### 3. API-ключ владельца

Создайте локальный `.env`, только если его ещё нет:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
notepad .env
```

В `.env` задайте (значение не показывайте в отчётах и скриншотах):

```dotenv
MISTRAL_API_KEY=
```

Заполните ключ вручную. **Не** передавайте его параметром командной строки и
**не** вставляйте секрет в однострочные env-присваивания в документации,
скриптах, логах или скриншотах. `.env` в `.gitignore`; публиковать его нельзя.

### 4. Preflight (без сети)

```powershell
uv run python scripts/run_local_demo.py --check
```

При успехе launcher печатает строку preflight OK: full-source checkout с
**12** SQLite DB + Chroma и подтверждение, что `MISTRAL_API_KEY` настроен
(**значение ключа не печатается**). Пример формы (точная пунктуация может
совпадать с текущим launcher'ом):

```text
[local-demo] preflight OK: full source checkout (12 SQLite DBs + Chroma); MISTRAL_API_KEY configured (value not printed).
```

`--check` не ходит во внешний API и не тратит квоту.

### 5. Запуск UI

```powershell
uv run python scripts/run_local_demo.py
```

Откройте <http://127.0.0.1:8501>.

Launcher копирует Chroma во **временный** каталог (`NL_SQL_CHROMA_DATA_DIR`),
чтобы housekeeping Chroma не пачкал tracked `chroma_data/` в исходном дереве.

## Первый запуск чистого клона → full-source

Если preflight жалуется на неполный набор DB или индекс:

```powershell
uv run python scripts/download_data.py chinook
uv run python scripts/download_data.py bird-mini-dev
uv run python scripts/build_index.py --db all
uv run python scripts/run_local_demo.py --check
```

`build_index.py` вызывает Mistral embeddings и может расходовать квоту вашего
ключа. На полностью подготовленной машине эти шаги не нужны.

## Health-check работающего UI

```powershell
$response = Invoke-WebRequest `
    -UseBasicParsing `
    -Uri 'http://127.0.0.1:8501/_stcore/health' `
    -TimeoutSec 15
$response.StatusCode
$response.Content
```

Ожидается:

```text
200
ok
```

Smoke в UI (расходует квоту SQL/embed провайдера — только осознанно):

1. База `chinook`, режим `Fast`.
2. Вопрос: `How many albums are in the store?`
3. Ожидание: ответ `347`, SQL `SELECT COUNT(*) FROM Album`.

## Остановка

В терминале launcher'а: `Ctrl+C`.

## Другой порт

```powershell
uv run python scripts/run_local_demo.py --port 8502
```

Затем <http://127.0.0.1:8502>.

## SQL-генератор (продуктовое подмножество)

Документированный набор для доставки:

| `NL_SQL_DEFAULT_PROVIDER` | Ключ / условие |
|---|---|
| `mistral` (default) | `MISTRAL_API_KEY` |
| `github_models` | `GITHUB_TOKEN` |
| `groq` | `GROQ_API_KEY` |
| `ollama` | локальный Ollama + `NL_SQL_OLLAMA_GEN_MODEL` |

Пример в `.env`:

```dotenv
NL_SQL_DEFAULT_PROVIDER=mistral
```

Research/internal имена провайдеров в коде (CLI-мосты, browser bridges и т.п.)
**не** рекомендуются как путь доставки.

**Embeddings** всегда требуют `MISTRAL_API_KEY` (`mistral-embed`), в том числе
когда SQL генерирует Ollama.

## Типовые ошибки

### `MISTRAL_API_KEY is not configured`

Проверьте, что `.env` лежит в **корне репозитория** и значение ключа непустое.
Ключ не должен попадать в argv.

### `Full-source database set is incomplete`

Скачайте данные (раздел «Первый запуск чистого клона»).

### `Chroma index is missing` / incomplete index

```powershell
uv run python scripts/build_index.py --db all
```

### Порт занят

Откройте уже запущенный <http://127.0.0.1:8501> или укажите `--port`.

## Связанные файлы

- Docstring / `--help`: [`scripts/run_local_demo.py`](scripts/run_local_demo.py)
- Обзор в README: раздел **Quick start** → full-source local demo
- Опциональный HF tooling (не runtime-зависимость): [`DEPLOY.md`](DEPLOY.md)
