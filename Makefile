.PHONY: install test lint fmt typecheck ci clean agent-clean

install:
	uv sync

test:
	scripts/agent-run.sh uv run pytest

test-cov:
	scripts/agent-run.sh uv run pytest --cov=gitvisual --cov-report=term-missing

lint:
	scripts/agent-run.sh uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

typecheck:
	scripts/agent-run.sh uv run mypy src/

ci: lint typecheck test

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

agent-clean:
	rm -rf .agent-output/
