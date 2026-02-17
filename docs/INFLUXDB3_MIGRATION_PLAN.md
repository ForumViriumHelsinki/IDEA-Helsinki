# InfluxDB 2.7 → 3 Migration Plan

## Executive Summary

This document outlines the migration plan for IDEA-Helsinki from InfluxDB 2.7 (TSM engine) to InfluxDB 3 Core/Enterprise (Apache Arrow + DataFusion + Parquet engine). The migration is a **breaking change** — InfluxDB 3 drops Flux entirely and replaces the v2 data model (buckets/organizations) with a simplified model (databases/tables).

### Why Migrate

- **Flux is deprecated**: InfluxDB 3 does not support Flux. All 12+ Flux queries in the codebase must be rewritten to SQL or InfluxQL.
- **Performance**: InfluxDB 3 eliminates series cardinality limits, offers sub-10ms last-value queries, and handles unlimited cardinality.
- **Docker tag change**: On **April 7, 2026**, the `latest` Docker tag will point to InfluxDB 3 Core. Our `influxdb:2.7-alpine` image pin protects us, but staying on 2.7 means no further updates.
- **Architecture**: InfluxDB 3 uses Apache Arrow, DataFusion, and Parquet — a modern columnar storage stack that replaces the TSM engine.

### Key Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Flux queries not translatable to SQL | High | Pre-map every Flux query before starting |
| Data loss during migration | High | Export all data before migration; run dual-write during transition |
| InfluxDB 3 Core lacks compaction | Medium | Evaluate Enterprise (free at-home tier available) |
| Client library incompatibility | Medium | `influxdb3-python` has different API surface than `influxdb-client` |
| Health check Flux queries break | High | Rewrite all health checks to use SQL/InfluxQL |

---

## 1. Conceptual Changes

### 1.1 Data Model

| Concept | InfluxDB 2.7 (Current) | InfluxDB 3 |
|---------|------------------------|------------|
| Data container | **Bucket** (within an Org) | **Database** |
| Organization | Required (`idea-helsinki`) | **Removed** |
| Measurement | Measurement | **Table** |
| Tag | Tag (indexed) | Tag column (string dictionary) |
| Field | Field | Column (typed) |
| Retention | Per-bucket | Per-database (optional) |
| Query language | **Flux** | **SQL** (primary), InfluxQL (compat) |
| Write protocol | Line Protocol via v2 API | Line Protocol via v3 API (v2 compat available) |

### 1.2 Authentication

| Aspect | InfluxDB 2.7 | InfluxDB 3 |
|--------|-------------|------------|
| Token model | Org-scoped tokens | Database-scoped tokens |
| Admin token | Operator token (setup wizard) | `_admin` operator token |
| CLI tool | `influx` | `influxdb3` |
| Auth header | `Token <token>` | `Bearer <token>` |

### 1.3 Client Library

| Aspect | Current (`influxdb-client`) | New (`influxdb3-python`) |
|--------|---------------------------|--------------------------|
| Package | `influxdb-client` | `influxdb3-python` |
| Import | `from influxdb_client import InfluxDBClient` | `from influxdb_client_3 import InfluxDBClient3` |
| Query API | `client.query_api().query(flux_query)` | `client.query(sql_query, mode="pandas")` |
| Query protocol | HTTP + Flux | Apache Arrow Flight + SQL |
| Write API | `client.write_api(write_options=SYNCHRONOUS)` | `client.write()` (synchronous by default) |
| DataFrame write | `write_api.write(record=df, data_frame_*)` | `client.write_dataframe(df, measurement, timestamp_column, tag_columns)` |
| Point write | `Point("m").tag("k","v").field("k",v)` | `Point("m").tag("k","v").field("k",v)` (same) |
| Connection params | `url`, `token`, `org` | `host`, `token`, `database` |
| Ping/health | `client.ping()` | HTTP `/health` endpoint |

### 1.4 Core vs Enterprise Decision

For IDEA-Helsinki, two options exist:

**InfluxDB 3 Core (OSS, MIT/Apache 2)**
- Single-node only
- No compaction (performance degrades over time with historical data)
- Best for recent data (last few days)
- Limitation: IDEA requires 6 months of FCD history for validation

**InfluxDB 3 Enterprise (commercial, free at-home tier)**
- Compaction engine (critical for 6-month historical queries)
- Historical query optimization
- High availability (multi-node)
- Single-series indexing

**Recommendation**: Start with **Enterprise (free at-home tier)** for development due to the 6-month FCD history requirement. Compaction is essential for querying historical data efficiently. Evaluate Core only if the data retention strategy changes.

---

## 2. Impact Assessment — Files Requiring Changes

### 2.1 Critical Path (Must Change)

| File | Changes Required |
|------|-----------------|
| `shared/pyproject.toml:21` | Replace `influxdb-client` with `influxdb3-python` dependency |
| `shared/src/idea_shared/classes/FCDInfluxDBManager.py` | **Complete rewrite**: new client, SQL queries, new write API |
| `shared/src/idea_shared/health/idea_checks.py` | Replace `InfluxDBClient` with `InfluxDBClient3`, rewrite Flux health queries |
| `shared/src/idea_shared/health/utils.py` | Rewrite `check_backfill_mode()` Flux queries to SQL |
| `shared/src/idea_shared/lib/Constants/PrivateConstants.py` | Remove `INFLUX_DB_ORG`, rename bucket vars to database vars |
| `services/orchestrator/src/health_checks.py` | Rewrite `InfluxDBConnectionManager`, `FCDDatabaseHealthCheck`, `ValidationDatabaseHealthCheck` |
| `k8s/influxdb-deployment.yaml` | New image, new init config, new env vars, remove org/bucket init |
| `k8s/secrets.yaml.tmpl` | Update variable names (bucket→database, remove org) |

### 2.2 Secondary Changes

| File | Changes Required |
|------|-----------------|
| `shared/src/idea_shared/classes/IdeaHelsinkiRoadSegment.py` | Update FCDInfluxDBManager usage (if constructor changes) |
| `shared/src/idea_shared/classes/IdeaHelsinkiManager.py` | Update InfluxDB initialization |
| `services/fcd-manager/src/main.py` | Update InfluxDB client initialization |
| `services/orchestrator/src/main.py` | Update InfluxDB client initialization |
| `shared/src/idea_shared/lib/Constants/Constants.py` | Update health check constant names if needed |
| `scripts/generate-secrets.sh` | Update env var names |
| `CLAUDE.md` | Update documentation references |
| All test files referencing InfluxDB | Update mocks and assertions |

---

## 3. Query Migration — Flux → SQL

### 3.1 Inventory of Flux Queries

Every Flux query in the codebase must be rewritten. Here is the complete mapping:

#### FCDInfluxDBManager.py Queries

**Query 1: Last update timestamp** (`get_last_update_timestamp`)
```flux
# CURRENT (Flux)
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

**Query 2: Segment timestamp (first/last)** (`get_segment_update_timestamp`)
```flux
# CURRENT (Flux)
from(bucket: "{bucket}")
  |> range(start: {range_start})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.segmentId == "{segment}")
  |> aggregateWindow(every: {interval}m, fn: last, createEmpty: false)
  |> {first_or_last}()
  |> keep(columns: ["_time"])
```
```sql
-- NEW (SQL) - last timestamp
SELECT max(time) as last_time
FROM "{measurement}"
WHERE "segmentId" = '{segment_id}'

-- NEW (SQL) - first timestamp
SELECT min(time) as first_time
FROM "{measurement}"
WHERE "segmentId" = '{segment_id}'

-- With interval aggregation (DATE_BIN replaces aggregateWindow)
SELECT max(time) as last_time
FROM "{measurement}"
WHERE "segmentId" = '{segment_id}'
GROUP BY DATE_BIN(INTERVAL '{interval} minutes', time)
ORDER BY last_time DESC
LIMIT 1
```

**Query 3: Segment data (CSV/DataFrame)** (`get_segment_data_csv` / `get_segment_data_dataframe`)
```flux
# CURRENT (Flux)
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
-- NEW (SQL)
-- Note: InfluxDB 3 stores data in columnar format natively,
-- no pivot needed. Fields are already columns.
SELECT time, speed, confidence
FROM "{measurement}"
WHERE "segmentId" = '{segment_id}'
  AND time >= '{start_time}'
  AND time <= '{end_time}'
ORDER BY time ASC

-- With interval aggregation
SELECT
  DATE_BIN(INTERVAL '{interval} minutes', time) as time_bin,
  LAST_VALUE(speed) as speed,
  LAST_VALUE(confidence) as confidence
FROM "{measurement}"
WHERE "segmentId" = '{segment_id}'
  AND time >= '{start_time}'
  AND time <= '{end_time}'
GROUP BY time_bin
ORDER BY time_bin ASC
```

#### Health Check Queries (utils.py, health_checks.py)

**Query 4: Recent data check** (`check_backfill_mode`)
```flux
# CURRENT (Flux)
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
FROM "{measurement}"
WHERE time >= now() - INTERVAL '{threshold} minutes'
LIMIT 1
```

**Query 5: Backfill lookback** (`check_backfill_mode`)
```flux
# CURRENT (Flux)
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
FROM "{measurement}"
WHERE time >= now() - INTERVAL '{days} days'
LIMIT 1
```

**Query 6: Validation data check** (`ValidationDatabaseHealthCheck`)
```flux
# CURRENT (Flux)
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

### 3.2 Query Safety

Current Flux queries use `_sanitize_flux_string()` to prevent injection. SQL queries should use **parameterized queries** instead:

```python
# Current (string interpolation with sanitization)
flux_query = f'... r.segmentId == "{_sanitize_flux_string(segment_id)}" ...'

# New (parameterized SQL via influxdb3-python)
sql = "SELECT * FROM segment_data WHERE segmentId = $segment_id"
result = client.query(sql, params={"segment_id": segment_id})
```

The `influxdb3-python` client supports parameterized queries natively, eliminating the need for manual sanitization.

---

## 4. Write Migration

### 4.1 Line Protocol (Unchanged)

InfluxDB 3 continues to accept Line Protocol for writes. The `Point` class API is identical:

```python
# This works in both v2 and v3
point = Point("segment_data").tag("segmentId", segment_id).time(dt_object)
point.field("speed", 42.5)
point.field("confidence", 0.95)
```

### 4.2 DataFrame Write

```python
# CURRENT (influxdb-client)
self.write_api.write(
    bucket=self.bucket,
    record=df,
    data_frame_measurement_name=measurement_name,
    data_frame_tag_columns=["segmentId"],
    data_frame_timestamp_column="time",
)

# NEW (influxdb3-python)
client.write_dataframe(
    df,
    measurement=measurement_name,
    timestamp_column="time",
    tag_columns=["segmentId"],
)
```

### 4.3 Write Retry Strategy

The current multi-layer retry strategy (urllib3 Retry + tenacity) needs adaptation:

- **urllib3 Retry**: Not applicable — `influxdb3-python` uses a different HTTP stack
- **tenacity retry**: Keep the application-level retry decorator, but update exception types
- **Batch writing**: `influxdb3-python` supports `WriteOptions` with built-in batching and retry

```python
# NEW: Built-in batch writing with retry
from influxdb_client_3 import WriteOptions, write_client_options

write_options = WriteOptions(
    batch_size=5000,
    flush_interval=10_000,
    retry_interval=5_000,
    max_retries=5,
    max_retry_delay=30_000,
    exponential_base=2,
)

wco = write_client_options(
    success_callback=on_success,
    error_callback=on_error,
    retry_callback=on_retry,
    write_options=write_options,
)

client = InfluxDBClient3(
    host="influxdb:8181",
    database="fcd-data",
    token="...",
    write_client_options=wco,
)
```

---

## 5. Infrastructure Migration

### 5.1 Kubernetes Deployment Changes

**Current** (`k8s/influxdb-deployment.yaml`):
```yaml
image: influxdb:2.7-alpine
env:
  - name: DOCKER_INFLUXDB_INIT_MODE
    value: "setup"
  - name: DOCKER_INFLUXDB_INIT_ORG
    value: "idea-helsinki"
  - name: DOCKER_INFLUXDB_INIT_BUCKET
    value: "fcd-data"
  - name: DOCKER_INFLUXDB_INIT_ADMIN_TOKEN
    value: "dev-token-changeme"
ports:
  - containerPort: 8086
volumeMounts:
  - mountPath: /var/lib/influxdb2
```

**New**:
```yaml
image: influxdb:3-core  # or influxdb:3-enterprise
# InfluxDB 3 does NOT use DOCKER_INFLUXDB_INIT_* env vars.
# Initialization is done via the influxdb3 CLI or HTTP API after startup.
# The server is stateless — data stored in object store or local Parquet.
ports:
  - containerPort: 8181  # Default HTTP port changed from 8086 to 8181
# No PVC needed for diskless mode (object store backed)
# For local Parquet storage:
volumeMounts:
  - mountPath: /var/lib/influxdb3
```

Key differences:
- **Port**: Default changes from `8086` to `8181`
- **Storage path**: `/var/lib/influxdb2` → `/var/lib/influxdb3`
- **Init process**: No `DOCKER_INFLUXDB_INIT_*` env vars. Use `influxdb3` CLI post-startup
- **StatefulSet → Deployment**: InfluxDB 3 can run stateless (object store backed), making a regular Deployment possible
- **Init script**: Replace `influx bucket create` with `influxdb3 create database` and `influxdb3 create token`

### 5.2 Database Initialization

```bash
# Replace init-buckets.sh content:
#!/bin/sh
set -e

echo "==> Waiting for InfluxDB 3 to start..."
sleep 5

# Create databases (replaces bucket creation)
influxdb3 create database fcd-data
influxdb3 create database validation --retention "0"

# Create admin token
influxdb3 create token \
  --description "IDEA Helsinki admin token" \
  --read-database fcd-data \
  --write-database fcd-data \
  --read-database validation \
  --write-database validation

echo "==> Initialization complete!"
echo "==> Available databases: fcd-data, validation"
```

### 5.3 Environment Variable Changes

```bash
# REMOVE these variables:
INFLUX_DB_ORG=idea-helsinki           # Organizations removed in v3

# RENAME these variables:
INFLUX_DB_FCD_BUCKET → INFLUX_DB_FCD_DATABASE
INFLUX_DB_VALIDATION_BUCKET → INFLUX_DB_VALIDATION_DATABASE

# UPDATE these variables:
INFLUX_DB_URL=http://influxdb:8181   # Port change: 8086 → 8181

# KEEP these variables (unchanged):
INFLUX_DB_FCD_TOKEN
INFLUX_DB_VALIDATION_TOKEN
```

### 5.4 Secrets Template Update

```yaml
# k8s/secrets.yaml.tmpl changes:
# Remove: INFLUX_DB_ORG
# Rename: INFLUX_DB_FCD_BUCKET → INFLUX_DB_FCD_DATABASE
# Rename: INFLUX_DB_VALIDATION_BUCKET → INFLUX_DB_VALIDATION_DATABASE
# Update: INFLUX_DB_URL default port from 8086 to 8181
```

---

## 6. Health Check Migration

### 6.1 Connection Check

```python
# CURRENT
client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
result = client.ping()

# NEW — influxdb3-python does not have a built-in ping()
# Use HTTP health endpoint instead
import httpx

async def check_health(host: str) -> bool:
    async with httpx.AsyncClient() as http_client:
        response = await http_client.get(f"http://{host}/health")
        return response.status_code == 200
```

### 6.2 InfluxDBConnectionManager

The current `InfluxDBConnectionManager` in `services/orchestrator/src/health_checks.py` manages `InfluxDBClient` instances. It needs to be rewritten for `InfluxDBClient3`:

```python
# Key change: InfluxDBClient3 uses host+database instead of url+org
# The connection manager should pool by host+database+token_hash
```

### 6.3 Query-based Health Checks

All health check queries (FCDDatabaseHealthCheck, ValidationDatabaseHealthCheck, check_backfill_mode) use Flux and must be rewritten to SQL as shown in Section 3.

---

## 7. Data Migration Strategy

### 7.1 Options

| Approach | Pros | Cons |
|----------|------|------|
| **Line Protocol export/import** | Simple, well-documented | Slow for large datasets |
| **Quix template** (Kafka-based sync) | Real-time sync, official partner | Complex setup, requires Kafka |
| **Historian** (Parquet-based) | Clean migration, queryable history | Community tool, less tested |
| **Dual-write period** | Zero downtime, gradual migration | Doubles write load temporarily |

### 7.2 Recommended Approach: Dual-Write + Backfill

1. **Deploy InfluxDB 3 alongside InfluxDB 2.7** (both running in k8s)
2. **Implement dual-write** in FCDInfluxDBManager — write to both databases
3. **Export historical data** from InfluxDB 2.7 using Line Protocol export
4. **Import historical data** into InfluxDB 3 databases
5. **Validate** data consistency between both instances
6. **Switch reads** from InfluxDB 2.7 to InfluxDB 3
7. **Decommission** InfluxDB 2.7

This approach ensures:
- No data loss
- Zero-downtime migration
- Ability to rollback at any point
- Historical data preserved

### 7.3 Historical Data Export

```bash
# Export from InfluxDB 2.7
influx query \
  'from(bucket: "fcd-data") |> range(start: 0)' \
  --raw > fcd-data-export.lp

# Import to InfluxDB 3
influxdb3 write \
  --database fcd-data \
  --file fcd-data-export.lp
```

---

## 8. Implementation Phases

### Phase 1: Preparation (No Production Changes)

- [ ] Set up InfluxDB 3 locally for development/testing
- [ ] Install `influxdb3-python` alongside `influxdb-client` (both can coexist)
- [ ] Write a prototype `FCDInfluxDBManagerV3` class with SQL queries
- [ ] Validate all query translations against test data
- [ ] Write integration tests for the new manager
- [ ] Document all Flux → SQL query equivalences with test cases

### Phase 2: Abstraction Layer

- [ ] Create `InfluxDBAdapter` interface abstracting v2/v3 differences
- [ ] Implement `InfluxDBV2Adapter` wrapping current `FCDInfluxDBManager`
- [ ] Implement `InfluxDBV3Adapter` using `influxdb3-python`
- [ ] Add feature flag `INFLUXDB_VERSION` to switch between adapters
- [ ] Update health checks to use the adapter pattern
- [ ] Run both adapters in parallel for validation

### Phase 3: Infrastructure

- [ ] Add InfluxDB 3 deployment to Kubernetes manifests
- [ ] Update secrets template with new env vars
- [ ] Create database initialization script for InfluxDB 3
- [ ] Deploy InfluxDB 3 alongside InfluxDB 2.7 in dev/staging
- [ ] Implement dual-write capability
- [ ] Export and import historical data

### Phase 4: Migration

- [ ] Switch reads to InfluxDB 3 (writes still dual)
- [ ] Validate data consistency and query correctness
- [ ] Monitor performance metrics
- [ ] Remove dual-write, write only to InfluxDB 3
- [ ] Remove InfluxDB 2.7 deployment
- [ ] Remove `influxdb-client` dependency
- [ ] Clean up adapter layer (remove v2 adapter)
- [ ] Update all documentation

### Phase 5: Cleanup

- [ ] Remove deprecated code (Flux sanitization, v2-specific retry logic)
- [ ] Update `CLAUDE.md` with new architecture details
- [ ] Update `k8s/secrets.yaml.tmpl`
- [ ] Update `scripts/generate-secrets.sh`
- [ ] Run full test suite
- [ ] Tag release

---

## 9. Testing Strategy

### 9.1 Unit Tests

- Mock `InfluxDBClient3` in all tests
- Verify SQL query construction (parameterized, no injection)
- Test DataFrame conversion with the new client
- Test error handling and retry behavior

### 9.2 Integration Tests

- Run InfluxDB 3 in Docker for integration tests
- Write/read roundtrip tests for all data patterns
- Validate data type preservation (int, float, str, bool)
- Test batch writing with 5000+ points
- Test health check queries against real InfluxDB 3

### 9.3 Migration Validation

- Compare query results between v2 and v3 for identical data
- Verify timestamp precision is preserved
- Validate tag/field semantics remain consistent
- Performance benchmarking (query latency, write throughput)

---

## 10. Rollback Plan

At each phase, rollback is straightforward:

- **Phase 1-2**: No production changes, nothing to rollback
- **Phase 3**: Remove InfluxDB 3 deployment, revert to InfluxDB 2.7 only
- **Phase 4**: Switch feature flag back to v2 adapter; InfluxDB 2.7 still has all data (dual-write ensures this)
- **Phase 5**: Revert the cleanup commit

The dual-write period in Phase 3-4 is the key safety net. Both databases contain identical data, so switching back is instant.

---

## Sources

- [InfluxDB 3 Core Documentation](https://docs.influxdata.com/influxdb3/core/)
- [InfluxDB 3 Enterprise Migration Guide](https://docs.influxdata.com/influxdb3/enterprise/get-started/)
- [Migrate from InfluxDB v1 or v2](https://test2.docs.influxdata.com/influxdb3/enterprise/api/migrate-from-influxdb-v1-or-v2/)
- [influxdb3-python Client Library](https://github.com/InfluxCommunity/influxdb3-python)
- [influxdb3-python on PyPI](https://pypi.org/project/influxdb3-python/)
- [Python Client Library Reference](https://docs.influxdata.com/influxdb3/core/reference/client-libraries/v3/python/)
- [The Future of Flux](https://docs.influxdata.com/flux/v0/future-of-flux/)
- [InfluxDB 3 Core & Enterprise GA Announcement](https://www.influxdata.com/blog/influxdata-announces-influxdb-3-OSS-GA/)
- [Quix Migration Tutorial](https://quix.io/docs/tutorials/influxdb-migration/overview.html)
- [Historian Migration Tool](https://cduser.com/how-to-migrate-influxdb-1-x-2-x-to-3-0-without-losing-your-history-introducing-historian/)
- [InfluxDB Docker Hub](https://hub.docker.com/_/influxdb)
