# Development Workflow

## Test-Driven Development (TDD)

Follow strict RED → GREEN → REFACTOR workflow:

1. **RED**: Write a failing test that defines desired behavior
2. **GREEN**: Implement minimal code to make the test pass
3. **REFACTOR**: Improve code quality while keeping tests green

Use the Justfile for quick testing:
```bash
just test-unit              # Fast unit tests only
just pre-commit             # Format, lint, typecheck, and test before committing
```

## Commit Conventions

Use conventional commit messages (enables automated versioning via release-please):

- **`feat:`** - New features (minor version bump)
- **`fix:`** - Bug fixes (patch version bump)
- **`feat!:` or `BREAKING CHANGE:`** - Breaking changes (major version bump)
- **`chore:`, `docs:`, `style:`, `refactor:`** - No version bump

Example:
```bash
git commit -m "feat: add segment caching with TTL configuration"
git commit -m "fix: resolve health check failures in orchestrator"
git commit -m "feat!: redesign validation worker pool

BREAKING CHANGE: Worker pool configuration API changed."
```

## uv Workspace Development

This is a **uv workspace** project with workspace members:
- `shared/` - Shared library (idea-shared)
- `services/orchestrator/`
- `services/fcd-manager/`
- `services/traffic-monitor/`

All packages share a single lockfile (`uv.lock`) and virtual environment.

### Dependency Management

```bash
# Install all dependencies
uv sync --all-packages --all-extras

# Add a dependency to a specific service
uv add --package <service-name> <package-name>

# Update workspace
uv sync
```

### Running Code

```bash
# Run in a specific service
uv run --package <service-name> --directory services/<service-name> python <script>

# Run shared library tests
uv run --package idea-shared --directory shared python -m pytest tests
```

## Local Kubernetes Development

Use Skaffold for local development with hot reload:

```bash
# Start all services with automatic rebuild on file changes
skaffold dev

# Clean up
skaffold delete
```

Services are available via Kubernetes service discovery. InfluxDB UI: http://localhost:8086

### Environment Setup

Create `.env` file with Azure credentials:
```bash
AZURE_ACCOUNT_NAME=your-account
AZURE_CONTAINER_NAME=your-container
AZURE_SAS_TOKEN=your-token
```

Run with: `dotenvx run -- skaffold dev`

## Before Committing

1. Run fast pre-commit checks:
   ```bash
   just pre-commit    # Format + lint + typecheck + unit tests
   ```

2. Ensure tests pass:
   ```bash
   just test          # Run all tests
   ```

3. Check for uncommitted changes and untracked files

4. Review git diff before staging

5. Commit with descriptive message using conventional format

## Local↔CI Parity

Every job in `.github/workflows/lint.yml` has a justfile recipe that runs the
same commands locally:

| CI job | Local recipe |
|---|---|
| `lint` | `just lint` |
| `type-check` | `just typecheck` |

Both recipes depend on `just sync`, which runs CI's install step
(`uv sync --all-packages --all-extras`). Without that sync the workspace members
are missing from the venv and `ty` reports hundreds of spurious
`unresolved-import` diagnostics (#520) — the failure mode that made `SKIP=ty` a
habit.

The `ty` pre-commit hook calls `just typecheck` rather than `ty` directly, so
the hook, the recipe and the CI job are one definition. Running the hooks
therefore requires `just` on `PATH`.

`shared/tests/unit/test_ci_parity.py` enforces this: it fails when a job is
added to `lint.yml` without a local counterpart, when a recipe stops running
what its CI job runs (sync included), or when `just ci` no longer covers every
CI job. Adding a job means adding the recipe and the mapping entry in that test.
