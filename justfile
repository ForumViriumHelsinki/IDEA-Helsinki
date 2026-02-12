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
    cd shared && uv pip install -e .[dev]
    cd services/orchestrator && uv pip install -e ../../shared && uv pip install -e .[dev]
    cd services/fcd-manager && uv pip install -e ../../shared && uv pip install -e .[dev]
    cd services/traffic-monitor && uv pip install -e ../../shared && uv pip install -e .[dev]
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
    cd shared && uv run ruff check {{ args }}
    cd services/orchestrator && uv run ruff check {{ args }}
    cd services/fcd-manager && uv run ruff check {{ args }}
    cd services/traffic-monitor && uv run ruff check {{ args }}
    @echo "Linting passed!"

# Format code with ruff
format *args:
    @echo "Formatting code..."
    cd shared && uv run ruff format {{ args }}
    cd services/orchestrator && uv run ruff format {{ args }}
    cd services/fcd-manager && uv run ruff format {{ args }}
    cd services/traffic-monitor && uv run ruff format {{ args }}
    @echo "Code formatted!"

# Check code formatting without modifying
format-check *args:
    @echo "Checking code formatting..."
    cd shared && uv run ruff format --check {{ args }}
    cd services/orchestrator && uv run ruff format --check {{ args }}
    cd services/fcd-manager && uv run ruff format --check {{ args }}
    cd services/traffic-monitor && uv run ruff format --check {{ args }}
    @echo "Formatting check passed!"

# Composite: format-check + lint (code quality only, no tests)
check: format-check lint
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
    cd shared && uv sync --all-extras --quiet && uv run pytest -v {{ args }}

# Run tests for orchestrator service
test-orchestrator *args:
    @echo "Testing orchestrator service..."
    cd services/orchestrator && uv sync --all-extras --quiet && uv run pytest -v {{ args }}

# Run tests for fcd-manager service
test-fcd-manager *args:
    @echo "Testing fcd-manager service..."
    cd services/fcd-manager && uv sync --all-extras --quiet && uv run pytest -v {{ args }}

# Run tests for traffic-monitor service
test-traffic-monitor *args:
    @echo "Testing traffic-monitor service..."
    cd services/traffic-monitor && uv sync --all-extras --quiet && uv run pytest -v {{ args }}

# Run only unit tests (fast, no external dependencies)
test-unit *args:
    @echo "Running unit tests only..."
    cd shared && uv sync --all-extras --quiet && uv run pytest -m unit -v {{ args }}
    cd services/orchestrator && uv sync --all-extras --quiet && uv run pytest -m unit -v {{ args }}
    cd services/fcd-manager && uv sync --all-extras --quiet && uv run pytest -m unit -v {{ args }}
    cd services/traffic-monitor && uv sync --all-extras --quiet && uv run pytest -m unit -v {{ args }}
    @echo "All unit tests passed!"

# Run only integration tests
test-integration *args:
    @echo "Running integration tests only..."
    cd shared && uv sync --all-extras --quiet && uv run pytest -m integration -v {{ args }}
    cd services/orchestrator && uv sync --all-extras --quiet && uv run pytest -m integration -v {{ args }}
    cd services/fcd-manager && uv sync --all-extras --quiet && uv run pytest -m integration -v {{ args }}
    cd services/traffic-monitor && uv sync --all-extras --quiet && uv run pytest -m integration -v {{ args }}
    @echo "All integration tests passed!"

# Run all tests with coverage report
test-coverage *args:
    @echo "Running tests with coverage..."
    cd shared && uv sync --all-extras --quiet && uv run pytest --cov --cov-report=html --cov-report=term-missing {{ args }}
    cd services/orchestrator && uv sync --all-extras --quiet && uv run pytest --cov --cov-report=html --cov-report=term-missing {{ args }}
    cd services/fcd-manager && uv sync --all-extras --quiet && uv run pytest --cov --cov-report=html --cov-report=term-missing {{ args }}
    cd services/traffic-monitor && uv sync --all-extras --quiet && uv run pytest --cov --cov-report=html --cov-report=term-missing {{ args }}
    @echo "Coverage reports generated in each service's htmlcov/ directory"

# Run all tests in parallel (fast)
test-parallel *args:
    @echo "Running tests in parallel..."
    cd shared && uv sync --all-extras --quiet && uv run pytest -n auto -v {{ args }}
    cd services/orchestrator && uv sync --all-extras --quiet && uv run pytest -n auto -v {{ args }}
    cd services/fcd-manager && uv sync --all-extras --quiet && uv run pytest -n auto -v {{ args }}
    cd services/traffic-monitor && uv sync --all-extras --quiet && uv run pytest -n auto -v {{ args }}
    @echo "All parallel tests passed!"

# Run multithreading equivalence tests for fcd-manager
test-equivalence *args:
    @echo "Testing multithreading equivalence..."
    cd services/fcd-manager && uv sync --all-extras --quiet && uv run pytest tests/test_multithreading_equivalence.py -v {{ args }}
    @echo "Equivalence tests passed!"

####################
# Workflows
####################

# Run all pre-commit checks (non-mutating: format-check, lint, test-unit)
pre-commit: format-check lint test-unit
    @echo "Pre-commit checks passed!"

# Simulate CI pipeline (format-check + lint + test with coverage)
ci: format-check lint test-coverage
    @echo "CI simulation passed!"
