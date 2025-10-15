# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

IDEA-Helsinki is a traffic validation system for analyzing the impact of traffic disturbances (like roadworks) on road segments in Helsinki. It processes real-time floating car data (FCD) from TomTom and correlates it with planned traffic disturbances from Helsinki's WFS services to validate traffic impact predictions using the IDEA algorithm.

## Core Application Entry Points

### Main Applications
- `IDEA_Helsinki.py` - Main async orchestration service for IDEA validation
- `helsinki_fcd_manager.py` - FCD data synchronization from Azure blob storage to InfluxDB
- `helsinki_traffic_disturbance_monitor.py` - Traffic disturbance monitoring and intersection detection

### Running Applications
```bash
# Run IDEA validation service
python IDEA_Helsinki.py

# Run FCD data synchronization service
python helsinki_fcd_manager.py

# Run traffic disturbance monitoring
python helsinki_traffic_disturbance_monitor.py
```

## Infrastructure and Data Management

### InfluxDB Container Management
```bash
# Initialize InfluxDB container (first time only)
./Docker/InfluxDB/init_run_influxdb_docker_container.sh

# Start existing InfluxDB container
./Docker/InfluxDB/run_influxdb_docker_container.sh

# Stop InfluxDB container
./Docker/InfluxDB/stop_influxdb_docker_container.sh

# Remove InfluxDB container and data
./Docker/InfluxDB/remove_influxdb_docker_container.sh

# Delete bucket contents
./Docker/InfluxDB/delete_influxdb_bucket_contents.sh
```

## Architecture Overview

### Three-Stage Pipeline
1. **FCD Manager**: Processes TomTom floating car data from Azure blob storage, maintains segment geometry mapping, stores timeseries data in InfluxDB
2. **Traffic Disturbance Monitor**: Fetches traffic disturbance data from Helsinki WFS API, performs spatial intersection with FCD segments, validates disturbances against data availability
3. **IDEA Helsinki**: Runs IDEA algorithm validation workers on intersected segments, compares actual vs expected traffic patterns, stores validation results

### Key Components

#### Data Sources
- **Azure FCD Storage**: TomTom floating car data blobs
- **Helsinki WFS Service**: Planned roadworks and traffic disturbances
- **InfluxDB**: Time-series storage for FCD data and validation results
- **Local JSON Files**: Segment mapping and intersection data

#### Core Classes
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

### Constants Configuration
- `lib/Constants/Constants.py` - Public configuration (update frequencies, file paths, timeframes)
- `lib/Constants/PrivateConstants.py` - Private credentials (Azure, InfluxDB tokens) - use PrivateConstantExample.py as template

### Key Settings
- FCD history requirement: 6 months minimum for validation
- Profile timeframe: 26 weeks default
- Validation frequency: 5 minutes
- FCD update frequency: 5 minutes
- Traffic disturbance update: 60 minutes

## Data Storage Locations

### Local Files
- `data/segments_mapping.json` - Current FCD segment geometries
- `data/master_segment_history.json` - Segment geometry change tracking
- `data/archived_segment_history.json` - Removed segments archive
- `data/traffic_disturbance_data.json` - Intersected segment-disturbance data

### InfluxDB Buckets
- FCD bucket: Raw speed/confidence timeseries data
- IDEA validation bucket: Algorithm validation results

## Important Implementation Notes

### Async Architecture
IDEA_Helsinki.py uses asyncio for concurrent segment processing. Each road segment runs as an independent worker with its own validation lifecycle.

### Geometry Tracking
The system tracks segment geometry changes using SHA-256 hashing to detect when TomTom updates road segment definitions, maintaining historical mapping for consistent analysis.

### Validation Requirements
Traffic disturbances can only be validated if there's at least 6 months of FCD history available for affected segments, ensuring sufficient baseline data for impact analysis.

## Testing

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
cd services/{service-name}  # idea-helsinki, fcd-manager, or traffic-monitor
uv venv
. .venv/bin/activate
uv pip install -e ../../shared
uv pip install -e .[dev]
pytest
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
