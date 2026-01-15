# Test with Makefile

Run tests and code quality checks using the project's Makefile. This is the recommended approach for testing in the IDEA-Helsinki project.

## Usage

```
/test-with-make [target]
```

## Parameters

- `target` (optional): Specific make target to run. If omitted, shows help with all available targets.

## Available Targets

### Quick Testing
- `make test` - Run all tests sequentially
- `make test-parallel` - Run all tests in parallel (faster)
- `make test-unit` - Run only unit tests (fast, no external dependencies)
- `make test-integration` - Run only integration tests

### Individual Services
- `make test-shared` - Test shared library only
- `make test-orchestrator` - Test orchestrator service
- `make test-fcd-manager` - Test FCD manager service
- `make test-traffic-monitor` - Test traffic monitor service

### Coverage
- `make test-cov` - Run all tests with coverage reports (generates htmlcov/ in each service)

### Code Quality
- `make lint` - Run ruff linting checks
- `make format` - Auto-format code with ruff
- `make format-check` - Check formatting without modifying

### Workflows
- `make pre-commit` - Run format + lint + unit tests (recommended before committing)
- `make ci` - Simulate full CI pipeline (format-check + lint + test-cov)

### Utilities
- `make clean` - Remove test artifacts and cache files (__pycache__, .pytest_cache, htmlcov, etc.)
- `make install-deps` - Install dependencies for all services
- `make help` - Show all available targets with descriptions

## What This Command Does

1. **Analyzes the request** to determine which make target to run
2. **Executes the appropriate make command** from the project root
3. **Reports results** including any test failures or linting issues
4. **Suggests next steps** based on the output

## Common Workflows

### Before Committing
```
/test-with-make pre-commit
```
This runs formatting, linting, and unit tests - the fastest way to ensure code quality.

### During Development
```
/test-with-make test-unit
```
Quick unit tests provide fast feedback during TDD cycles.

### Comprehensive Testing
```
/test-with-make test-cov
```
Full test suite with coverage reports for thorough validation.

### Single Service Testing
```
/test-with-make test-orchestrator
```
Test only the orchestrator service when working on that specific component.

## Architecture Notes

The Makefile wraps the per-service testing architecture:
- Each service maintains its own virtual environment
- Tests are run from each service's directory using `uv run --no-sync pytest`
- The Makefile automates running tests across all three services + shared library
- Follows the production Docker container architecture

## Examples

### Show All Available Commands
```
/test-with-make
```
or
```
/test-with-make help
```

### Run Quick Pre-Commit Checks
```
/test-with-make pre-commit
```

### Run All Tests with Coverage
```
/test-with-make test-cov
```

### Test a Specific Service
```
/test-with-make test-fcd-manager
```

### Clean All Test Artifacts
```
/test-with-make clean
```

## Benefits

- **Consistency**: Same commands work for all developers
- **Simplicity**: No need to remember complex pytest or ruff invocations
- **Comprehensive**: Single command runs tests across all services
- **Fast feedback**: Parallel testing and unit-only options for speed
- **CI alignment**: `make ci` simulates the full GitHub Actions pipeline

## See Also

- [CLAUDE.md Testing Section](../CLAUDE.md#testing) - Detailed testing documentation
- [README.md Testing](../README.md#testing-and-development) - Quick start guide
- [Makefile](../Makefile) - Full implementation details
