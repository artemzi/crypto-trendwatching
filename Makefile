# Makefile for crypto-trendwatching

.PHONY: lint fix format test security check run clean install help

.DEFAULT_GOAL := help

## lint: Run linters (ruff check, ruff format, mypy)
lint:
	@echo "Running linters..."
	uv run ruff check . && \
	uv run ruff format . --check && \
	uv run mypy .
	@echo "Linting complete!"

## fix: Run fix with linters (ruff check, ruff format)
fix:
	@echo "Running fix..."
	uv run ruff check . --fix && \
	uv run ruff format .
	@echo "Fixing complete!"

## format: Format code with ruff
format:
	@echo "Formatting code..."
	uv run ruff format .
	@echo "Formatting complete!"

## test: Run tests with pytest
test:
	@echo "Running tests..."
	uv run pytest
	@echo "Tests complete!"

## security: Run security checks (bandit + pip-audit)
security:
	@echo "Running security checks..."
	uv run bandit -r src/ && \
	uv run pip-audit
	@echo "Security checks complete!"

## check: Run all checks (lint + test + security)
check: lint test security
	@echo "All checks complete!"

## run: Run the FastAPI web UI
run:
	@echo "Starting web UI..."
	uv run uvicorn crypto_trendwatching.api.app:app --reload

## clean: Remove cache and build artifacts
clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete!"

## install: Install dependencies with uv
install:
	@echo "Installing dependencies..."
	uv sync
	@echo "Installation complete!"

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
