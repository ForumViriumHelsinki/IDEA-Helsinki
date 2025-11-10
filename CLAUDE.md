# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

IDEA-Helsinki is a traffic validation system for analyzing the impact of traffic disturbances (like roadworks) on road segments in Helsinki. It processes real-time floating car data (FCD) from TomTom and correlates it with planned traffic disturbances from Helsinki's WFS services to validate traffic impact predictions using the IDEA algorithm.

## Core Application Services

IDEA-Helsinki is composed of three microservices that run as containers in Kubernetes:

### Orchestrator Service
- **Path**: `services/orchestrator/src/main.py`
- **Purpose**: Main async orchestration service for IDEA validation
- **Container**: `orchestrator`

### FCD Manager Service
- **Path**: `services/fcd-manager/src/main.py`
- **Purpose**: FCD data synchronization from Azure blob storage to InfluxDB
- **Container**: `fcd-manager`

### Traffic Monitor Service
- **Path**: `services/traffic-monitor/src/main.py`
- **Purpose**: Traffic disturbance monitoring and spatial intersection detection
- **Container**: `traffic-monitor`

## Running the Application

### Local Development with Skaffold

The entire stack (all three services + InfluxDB) can be run locally with a single command:

```bash
# Start all services in development mode with hot reload
skaffold dev

# Services will be available at:
# - InfluxDB UI: http://localhost:8086
# - Services communicate via k8s service discovery
```

**First-time setup**: On initial startup, InfluxDB automatically creates:
- Organization: `idea-helsinki`
- Buckets: `fcd-data`, `validation`
- Admin token: `dev-token-changeme` (configurable via environment)

To reset InfluxDB state:
```bash
# Delete the deployment and persistent volume
skaffold delete
kubectl delete pvc influxdb-pvc -n idea-helsinki

# Restart with clean state
skaffold dev
```

### Environment Configuration

**Required setup**: Create a `.env` file in the project root with Azure credentials:

```bash
# .env file (required)
AZURE_ACCOUNT_NAME=your-account
AZURE_CONTAINER_NAME=your-container
AZURE_SAS_TOKEN=your-token

# Optional: Override InfluxDB defaults
INFLUX_DB_ORG=idea-helsinki
INFLUX_DB_URL=http://influxdb:8086
INFLUX_DB_FCD_BUCKET=fcd-data
INFLUX_DB_VALIDATION_BUCKET=validation
```

**How it works**: When you run `dotenvx run -- skaffold dev`:
1. `dotenvx` loads variables from `.env`
2. The pre-deploy hook (`scripts/generate-secrets.sh`) generates `k8s/secrets.yaml` from `k8s/secrets.yaml.tmpl`
3. Missing InfluxDB variables are filled with defaults suitable for local development
4. Skaffold deploys with the generated secrets

## Architecture Overview

### Three-Stage Pipeline
1. **FCD Manager** (`fcd-manager` service): Processes TomTom floating car data from Azure blob storage, maintains segment geometry mapping, stores timeseries data in InfluxDB
2. **Traffic Monitor** (`traffic-monitor` service): Fetches traffic disturbance data from Helsinki WFS API, performs spatial intersection with FCD segments, validates disturbances against data availability
3. **Orchestrator** (`orchestrator` service): Runs IDEA algorithm validation workers on intersected segments, compares actual vs expected traffic patterns, stores validation results

### Key Components

#### Infrastructure
- **Kubernetes**: Container orchestration (local via Skaffold + OrbStack)
- **Skaffold**: Development workflow automation (build, deploy, hot reload)
- **InfluxDB StatefulSet**: Time-series database with persistent storage

#### Data Sources
- **Azure FCD Storage**: TomTom floating car data blobs
- **Helsinki WFS Service**: Planned roadworks and traffic disturbances
- **InfluxDB Buckets**:
  - `fcd-data`: Raw speed/confidence timeseries
  - `validation`: IDEA validation results
- **Shared Volumes**: Segment mapping and intersection data (mounted in pods)

#### Core Classes (Shared Library)
Located in `shared/src/idea_shared/`:
- `IdeaHelsinkiManager` - Orchestrates IDEA validation workers
- `IdeaHelsinkiRoadSegment` - Individual segment validation logic
- `IntersectionDetector` - Spatial analysis for segment-disturbance intersections
- `FCDInfluxDBManager` - InfluxDB operations for FCD data
- `AzureBlobContainerManager` - Azure blob storage interface
- `HelsinkiWFSClient` - WFS service client for traffic disturbances

#### Data Models
- **FCD Segment Mapping**: Current road segment geometries (LineString GeoJSON)
- **Master Segment History**: Tracks geometry changes over time with SHA-256 hashing
- **Traffic Disturbance Intersections**: FCD segments affected by specific disturbances
- **Time Series Data**: Speed/confidence metrics per segment per 5-minute interval

### Processing Flow
1. FCD data ingestion from Azure → geometry mapping → InfluxDB storage
2. Traffic disturbance fetching → validation against 6-month FCD history → intersection detection
3. IDEA workers process validated segments → profile analysis → impact validation results

## Configuration

### Shared Library Configuration
- **Path**: `shared/src/idea_shared/lib/Constants/`
- **Constants.py**: Public configuration (update frequencies, file paths, timeframes)
- **PrivateConstants.py**: Private credentials (Azure, InfluxDB tokens)
  - Use `PrivateConstantExample.py` as template for local development
  - In Kubernetes, values are injected via `k8s/secrets.yaml` (generated from `secrets.yaml.tmpl`)

### Key Settings
- FCD history requirement: 6 months minimum for validation
- Profile timeframe: 26 weeks default
- Validation frequency: 5 minutes
- FCD update frequency: 5 minutes
- Traffic disturbance update: 60 minutes

### Kubernetes Secrets
Configuration is managed through environment variables and generated during deployment:
- **Template**: `k8s/secrets.yaml.tmpl` - Secret structure with `${VAR}` placeholders
- **Generator**: `scripts/generate-secrets.sh` - Shell script that sets defaults and runs `envsubst`
- **Generated**: `k8s/secrets.yaml` - Auto-generated before deployment (gitignored)
- **Workflow**: `dotenvx` → `generate-secrets.sh` → `envsubst` → `k8s/secrets.yaml`

### Feature Flags Configuration
- `data/feature_flags.json` - Feature flag configuration (use `data/feature_flags.example.json` as template)
- Supports toggling experimental features, performance optimizations, and configuration overrides
- Can use JSON files (development) or environment variables (production)
- See `shared/src/idea_shared/feature_flags/README.md` for detailed documentation

## Versioning Strategy

IDEA-Helsinki uses **unified versioning** where all components (shared library and three services) share a single version number. This ensures perfect compatibility and simplifies deployment.

### Current Approach
- All components move together via release-please's `linked-versions` plugin
- Services depend on adjacent shared library code (editable installs)
- Breaking changes update all components atomically
- See `docs/VERSIONING.md` for detailed versioning documentation

### Version Information

**Release manifest**: `.release-please-manifest.json`
```json
{
  "shared": "0.9.0",
  "services/orchestrator": "0.9.0",
  "services/fcd-manager": "0.9.0",
  "services/traffic-monitor": "0.9.0"
}
```

**Docker images** include version metadata:
- Labels: `org.idea-helsinki.version` and `org.opencontainers.image.version`
- Version file: `/app/VERSION` (readable at runtime)

### Release Process
1. Use conventional commits (`feat:`, `fix:`, `feat!:` for breaking changes)
2. Release-please creates PR with version bumps and changelog
3. Merge PR triggers GitHub release and Docker builds
4. All services deploy together with same version

### Semantic Versioning
- **MAJOR** (X.0.0): Breaking changes anywhere in the system
- **MINOR** (0.X.0): New backward-compatible features
- **PATCH** (0.0.X): Backward-compatible bug fixes

**Why unified versioning?**
- Matches deployment reality (all services deployed together)
- Implements "living at HEAD" development pattern
- Eliminates version drift between shared library and services
- Simpler mental model (one version = complete system state)

## Data Storage Locations

### Persistent Data Files
Mounted as shared volumes in Kubernetes pods:
- `data/segments_mapping.json` - Current FCD segment geometries
- `data/master_segment_history.json` - Segment geometry change tracking
- `data/archived_segment_history.json` - Removed segments archive
- `data/traffic_disturbance_data.json` - Intersected segment-disturbance data

### InfluxDB Buckets
Automatically created on first startup via `/docker-entrypoint-initdb.d/init-buckets.sh`:
- **fcd-data**: Raw speed/confidence timeseries (created via DOCKER_INFLUXDB_INIT_BUCKET)
- **validation**: IDEA algorithm validation results (created via init script)

## Important Implementation Notes

### Microservices Architecture
The application uses a microservices architecture with three independent services:
- Each service runs in its own container with dedicated resources
- Services communicate via shared data files and InfluxDB
- Built with Python 3.12, packaged with `uv` and `hatchling`

### Async Architecture
The orchestrator service (`services/orchestrator/src/main.py`) uses asyncio for concurrent segment processing. Each road segment runs as an independent worker with its own validation lifecycle.

### Geometry Tracking
The FCD Manager tracks segment geometry changes using SHA-256 hashing to detect when TomTom updates road segment definitions, maintaining historical mapping for consistent analysis.

### Validation Requirements
Traffic disturbances can only be validated if there's at least 6 months of FCD history available for affected segments, ensuring sufficient baseline data for impact analysis.

### Shared Library Pattern
Common functionality is in `shared/src/idea_shared/`:
- All three services depend on the shared library
- Installed as editable dependency during container build
- Version: managed independently in `shared/pyproject.toml`

## Testing

### **Per-Service Testing Architecture**

This microservices architecture uses independent testing environments for each service. Run tests from each service's directory to leverage the benefits of this design:

**Best practice: Run tests from service directories**
- Each service maintains its own virtual environment and dependencies
- Test isolation ensures clean dependency resolution
- Follows the production Docker container architecture
- Aligns with microservices testing best practices

**Benefits of per-service testing:**
- Clean module imports without namespace conflicts
- Accurate dependency version testing for each service
- Faster test execution through better isolation
- Matches how services run in production

### Running Tests Locally

#### Shared Library Tests
```bash
cd shared
uv venv
. .venv/bin/activate
uv pip install -e .[dev]
pytest
```

#### Service Tests
```bash
cd services/{service-name}  # orchestrator, fcd-manager, or traffic-monitor
uv venv
uv pip install -e ../../shared
uv pip install -e '.[dev]'

# Run tests using uv run (recommended - automatically uses venv)
uv run --no-sync pytest -v

# Alternative: manually activate venv
# . .venv/bin/activate
# pytest
```

#### Run with Coverage
```bash
# In shared directory
pytest --cov --cov-report=html
# Open htmlcov/index.html to view coverage report
```

#### Run Specific Test Types
```bash
pytest -m unit          # Only unit tests (fast, no external dependencies)
pytest -m integration   # Only integration tests (may require services)
pytest -k test_pattern  # Tests matching pattern
pytest path/to/test_file.py::test_name  # Run specific test
```

#### Parallel Testing
```bash
# Run tests in parallel using multiple CPU cores (speeds up test execution)
pytest -n auto          # Auto-detect number of CPUs
pytest -n 4             # Use 4 parallel workers

# Parallel with coverage
pytest -n auto --cov --cov-report=xml --cov-report=term-missing

# Parallel testing with specific markers
pytest -n auto -m unit  # Run only unit tests in parallel
```

#### Advanced Pytest Options
```bash
# Verbose output with detailed test information
pytest -v               # Verbose mode
pytest -vv              # Extra verbose (shows full diff on failures)

# Stop on first failure (useful during TDD)
pytest -x               # Stop after first failure
pytest --maxfail=3      # Stop after 3 failures

# Run only tests that failed in the last run
pytest --lf             # Last failed
pytest --ff             # Failed first (run failures first, then rest)

# Show local variables in tracebacks
pytest -l               # Show locals in tracebacks

# Disable output capture (see print statements immediately)
pytest -s               # No capture (useful for debugging)

# Run with pytest warnings
pytest -W error         # Turn warnings into errors
pytest -W ignore        # Ignore warnings
```

### Test-Driven Development Workflow

We follow **RED-GREEN-REFACTOR**:

1. **RED**: Write a failing test first
   ```bash
   pytest path/to/test_file.py::test_name  # Should fail
   ```

2. **GREEN**: Write minimal code to pass
   ```bash
   pytest path/to/test_file.py::test_name  # Should pass
   ```

3. **REFACTOR**: Improve code while keeping tests green
   ```bash
   pytest  # All tests should still pass
   ```

### Before Committing
```bash
# Run tests
pytest

# Run linting
ruff check
ruff format

# Commit with descriptive message
git add .
git commit -m "feat: implement feature X with tests"
```

### CI/CD
- Tests run automatically on push and PR via GitHub Actions
- All tests must pass before merging
- Coverage reports are generated and tracked via Codecov
- Matrix testing across all three services ensures compatibility

## Feature Flags

IDEA-Helsinki supports feature flags for toggling functionality and configuration without code changes. This is useful for:
- Developing and testing new features safely
- Gradual rollouts of improvements
- Performance optimization experiments
- Environment-specific behavior

### Quick Start

**Initialize at service startup:**
```python
from idea_shared.feature_flags import initialize_feature_flags
from idea_shared.feature_flags.providers import JsonFileProvider

# Development: Use JSON file
provider = JsonFileProvider("data/feature_flags.json")
initialize_feature_flags(provider)

# Production: Use environment variables
from idea_shared.feature_flags.providers import EnvironmentVariableProvider
provider = EnvironmentVariableProvider()
initialize_feature_flags(provider)
```

**Use throughout application:**
```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag

flags = get_feature_flags()

if flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION):
    # Use experimental algorithm
    pass
```

### Configuration

**JSON file** (`data/feature_flags.json`):
```json
{
  "flags": {
    "enable_caching": {
      "enabled": true,
      "description": "Enable in-memory caching"
    }
  }
}
```

**Environment variables:**
```bash
FEATURE_FLAG_ENABLE_CACHING=true
FEATURE_FLAG_MAX_CONNECTIONS=100
```

### Available Flags

- `ENABLE_EXPERIMENTAL_VALIDATION` - Toggle experimental validation algorithms
- `ENABLE_PARALLEL_PROCESSING` - Process segments in parallel (default: true)
- `ENABLE_SEGMENT_CACHING` - Cache FCD segment geometries in memory
- `ENABLE_ENHANCED_LOGGING` - Detailed debug logging
- `FCD_UPDATE_INTERVAL_OVERRIDE` - Override FCD update frequency (minutes)
- `DISTURBANCE_UPDATE_INTERVAL_OVERRIDE` - Override disturbance update frequency

See `shared/src/idea_shared/feature_flags/README.md` for comprehensive documentation and examples.
