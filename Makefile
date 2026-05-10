.PHONY: test lint format typecheck doctor check coverage mdlint

test:
	uv run pytest tests/unit/ tests/integration/ -v --tb=short

coverage:
	uv run pytest tests/unit/ tests/integration/ --cov=src/mast --cov-report=term-missing --cov-report=html:.coverage_html -v --tb=short

lint:
	uv run ruff check src/ tests/ evals/

mdlint:
	uv run pymarkdownlnt -d MD013,MD024,MD041,MD033 scan *.md docs/*.md

format:
	uv run ruff format --check src/ tests/ evals/

typecheck:
	uv run mypy src/ tests/

doctor:
	uv run python -m mast --doctor

check: lint format typecheck test
