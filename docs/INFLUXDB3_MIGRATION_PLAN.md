# InfluxDB 2.7 → 3 Migration Plan

## Executive Summary

Migrate IDEA-Helsinki from InfluxDB 2.7 (self-hosted, TSM engine, Flux) to **InfluxDB 3 Cloud** (managed, Apache Arrow + DataFusion + Parquet, SQL). The migration is **feature-flagged** — both v2 and v3 code paths coexist, controlled by the existing feature flag system, enabling instant rollback.

**Data strategy**: No data migration needed. Historical data will be reprocessed from Azure blob storage into InfluxDB Cloud. The local InfluxDB 2.7 StatefulSet remains available as fallback during the transition.

### Why Migrate

- **Flux is deprecated**: InfluxDB 3 removes Flux entirely. Our 12+ Flux queries must become SQL.
- **Performance**: Near-unlimited series cardinality, sub-10ms last-value queries, columnar storage.
- **Docker tag change**: On **April 7, 2026**, the `latest` Docker tag switches to InfluxDB 3 Core. Our `influxdb:2.7-alpine` pin protects us, but 2.7 receives no further updates.
- **InfluxDB Cloud**: Managed service eliminates operational burden of the local StatefulSet.

### Scope

| In scope | Out of scope |
|----------|-------------|
| Client library swap (`influxdb-client` → `influxdb3-python`) | Kubernetes deployment changes |
| Flux → SQL query rewrite | Data migration/export from v2 |
| Feature flag to toggle v2/v3 | Multi-region HA setup |
| Health check migration | InfluxDB Cloud provisioning |
| New `FCDInfluxDBManagerV3` class | Changes to Azure blob ingestion |

---

## 1. Feature Flag Design

### 1.1 Flag Definition

Add to `shared/src/idea_shared/feature_flags/flags.py`:

```python
class FeatureFlag(StrEnum):
    # ... existing flags ...

    # InfluxDB version selection
    INFLUXDB_VERSION = "influxdb_version"
```

```python
class FlagDefaults:
    # ... existing defaults ...

    INFLUXDB_VERSION: str = "v2"  # Safe default: current behavior
```

### 1.2 Configuration

**JSON file** (`data/feature_flags.json`):
```json
{
  "flags": {
    "influxdb_version": {
      "value": "v2",
      "description": "InfluxDB client version: 'v2' (self-hosted, Flux) or 'v3' (Cloud, SQL)"
    }
  }
}
```

**Environment variable** (production):
```bash
FEATURE_FLAG_INFLUXDB_VERSION=v3
```

### 1.3 New Environment Variables for v3

When the flag is set to `v3`, the following env vars are read:

```bash
# InfluxDB 3 Cloud connection (only used when flag = v3)
INFLUX_DB_V3_HOST=us-east-1-1.aws.cloud2.influxdata.com  # Cloud host (no http://)
INFLUX_DB_V3_TOKEN=your-cloud-token
INFLUX_DB_V3_FCD_DATABASE=fcd-data
INFLUX_DB_V3_VALIDATION_DATABASE=validation
```

The existing v2 env vars remain untouched — both sets coexist.

---

## 2. Architecture — Factory + Strategy Pattern

### 2.1 Overview

```
Callers (IdeaHelsinkiRoadSegment, fcd-manager, health checks)
    │
    │  unchanged public interface
    ▼
┌──────────────────────────────────┐
│  create_influxdb_manager()       │  ← factory reads feature flag
│  (shared/classes/__init__.py)    │
└───────────┬──────────────────────┘
            │
      ┌─────┴──────┐
      ▼            ▼
┌───────────┐ ┌───────────┐
│ FCDInflux  │ │ FCDInflux  │
│ DBManager  │ │ DBManager  │
│ (v2/Flux)  │ │ V3 (SQL)   │
└───────────┘ └───────────┘
```

### 2.2 Why This Works

The `FCDInfluxDBManager` public interface is **already query-language agnostic**. Callers never touch Flux — they call methods like:

| Method | Return type | Used by |
|--------|-------------|---------|
| `check_connection()` | `bool` | All services |
| `get_last_update_timestamp()` | `datetime \| None` | fcd-manager |
| `get_last_segment_update_timestamp()` | `datetime \| None` | orchestrator |
| `get_first_segment_update_timestamp()` | `datetime \| None` | orchestrator |
| `get_segment_data_dataframe()` | `DataFrame \| None` | orchestrator |
| `get_segment_data_csv()` | `str \| None` | orchestrator |
| `write_dataframe()` | `None` | orchestrator |
| `write_fcd_model()` | `None` | fcd-manager |
| `close()` | `None` | All services |

Both implementations return identical types. Callers don't change at all.

### 2.3 Factory Function

```python
# shared/src/idea_shared/classes/influxdb_factory.py

from idea_shared.feature_flags import get_feature_flags, FeatureFlag

def create_influxdb_manager(
    url: str,
    token: str,
    org: str,
    bucket: str,
    timeout: int = 300_000,
):
    """Create the appropriate InfluxDB manager based on feature flag.

    Callers pass the SAME arguments as today. When v3 is active,
    the factory maps them to v3 equivalents:
      - url   → ignored (reads INFLUX_DB_V3_HOST from env)
      - org   → ignored (not needed in v3)
      - bucket → mapped to database name
    """
    flags = get_feature_flags()
    version = flags.get_string(FeatureFlag.INFLUXDB_VERSION, default="v2")

    if version == "v3":
        from idea_shared.classes.FCDInfluxDBManagerV3 import FCDInfluxDBManagerV3
        import os

        # v3 connection params come from dedicated env vars
        host = os.getenv("INFLUX_DB_V3_HOST", "localhost:8181")
        v3_token = os.getenv("INFLUX_DB_V3_TOKEN", token)

        # Map bucket name → database name
        fcd_db = os.getenv("INFLUX_DB_V3_FCD_DATABASE", "fcd-data")
        val_db = os.getenv("INFLUX_DB_V3_VALIDATION_DATABASE", "validation")

        # Determine which database based on the bucket being requested
        database = val_db if "validation" in bucket.lower() else fcd_db

        return FCDInfluxDBManagerV3(
            host=host,
            token=v3_token,
            database=database,
            timeout=timeout,
        )
    else:
        from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager

        return FCDInfluxDBManager(
            url=url, token=token, org=org,
            bucket=bucket, timeout=timeout,
        )
```

### 2.4 Call Site Changes

All 13 production call sites change from direct instantiation to the factory. Example:

```python
# BEFORE (IdeaHelsinkiRoadSegment.py:346)
with FCDInfluxDBManager(
    url=self.db_url,
    token=self.db_validation_token,
    org=self.db_org,
    bucket=self.db_validation_bucket,
) as manager:
    ...

# AFTER
from idea_shared.classes.influxdb_factory import create_influxdb_manager

with create_influxdb_manager(
    url=self.db_url,
    token=self.db_validation_token,
    org=self.db_org,
    bucket=self.db_validation_bucket,
) as manager:
    ...
```

The arguments stay identical — the factory handles the v2/v3 routing internally.

**Complete call site inventory** (13 production locations):

| File | Line | Purpose |
|------|------|---------|
| `services/fcd-manager/src/main.py` | ~273 | Backfill init check |
| `services/fcd-manager/src/main.py` | ~348 | Write FCD data |
| `services/fcd-manager/src/main.py` | ~648 | Get last update timestamp |
| `services/fcd-manager/src/main.py` | ~771 | Get last FCD mapping timestamp |
| `shared/.../IdeaHelsinkiRoadSegment.py` | ~346 | Write validation results |
| `shared/.../IdeaHelsinkiRoadSegment.py` | ~383 | Get segment FCD data |
| `shared/.../IdeaHelsinkiRoadSegment.py` | ~419 | Get baseline confidence |
| `shared/.../IdeaHelsinkiRoadSegment.py` | ~461 | Get baseline speed |
| `shared/.../IdeaHelsinkiRoadSegment.py` | ~513 | Get impact data |
| `shared/.../threading/coordinator.py` | ~79 | Writer thread init |
| `shared/.../health/idea_checks.py` | ~198 | InfluxDB health check |
| `services/orchestrator/src/health_checks.py` | ~129 | Connection manager |
| `shared/.../health/utils.py` | ~90 | Backfill mode check |

---

## 3. New Class — `FCDInfluxDBManagerV3`

### 3.1 Module Structure

```
shared/src/idea_shared/classes/
├── FCDInfluxDBManager.py        # Existing v2 (unchanged)
├── FCDInfluxDBManagerV3.py      # New v3 implementation
└── influxdb_factory.py          # Factory function
```

### 3.2 Client Library

| Aspect | Current (`influxdb-client`) | New (`influxdb3-python`) |
|--------|---------------------------|--------------------------|
| Package | `influxdb-client` | `influxdb3-python` |
| Import | `from influxdb_client import InfluxDBClient` | `from influxdb_client_3 import InfluxDBClient3` |
| Connection | `InfluxDBClient(url=, token=, org=)` | `InfluxDBClient3(host=, token=, database=)` |
| Query | `client.query_api().query(flux)` | `client.query(sql, mode="pandas")` |
| Write DF | `write_api.write(record=df, data_frame_*)` | `client.write_dataframe(df, ...)` |
| Point write | `Point("m").tag().field()` | Same `Point` API |
| Ping | `client.ping()` | HTTP `/health` endpoint |

### 3.3 Dependencies

Both libraries coexist in `shared/pyproject.toml` during the transition:

```toml
dependencies = [
    "influxdb-client",       # v2 — keep until v2 code path removed
    "influxdb3-python",      # v3 — new
    # ... rest unchanged
]
```

### 3.4 Skeleton Implementation

```python
# shared/src/idea_shared/classes/FCDInfluxDBManagerV3.py

import pandas as pd
from datetime import datetime
from influxdb_client_3 import InfluxDBClient3
from idea_shared.classes.Logger import Logger

class FCDInfluxDBManagerV3:
    """InfluxDB 3 implementation using SQL queries and Arrow Flight protocol.

    Drop-in replacement for FCDInfluxDBManager with identical public interface.
    """

    def __init__(self, host: str, token: str, database: str, timeout: int = 300_000):
        self.client = InfluxDBClient3(
            host=host,
            token=token,
            database=database,
        )
        self.database = database
        self.logger = Logger(__name__)
        self.logger.info(
            f"FCDInfluxDBManagerV3 initialized - Host: {host}, "
            f"Database: {database}"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def check_connection(self) -> bool:
        """Check connectivity via a lightweight SQL query."""
        try:
            self.client.query("SELECT 1")
            return True
        except Exception as e:
            self.logger.error(f"InfluxDB 3 connection check failed: {e}")
            return False

    def get_last_update_timestamp(self, search_all: bool = False) -> datetime | None:
        ...  # SQL implementation (see Section 4)

    def get_segment_update_timestamp(self, ...) -> datetime | None:
        ...

    def get_last_segment_update_timestamp(self, ...) -> datetime | None:
        ...

    def get_first_segment_update_timestamp(self, ...) -> datetime | None:
        ...

    def get_segment_data_csv(self, ...) -> str | None:
        ...

    def get_segment_data_dataframe(self, ...) -> pd.DataFrame | None:
        ...

    def write_dataframe(self, df, segment_id, measurement_name, batch_size=5000):
        ...  # v3 write implementation (see Section 5)

    def write_fcd_model(self, fcd_data: dict, batch_size: int = 5000):
        ...

    def close(self):
        if self.client:
            self.client.close()
```

---

## 4. Query Migration — Flux → SQL

### 4.1 Query Safety: Parameterized Queries

InfluxDB 3's Python client supports parameterized queries natively, replacing `_sanitize_flux_string()`:

```python
# v2: Manual string sanitization
flux = f'... r.segmentId == "{_sanitize_flux_string(segment_id)}" ...'

# v3: Parameterized queries (injection-safe by design)
sql = "SELECT max(time) FROM segment_data WHERE segmentId = $segment_id"
result = client.query(sql, query_parameters={"segment_id": segment_id})
```

### 4.2 Complete Query Mapping

#### Query 1: Last update timestamp (`get_last_update_timestamp`)

```flux
-- CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: {range_start})
  |> filter(fn: (r) => r._measurement == "segment_data")
  |> last()
  |> keep(columns: ["_time"])
```
```sql
-- NEW (SQL)
SELECT max(time) as last_time
FROM segment_data
```

#### Query 2: Segment timestamp — last (`get_last_segment_update_timestamp`)

```flux
-- CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.segmentId == "{segment}")
  |> last()
  |> keep(columns: ["_time"])
```
```sql
-- NEW (SQL)
SELECT max(time) as last_time
FROM $measurement
WHERE "segmentId" = $segment_id
```

#### Query 3: Segment timestamp — first (`get_first_segment_update_timestamp`)

```flux
-- CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.segmentId == "{segment}")
  |> first()
  |> keep(columns: ["_time"])
```
```sql
-- NEW (SQL)
SELECT min(time) as first_time
FROM $measurement
WHERE "segmentId" = $segment_id
```

#### Query 4: Segment data — full range (`get_segment_data_dataframe` / `get_segment_data_csv`)

```flux
-- CURRENT (Flux) — requires pivot because v2 stores fields row-wise
from(bucket: "{bucket}")
  |> range(start: {start}, stop: {end})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r.segmentId == "{segment}")
  |> filter(fn: (r) => r._field == "speed" or r._field == "confidence")
  |> aggregateWindow(every: {interval}m, fn: last, createEmpty: false)
  |> sort(columns: ["_time"])
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
```
```sql
-- NEW (SQL) — fields are already columns in v3, no pivot needed
SELECT time, speed, confidence
FROM $measurement
WHERE "segmentId" = $segment_id
  AND time >= $start_time
  AND time <= $end_time
ORDER BY time ASC

-- With interval aggregation (DATE_BIN replaces aggregateWindow)
SELECT
  DATE_BIN(INTERVAL '5 minutes', time) as time_bin,
  LAST_VALUE(speed) as speed,
  LAST_VALUE(confidence) as confidence
FROM $measurement
WHERE "segmentId" = $segment_id
  AND time >= $start_time
  AND time <= $end_time
GROUP BY time_bin
ORDER BY time_bin ASC
```

#### Query 5: Recent data check (`check_backfill_mode` — freshness)

```flux
-- CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: -{threshold}m)
  |> filter(fn: (r) => r["_measurement"] == "{measurement}")
  |> last()
  |> keep(columns: ["_time"])
  |> limit(n: 1)
```
```sql
-- NEW (SQL)
SELECT max(time) as last_time
FROM $measurement
WHERE time >= now() - INTERVAL '$threshold minutes'
```

#### Query 6: Backfill lookback (`check_backfill_mode` — historical)

```flux
-- CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r["_measurement"] == "{measurement}")
  |> last()
  |> keep(columns: ["_time"])
  |> limit(n: 1)
```
```sql
-- NEW (SQL)
SELECT max(time) as last_time
FROM $measurement
WHERE time >= now() - INTERVAL '$days days'
```

#### Query 7: Validation data check (`ValidationDatabaseHealthCheck`)

```flux
-- CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "validation_result")
  |> keep(columns: ["_time"])
  |> limit(n: 1)
```
```sql
-- NEW (SQL)
SELECT time
FROM validation_result
WHERE time >= now() - INTERVAL '24 hours'
ORDER BY time DESC
LIMIT 1
```

---

## 5. Write Migration

### 5.1 Line Protocol (Unchanged)

The `Point` API is identical in both libraries:

```python
# Works in both v2 and v3
point = Point("segment_data").tag("segmentId", segment_id).time(dt_object)
point.field("speed", 42.5)
point.field("confidence", 0.95)
```

### 5.2 DataFrame Write

```python
# v2 (current)
self.write_api.write(
    bucket=self.bucket,
    record=df,
    data_frame_measurement_name=measurement_name,
    data_frame_tag_columns=["segmentId"],
    data_frame_timestamp_column="time",
)

# v3 (new)
self.client.write_dataframe(
    df,
    measurement=measurement_name,
    timestamp_column="time",
    tag_columns=["segmentId"],
)
```

### 5.3 Retry Strategy

Keep the application-level tenacity retry decorator, but update exception types for the v3 client:

```python
# v3 transient exceptions (to be determined during implementation)
_V3_TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    OSError,
    TimeoutError,
)

_influxdb_v3_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=15),
    retry=retry_if_exception_type(_V3_TRANSIENT_EXCEPTIONS),
    reraise=True,
)
```

The urllib3-level retry is not applicable — `influxdb3-python` uses a different HTTP stack.

---

## 6. Health Check Migration

### 6.1 Connection Check

```python
# v2: client.ping()
client = InfluxDBClient(url=url, token=token, org=org)
result = client.ping()

# v3: lightweight SQL query (no built-in ping)
client = InfluxDBClient3(host=host, token=token, database=database)
try:
    client.query("SELECT 1")
    return True
except Exception:
    return False
```

### 6.2 `check_backfill_mode()` Refactor

The current function in `shared/src/idea_shared/health/utils.py` accepts a v2 `QueryApi` object directly. This needs refactoring to work behind the feature flag:

**Option A (recommended)**: Make `check_backfill_mode()` accept the manager instead of raw query API:

```python
# BEFORE: Tightly coupled to v2 QueryApi
def check_backfill_mode(query_api: QueryApi, org, bucket, measurement, ...):
    recent_query = f'from(bucket: "{bucket}") |> range(...) ...'
    tables = query_api.query(query=recent_query, org=org)

# AFTER: Uses manager abstraction
def check_backfill_mode(manager, measurement, freshness_threshold_minutes, ...):
    # Manager handles the query language internally
    last_time = manager.get_recent_timestamp(measurement, freshness_threshold_minutes)
```

**Option B**: Create a v3-specific `check_backfill_mode_v3()` and select via flag.

### 6.3 `InfluxDBConnectionManager` (Orchestrator)

The connection manager in `services/orchestrator/src/health_checks.py` pools `InfluxDBClient` instances. For v3, either:
- Create `InfluxDBConnectionManagerV3` pooling `InfluxDBClient3` instances
- Or simplify: `InfluxDBClient3` may not need pooling (Arrow Flight connections are lighter)

### 6.4 Health Check Classes

`InfluxDBHealthCheck`, `FCDDatabaseHealthCheck`, `FCDDataFreshnessHealthCheck`, and `ValidationDatabaseHealthCheck` all instantiate `InfluxDBClient` directly. These need to check the feature flag and use the appropriate client.

---

## 7. Files Requiring Changes

### 7.1 New Files

| File | Purpose |
|------|---------|
| `shared/src/idea_shared/classes/FCDInfluxDBManagerV3.py` | v3 implementation with SQL queries |
| `shared/src/idea_shared/classes/influxdb_factory.py` | Factory function reading feature flag |
| `shared/tests/unit/test_fcd_influxdb_manager_v3.py` | Unit tests for v3 manager |

### 7.2 Modified Files

| File | Change |
|------|--------|
| `shared/pyproject.toml` | Add `influxdb3-python` dependency (keep `influxdb-client`) |
| `shared/src/idea_shared/feature_flags/flags.py` | Add `INFLUXDB_VERSION` flag + default |
| `shared/src/idea_shared/lib/Constants/PrivateConstants.py` | Add `INFLUX_DB_V3_*` env var reads |
| `shared/src/idea_shared/classes/IdeaHelsinkiRoadSegment.py` | Replace `FCDInfluxDBManager(...)` → `create_influxdb_manager(...)` (5 call sites) |
| `shared/src/idea_shared/threading/coordinator.py` | Replace constructor call (1 call site) |
| `shared/src/idea_shared/health/idea_checks.py` | Feature-flag health check classes |
| `shared/src/idea_shared/health/utils.py` | Refactor `check_backfill_mode()` |
| `services/fcd-manager/src/main.py` | Replace constructor calls (4 call sites) |
| `services/orchestrator/src/health_checks.py` | Feature-flag connection manager + health checks |
| `data/feature_flags.example.json` | Add `influxdb_version` flag |
| `k8s/secrets.yaml.tmpl` | Add `INFLUX_DB_V3_*` variables |

### 7.3 Unchanged Files

- `k8s/influxdb-deployment.yaml` — local v2 remains as fallback
- `services/orchestrator/src/main.py` — uses health checks, no direct InfluxDB instantiation
- `services/traffic-monitor/src/main.py` — doesn't use InfluxDB directly

---

## 8. Implementation Phases

### Phase 1: Foundation

- [ ] Add `influxdb3-python` to `shared/pyproject.toml` (alongside `influxdb-client`)
- [ ] Add `INFLUXDB_VERSION` to `FeatureFlag` enum and `FlagDefaults`
- [ ] Add `INFLUX_DB_V3_*` env vars to `PrivateConstants.py`
- [ ] Create `FCDInfluxDBManagerV3` with full public interface and SQL queries
- [ ] Create `influxdb_factory.py` with `create_influxdb_manager()`
- [ ] Write unit tests for `FCDInfluxDBManagerV3` (mock `InfluxDBClient3`)
- [ ] Update `data/feature_flags.example.json`

### Phase 2: Wire Up

- [ ] Replace all 13 `FCDInfluxDBManager(...)` call sites with `create_influxdb_manager(...)`
- [ ] Refactor `check_backfill_mode()` to work with both v2 and v3
- [ ] Feature-flag the health check classes
- [ ] Feature-flag `InfluxDBConnectionManager`
- [ ] Update `k8s/secrets.yaml.tmpl` with v3 env vars
- [ ] Run full test suite with flag=v2 (verify no regression)

### Phase 3: Validate

- [ ] Set up InfluxDB Cloud databases (`fcd-data`, `validation`)
- [ ] Set flag=v3 in local dev environment
- [ ] Reprocess FCD data from Azure into InfluxDB Cloud
- [ ] Validate all query results match expected output
- [ ] Run integration tests against InfluxDB Cloud
- [ ] Performance comparison (v2 local vs v3 Cloud)

### Phase 4: Cleanup (after v3 is stable)

- [ ] Remove `influxdb-client` from `pyproject.toml`
- [ ] Remove `FCDInfluxDBManager.py` (v2)
- [ ] Remove factory, make v3 the only implementation
- [ ] Remove `INFLUXDB_VERSION` feature flag
- [ ] Remove v2 env vars from `PrivateConstants.py` and secrets
- [ ] Remove local InfluxDB StatefulSet from k8s manifests
- [ ] Update `CLAUDE.md`

---

## 9. Testing Strategy

### 9.1 Unit Tests (both versions)

```
shared/tests/unit/
├── test_fcd_influxdb_manager.py       # Existing v2 tests (unchanged)
├── test_fcd_influxdb_manager_v3.py    # New v3 tests
└── test_influxdb_factory.py           # Factory flag-switching tests
```

- Mock `InfluxDBClient3` — verify SQL queries are constructed correctly
- Test parameterized query generation (no injection)
- Test DataFrame conversion roundtrip
- Test factory returns correct implementation based on flag
- Test error handling and retry behavior

### 9.2 Run Existing Tests with Flag = v2

After wiring up the factory, the entire existing test suite must pass with the default flag (`v2`). This proves the factory is transparent to callers.

```bash
# Must pass — proves no regression
FEATURE_FLAG_INFLUXDB_VERSION=v2 just test
```

### 9.3 Integration Tests (v3)

- Write/read roundtrip against real InfluxDB 3 (Cloud or local Docker)
- Validate data type preservation (int, float, str, bool, timestamp)
- Batch writing with 5000+ points
- Health check queries against live instance
- Test `check_backfill_mode()` with both fresh and stale data

---

## 10. Rollback Plan

Rollback is a single flag change at any point:

```bash
# Instant rollback — switch back to v2
FEATURE_FLAG_INFLUXDB_VERSION=v2
```

Or in `data/feature_flags.json`:
```json
{ "flags": { "influxdb_version": { "value": "v2" } } }
```

| Phase | Rollback action |
|-------|----------------|
| Phase 1 | Delete new files, revert `pyproject.toml` |
| Phase 2 | Set flag=v2 (or revert factory wiring) |
| Phase 3 | Set flag=v2 (local InfluxDB 2.7 still running) |
| Phase 4 | Not applicable (v2 code removed — this is the point of no return) |

**Phase 4 should only happen after v3 has been stable in production for a sufficient period.**

---

## Appendix A: Conceptual Changes Reference

### Data Model

| Concept | InfluxDB 2.7 | InfluxDB 3 |
|---------|-------------|------------|
| Data container | Bucket (within Org) | Database |
| Organization | Required | Removed |
| Measurement | Measurement | Table |
| Query language | Flux | SQL (primary), InfluxQL |
| Write protocol | Line Protocol v2 API | Line Protocol v3 API (v2 compat) |

### Authentication

| Aspect | InfluxDB 2.7 | InfluxDB 3 Cloud |
|--------|-------------|-----------------|
| Token scope | Org + bucket | Database-scoped |
| Auth header | `Token <token>` | `Bearer <token>` |
| CLI tool | `influx` | `influxdb3` |

---

## Sources

- [InfluxDB 3 Core Documentation](https://docs.influxdata.com/influxdb3/core/)
- [Migrate from InfluxDB v1 or v2](https://test2.docs.influxdata.com/influxdb3/enterprise/api/migrate-from-influxdb-v1-or-v2/)
- [influxdb3-python Client Library](https://github.com/InfluxCommunity/influxdb3-python)
- [Python Client Library Reference](https://docs.influxdata.com/influxdb3/core/reference/client-libraries/v3/python/)
- [InfluxDB 3 Core & Enterprise GA Announcement](https://www.influxdata.com/blog/influxdata-announces-influxdb-3-OSS-GA/)
- [InfluxDB Docker Hub](https://hub.docker.com/_/influxdb)
