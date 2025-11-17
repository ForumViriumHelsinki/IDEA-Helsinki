.PHONY: help test test-all test-shared test-orchestrator test-fcd-manager test-traffic-monitor
.PHONY: test-cov test-parallel clean lint install-deps
.DEFAULT_GOAL := help

# Color output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)IDEA-Helsinki Test Makefile$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# Individual service tests
test-shared: ## Run tests for shared library
	@echo "$(BLUE)Testing shared library...$(NC)"
	cd shared && uv sync --all-extras --quiet && .venv/bin/python -m pytest -v

test-orchestrator: ## Run tests for orchestrator service
	@echo "$(BLUE)Testing orchestrator service...$(NC)"
	cd services/orchestrator && uv sync --all-extras --quiet && .venv/bin/python -m pytest -v

test-fcd-manager: ## Run tests for fcd-manager service
	@echo "$(BLUE)Testing fcd-manager service...$(NC)"
	cd services/fcd-manager && uv sync --all-extras --quiet && .venv/bin/python -m pytest -v

test-traffic-monitor: ## Run tests for traffic-monitor service
	@echo "$(BLUE)Testing traffic-monitor service...$(NC)"
	cd services/traffic-monitor && uv sync --all-extras --quiet && .venv/bin/python -m pytest -v

test-equivalence: ## Run multithreading equivalence tests for fcd-manager
	@echo "$(BLUE)Testing multithreading equivalence...$(NC)"
	cd services/fcd-manager && uv sync --all-extras --quiet && .venv/bin/python -m pytest tests/test_multithreading_equivalence.py -v
	@echo "$(GREEN)✓ Equivalence tests passed!$(NC)"

# Run all tests
test: ## Run tests for all services (sequential)
	@echo "$(GREEN)Running all tests...$(NC)"
	@$(MAKE) test-shared
	@$(MAKE) test-orchestrator
	@$(MAKE) test-fcd-manager
	@$(MAKE) test-traffic-monitor
	@echo "$(GREEN)✓ All tests passed!$(NC)"

test-all: test ## Alias for 'test' target

# Test with coverage
test-cov: ## Run all tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	cd shared && uv sync --all-extras --quiet && .venv/bin/python -m pytest --cov --cov-report=html --cov-report=term-missing
	cd services/orchestrator && uv sync --all-extras --quiet && .venv/bin/python -m pytest --cov --cov-report=html --cov-report=term-missing
	cd services/fcd-manager && uv sync --all-extras --quiet && .venv/bin/python -m pytest --cov --cov-report=html --cov-report=term-missing
	cd services/traffic-monitor && uv sync --all-extras --quiet && .venv/bin/python -m pytest --cov --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)✓ Coverage reports generated in each service's htmlcov/ directory$(NC)"

# Parallel testing
test-parallel: ## Run all tests in parallel (fast)
	@echo "$(BLUE)Running tests in parallel...$(NC)"
	cd shared && uv sync --all-extras --quiet && .venv/bin/python -m pytest -n auto -v
	cd services/orchestrator && uv sync --all-extras --quiet && .venv/bin/python -m pytest -n auto -v
	cd services/fcd-manager && uv sync --all-extras --quiet && .venv/bin/python -m pytest -n auto -v
	cd services/traffic-monitor && uv sync --all-extras --quiet && .venv/bin/python -m pytest -n auto -v
	@echo "$(GREEN)✓ All parallel tests passed!$(NC)"

# Unit tests only (fast)
test-unit: ## Run only unit tests (fast, no external dependencies)
	@echo "$(BLUE)Running unit tests only...$(NC)"
	cd shared && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m unit -v
	cd services/orchestrator && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m unit -v
	cd services/fcd-manager && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m unit -v
	cd services/traffic-monitor && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m unit -v
	@echo "$(GREEN)✓ All unit tests passed!$(NC)"

# Integration tests only
test-integration: ## Run only integration tests
	@echo "$(BLUE)Running integration tests only...$(NC)"
	cd shared && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m integration -v
	cd services/orchestrator && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m integration -v
	cd services/fcd-manager && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m integration -v
	cd services/traffic-monitor && uv sync --all-extras --quiet && .venv/bin/python -m pytest -m integration -v
	@echo "$(GREEN)✓ All integration tests passed!$(NC)"

# Linting and formatting
lint: ## Run linting checks (ruff check + format check)
	@echo "$(BLUE)Running linting checks...$(NC)"
	cd shared && uv run ruff check
	cd services/orchestrator && uv run ruff check
	cd services/fcd-manager && uv run ruff check
	cd services/traffic-monitor && uv run ruff check
	@echo "$(GREEN)✓ Linting passed!$(NC)"

format: ## Format code with ruff
	@echo "$(BLUE)Formatting code...$(NC)"
	cd shared && uv run ruff format
	cd services/orchestrator && uv run ruff format
	cd services/fcd-manager && uv run ruff format
	cd services/traffic-monitor && uv run ruff format
	@echo "$(GREEN)✓ Code formatted!$(NC)"

format-check: ## Check code formatting without modifying
	@echo "$(BLUE)Checking code formatting...$(NC)"
	cd shared && uv run ruff format --check
	cd services/orchestrator && uv run ruff format --check
	cd services/fcd-manager && uv run ruff format --check
	cd services/traffic-monitor && uv run ruff format --check
	@echo "$(GREEN)✓ Formatting check passed!$(NC)"

# Dependency management
install-deps: ## Install dependencies for all services
	@echo "$(BLUE)Installing dependencies...$(NC)"
	cd shared && uv pip install -e .[dev]
	cd services/orchestrator && uv pip install -e ../../shared && uv pip install -e .[dev]
	cd services/fcd-manager && uv pip install -e ../../shared && uv pip install -e .[dev]
	cd services/traffic-monitor && uv pip install -e ../../shared && uv pip install -e .[dev]
	@echo "$(GREEN)✓ Dependencies installed!$(NC)"

# Cleanup
clean: ## Clean test artifacts and cache files
	@echo "$(BLUE)Cleaning test artifacts...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned!$(NC)"

# Pre-commit checks
pre-commit: ## Run all pre-commit checks (format, lint, test-unit)
	@echo "$(BLUE)Running pre-commit checks...$(NC)"
	@$(MAKE) format
	@$(MAKE) lint
	@$(MAKE) test-unit
	@echo "$(GREEN)✓ Pre-commit checks passed!$(NC)"

# CI simulation
ci: ## Simulate CI pipeline (lint + format-check + test with coverage)
	@echo "$(BLUE)Simulating CI pipeline...$(NC)"
	@$(MAKE) format-check
	@$(MAKE) lint
	@$(MAKE) test-cov
	@echo "$(GREEN)✓ CI simulation passed!$(NC)"
