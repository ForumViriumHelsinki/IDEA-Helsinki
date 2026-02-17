# Testing Requirements

## Test Structure

IDEA-Helsinki uses pytest with the following test markers:
- **`unit`** - Fast tests with no external dependencies (database, network, filesystem)
- **`integration`** - Tests requiring services (InfluxDB, Azure Blob, WFS API)
- **`e2e`** - End-to-end tests across all services

## Quick Testing

Use the Justfile for convenient test execution:

```bash
# Fast unit tests only (< 30 seconds)
just test-unit

# All tests sequentially
just test

# All tests in parallel (faster for large test suite)
just test-parallel

# Tests with coverage reports
just test-coverage

# Individual service testing
just test-shared
just test-orchestrator
just test-fcd-manager
just test-traffic-monitor

# Full CI pipeline simulation
just ci
```

## Running Specific Tests

```bash
# Tests matching a pattern
pytest -k test_pattern

# Specific test file
pytest path/to/test_file.py

# Specific test in a file
pytest path/to/test_file.py::test_name

# Only unit tests (fast)
pytest -m unit

# Only integration tests
pytest -m integration

# Stop on first failure
pytest -x
```

## Test Organization

Tests are colocated with source code:
- Shared library: `shared/tests/`
- Services: `services/<service>/tests/`

Test files follow naming convention: `test_<module>.py`

## Coverage Requirements

- **Target**: > 80% overall coverage
- **Critical paths**: 100% coverage for validation logic
- **View coverage**: `just test-coverage`

## Parallel Testing

Run tests across multiple CPU cores for faster execution:

```bash
# Auto-detect number of CPUs
pytest -n auto

# Use specific number of workers
pytest -n 4

# Parallel with coverage
pytest -n auto --cov --cov-report=xml --cov-report=term-missing
```

## Before Committing

```bash
# Minimum: Fast pre-commit check (unit tests only)
just pre-commit

# Recommended: Full test suite
just test

# Before opening PR: Full CI simulation
just ci
```

## Integration Tests

Integration tests may require:
- InfluxDB running (can use Docker Compose or Kubernetes)
- Azure credentials in `.env`
- Sufficient disk space for test data

Run integration tests explicitly:
```bash
pytest -m integration
```

## Debugging Tests

```bash
# Show print statements and logging
pytest -s

# Verbose output with detailed test info
pytest -v

# Extra verbose (full diffs on failures)
pytest -vv

# Show local variables in tracebacks
pytest -l

# Stop after N failures
pytest --maxfail=3
```

## Test-Driven Development (TDD)

Always follow RED → GREEN → REFACTOR:

1. Write a failing test that defines desired behavior
2. Implement minimal code to make the test pass
3. Refactor to improve quality while keeping tests green

Use `just test-unit` after each implementation change for fast feedback.
