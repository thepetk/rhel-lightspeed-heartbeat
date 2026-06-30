.PHONY: install lint format format-fix type-check test test-cov run check clean help

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Check formatting with ruff
	uv run ruff format --check src/ tests/

format-fix: ## Auto-fix formatting
	uv run ruff format src/ tests/

type-check: ## Run ty type checker
	uv run ty check src/

test: ## Run tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=heartbeat --cov-report=term-missing

run: ## Run heartbeat locally (requires HEARTBEAT_SERVICES_JSON env var)
	uv run python -m heartbeat

check: lint format type-check test-cov ## Run all checks (lint, format, types, tests)

clean: ## Remove build artifacts and caches
	rm -rf .ruff_cache .pytest_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
