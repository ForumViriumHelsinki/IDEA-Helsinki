# Justfile for IDEA-Helsinki
# Run `just` or `just help` to see available recipes
# https://just.systems/

set dotenv-load
set positional-arguments

####################
# Metadata
####################

# Default recipe - show help
default:
    @just help

# Show available recipes with descriptions
help:
    @just --list --unsorted

####################
# Development
####################

# Install dependencies for all services
install:
    @echo "Installing dependencies..."
    uv sync --all-packages --all-extras
    @echo "Dependencies installed!"

# Build project (Docker images via Skaffold)
build:
    @echo "Building project..."
    skaffold build

# Start services with Skaffold
start:
    @echo "Starting services with Skaffold..."
    skaffold dev

# Stop services (runs skaffold delete)
stop:
    @echo "Stopping services..."
    skaffold delete

# Clean test artifacts and cache files
clean:
    @echo "Cleaning test artifacts..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name ".coverage" -delete 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    @echo "Cleaned!"

####################
# Code Quality
####################

# Run linting checks (ruff check)
lint *args:
    @echo "Running linting checks..."
    uv run ruff check {{ args }}
    @echo "Linting passed!"

# Format code with ruff
format *args:
    @echo "Formatting code..."
    uv run ruff format {{ args }}
    @echo "Code formatted!"

# Check code formatting without modifying
format-check *args:
    @echo "Checking code formatting..."
    uv run ruff format --check {{ args }}
    @echo "Formatting check passed!"

# Run type checking with ty
typecheck *args:
    @echo "Running type checks..."
    uv run ty check {{ args }}
    @echo "Type checks passed!"

# Composite: format-check + lint + typecheck (code quality only, no tests)
check: format-check lint typecheck
    @echo "Quality checks passed!"

####################
# Testing
####################

# Run tests for all services (sequential)
test *args:
    @echo "Running all tests..."
    @just test-shared {{ args }}
    @just test-orchestrator {{ args }}
    @just test-fcd-manager {{ args }}
    @just test-traffic-monitor {{ args }}
    @echo "All tests passed!"

# Run tests for shared library
test-shared *args:
    @echo "Testing shared library..."
    uv run --package idea-shared --directory shared python -m pytest tests -v {{ args }}

# Run tests for orchestrator service
test-orchestrator *args:
    @echo "Testing orchestrator service..."
    uv run --package orchestrator --directory services/orchestrator python -m pytest tests -v {{ args }}

# Run tests for fcd-manager service
test-fcd-manager *args:
    @echo "Testing fcd-manager service..."
    uv run --package fcd-manager --directory services/fcd-manager python -m pytest tests -v {{ args }}

# Run tests for traffic-monitor service
test-traffic-monitor *args:
    @echo "Testing traffic-monitor service..."
    uv run --package traffic-monitor --directory services/traffic-monitor python -m pytest tests -v {{ args }}

# Run only unit tests (fast, no external dependencies)
test-unit *args:
    @echo "Running unit tests only..."
    uv run --package idea-shared --directory shared python -m pytest tests -m unit -v {{ args }}
    uv run --package orchestrator --directory services/orchestrator python -m pytest tests -m unit -v {{ args }}
    uv run --package fcd-manager --directory services/fcd-manager python -m pytest tests -m unit -v {{ args }}
    uv run --package traffic-monitor --directory services/traffic-monitor python -m pytest tests -m unit -v {{ args }}
    @echo "All unit tests passed!"

# Run only integration tests
test-integration *args:
    @echo "Running integration tests only..."
    uv run --package idea-shared --directory shared python -m pytest tests -m integration -v {{ args }}
    uv run --package orchestrator --directory services/orchestrator python -m pytest tests -m integration -v {{ args }}
    uv run --package fcd-manager --directory services/fcd-manager python -m pytest tests -m integration -v {{ args }}
    uv run --package traffic-monitor --directory services/traffic-monitor python -m pytest tests -m integration -v {{ args }}
    @echo "All integration tests passed!"

# Run all tests with coverage report
test-coverage *args:
    @echo "Running tests with coverage..."
    uv run --package idea-shared --directory shared python -m pytest tests --cov --cov-report=html --cov-report=term-missing {{ args }}
    uv run --package orchestrator --directory services/orchestrator python -m pytest tests --cov --cov-report=html --cov-report=term-missing {{ args }}
    uv run --package fcd-manager --directory services/fcd-manager python -m pytest tests --cov --cov-report=html --cov-report=term-missing {{ args }}
    uv run --package traffic-monitor --directory services/traffic-monitor python -m pytest tests --cov --cov-report=html --cov-report=term-missing {{ args }}
    @echo "Coverage reports generated!"

# Run all tests in parallel (fast)
test-parallel *args:
    @echo "Running tests in parallel..."
    uv run --package idea-shared --directory shared python -m pytest tests -n auto -v {{ args }}
    uv run --package orchestrator --directory services/orchestrator python -m pytest tests -n auto -v {{ args }}
    uv run --package fcd-manager --directory services/fcd-manager python -m pytest tests -n auto -v {{ args }}
    uv run --package traffic-monitor --directory services/traffic-monitor python -m pytest tests -n auto -v {{ args }}
    @echo "All parallel tests passed!"

# Run multithreading equivalence tests for fcd-manager
test-equivalence *args:
    @echo "Testing multithreading equivalence..."
    uv run --package fcd-manager --directory services/fcd-manager python -m pytest tests/test_multithreading_equivalence.py -v {{ args }}
    @echo "Equivalence tests passed!"

####################
# Documentation
####################

# Build documentation site
docs-build:
    @echo "Building documentation..."
    uv run --group docs mkdocs build
    @echo "Documentation built in site/"

# Serve documentation locally with live reload
docs-serve:
    uv run --group docs mkdocs serve

# Check documentation builds without errors (strict mode)
docs-check:
    @echo "Checking documentation..."
    uv run --group docs mkdocs build --strict
    @echo "Documentation check passed!"

####################
# Workflows
####################

# Run all pre-commit checks (non-mutating: format-check, lint, test-unit)
pre-commit: format-check lint test-unit
    @echo "Pre-commit checks passed!"

# Simulate CI pipeline (format-check + lint + test with coverage)
ci: format-check lint test-coverage
    @echo "CI simulation passed!"
