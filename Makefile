.PHONY: install lint format type test all serve clean

install:
	uv sync --extra dev

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

type:
	uv run mypy src

test:
	uv run pytest

all: lint format type test

serve:
	uv run uvicorn nl_sql.api.main:app --reload --port 8000

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
