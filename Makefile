.PHONY: install install-ui lint format type test all serve ui clean

install:
	uv sync --extra dev

install-ui:
	uv sync --extra dev --extra ui

lint:
	uv run ruff check src tests scripts app

format:
	uv run ruff format src tests scripts app

type:
	uv run mypy src

test:
	uv run pytest

all: lint format type test

serve:
	uv run uvicorn nl_sql.api.main:app --reload --port 8000

ui:
	uv run streamlit run app/streamlit_app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
