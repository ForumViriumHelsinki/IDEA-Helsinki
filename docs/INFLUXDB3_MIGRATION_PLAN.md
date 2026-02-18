# InfluxDB 2.7 → 3 Migration Plan

## Executive Summary

Migrate IDEA-Helsinki from InfluxDB 2.7 (self-hosted, TSM engine, Flux) to **InfluxDB 3 Cloud** (managed, Apache Arrow + DataFusion + Parquet, SQL). The migration uses a **three-mode feature flag** with a **dual-write validation period**:

1. **`v2`** — current behavior (default, safe)
2. **`dual`** — writes to both v2 and v3, reads from v2, shadow-reads from v3 with comparison logging
3. **`v3`** — reads and writes v3 only (cutover)

This is the [Strangler Fig pattern](https://martinfowler.com/bliki/StranglerFigApplication.html) — the v3 system grows alongside v2 during dual-write, validated by shadow-read comparison, then v2 is removed once confidence is established.

**Data strategy**: Historical data will be reprocessed from Azure blob storage into InfluxDB Cloud. The local InfluxDB 2.7 StatefulSet remains as the trusted source during the dual-write period.

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
| Three-mode feature flag (`v2` / `dual` / `v3`) | Multi-region HA setup |
| Dual-write manager with shadow-read comparison | InfluxDB Cloud provisioning |
| Health check migration | Changes to Azure blob ingestion |
| New `FCDInfluxDBManagerV3` class | |
| New `DualWriteInfluxDBManager` class | |

---

## 1. Feature Flag Design

### 1.1 Three Migration Modes

| Mode | Writes | Reads | Shadow reads | Purpose |
|------|--------|-------|-------------|---------|
| **`v2`** (default) | v2 only | v2 | — | Current production behavior |
| **`dual`** | v2 + v3 | v2 | v3 (async, logged) | Validate v3 with real traffic |
| **`v3`** | v3 only | v3 | — | Full cutover |

**Dual mode** implements both dual-write and shadow-read:
- **Writes**: Every write goes to v2 first (blocking), then v3 (best-effort). A v3 write failure is logged but does **not** fail the operation — v2 remains the source of truth.
- **Reads**: All reads come from v2 (returned to caller). In the background, the same read is also executed against v3. Results are compared and discrepancies are logged with structured data for analysis.

### 1.2 Flag Definition

Add to `shared/src/idea_shared/feature_flags/flags.py`:

```python
class FeatureFlag(StrEnum):
    # ... existing flags ...

    # InfluxDB migration mode: "v2", "dual", or "v3"
    INFLUXDB_VERSION = "influxdb_version"
```

```python
class FlagDefaults:
    # ... existing defaults ...

    INFLUXDB_VERSION: str = "v2"  # Safe default: current behavior
```

### 1.3 Configuration

**JSON file** (`data/feature_flags.json`):
```json
{
  "flags": {
    "influxdb_version": {
      "value": "v2",
      "description": "InfluxDB migration mode: 'v2' (self-hosted only), 'dual' (write both, shadow-read), 'v3' (Cloud only)"
    }
  }
}
```

**Environment variable** (production):
```bash
# Migration progression:
FEATURE_FLAG_INFLUXDB_VERSION=v2    # Step 1: current behavior
FEATURE_FLAG_INFLUXDB_VERSION=dual  # Step 2: dual-write + shadow-read
FEATURE_FLAG_INFLUXDB_VERSION=v3    # Step 3: full cutover
```

### 1.4 New Environment Variables for v3

When the flag is set to `dual` or `v3`, the following env vars are read:

```bash
# InfluxDB 3 Cloud connection (used in dual and v3 modes)
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
│  (shared/classes/influxdb_factory)│
└───────────┬──────────────────────┘
            │
      ┌─────┼──────────┐
      ▼     ▼          ▼
┌────────┐ ┌─────────┐ ┌────────┐
│ v2     │ │ Dual    │ │ v3     │
│ (Flux) │ │ Write   │ │ (SQL)  │
└────────┘ └────┬────┘ └────────┘
               │
          ┌────┴────┐
          ▼         ▼
      ┌────────┐ ┌────────┐
      │ v2     │ │ v3     │   Dual mode delegates
      │ primary│ │ shadow │   to both implementations
      └────────┘ └────────┘
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

All three implementations (v2, dual, v3) return identical types. Callers don't change at all. The `DualWriteInfluxDBManager` is a decorator that composes v2 and v3 — it's invisible to callers.

### 2.3 Factory Function

```python
# shared/src/idea_shared/classes/influxdb_factory.py

import os
from idea_shared.feature_flags import get_feature_flags, FeatureFlag

def _create_v3_manager(bucket: str, token: str, timeout: int):
    """Create a v3 manager, mapping v2 bucket names to v3 database names."""
    from idea_shared.classes.FCDInfluxDBManagerV3 import FCDInfluxDBManagerV3

    host = os.getenv("INFLUX_DB_V3_HOST", "localhost:8181")
    v3_token = os.getenv("INFLUX_DB_V3_TOKEN", token)
    fcd_db = os.getenv("INFLUX_DB_V3_FCD_DATABASE", "fcd-data")
    val_db = os.getenv("INFLUX_DB_V3_VALIDATION_DATABASE", "validation")
    database = val_db if "validation" in bucket.lower() else fcd_db

    return FCDInfluxDBManagerV3(
        host=host, token=v3_token, database=database, timeout=timeout,
    )


def create_influxdb_manager(
    url: str,
    token: str,
    org: str,
    bucket: str,
    timeout: int = 300_000,
):
    """Create the appropriate InfluxDB manager based on feature flag.

    Callers pass the SAME arguments as today. The factory routes to
    the correct implementation:
      - "v2":   FCDInfluxDBManager (current behavior)
      - "dual": DualWriteInfluxDBManager (writes both, reads v2, shadow-reads v3)
      - "v3":   FCDInfluxDBManagerV3 (Cloud only)
    """
    flags = get_feature_flags()
    version = flags.get_string(FeatureFlag.INFLUXDB_VERSION, default="v2")

    if version == "v3":
        return _create_v3_manager(bucket, token, timeout)

    elif version == "dual":
        from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager
        from idea_shared.classes.DualWriteInfluxDBManager import DualWriteInfluxDBManager

        primary = FCDInfluxDBManager(
            url=url, token=token, org=org, bucket=bucket, timeout=timeout,
        )
        shadow = _create_v3_manager(bucket, token, timeout)

        return DualWriteInfluxDBManager(primary=primary, shadow=shadow)

    else:  # "v2" or any unknown value → safe default
        from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager

        return FCDInfluxDBManager(
            url=url, token=token, org=org, bucket=bucket, timeout=timeout,
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
├── DualWriteInfluxDBManager.py  # Dual-write + shadow-read decorator
└── influxdb_factory.py          # Factory function (reads feature flag)
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

## 4. `DualWriteInfluxDBManager` — Dual-Write + Shadow-Read

### 4.1 Design Principles

| Principle | Detail |
|-----------|--------|
| **v2 is always the source of truth** | All read results returned to callers come from v2 |
| **v3 write failures are non-fatal** | A v3 write error is logged but does not propagate to the caller |
| **Shadow reads are fire-and-forget** | v3 reads run in a background thread, results are compared and logged |
| **Structured comparison logging** | Discrepancies are logged with enough context to diagnose (method, args, v2 result, v3 result, diff) |
| **No performance impact on the hot path** | v3 operations never block the caller beyond the v2 operation time |

### 4.2 Implementation

```python
# shared/src/idea_shared/classes/DualWriteInfluxDBManager.py

import concurrent.futures
import pandas as pd
from datetime import datetime

from idea_shared.classes.Logger import Logger

# Thread pool for shadow operations — bounded to prevent resource exhaustion
_shadow_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="influxdb-shadow"
)


class DualWriteInfluxDBManager:
    """Dual-write + shadow-read decorator for InfluxDB migration.

    Wraps a primary (v2) and shadow (v3) manager. All operations use
    the primary as the source of truth. Writes are replicated to the
    shadow. Reads are shadow-executed in a background thread and results
    are compared and logged.

    Implements the same public interface as FCDInfluxDBManager.
    """

    def __init__(self, primary, shadow):
        self.primary = primary
        self.shadow = shadow
        self.logger = Logger(__name__)
        self.logger.info(
            "DualWriteInfluxDBManager initialized "
            f"(primary={type(primary).__name__}, shadow={type(shadow).__name__})"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ── Writes: primary (blocking) + shadow (best-effort) ──────────

    def write_dataframe(
        self, df: pd.DataFrame, segment_id: str,
        measurement_name: str, batch_size: int = 5000,
    ):
        """Write to primary, then replicate to shadow (non-blocking)."""
        # Primary write — must succeed
        self.primary.write_dataframe(df, segment_id, measurement_name, batch_size)

        # Shadow write — best-effort, log failures
        self._shadow_write(
            "write_dataframe", df=df, segment_id=segment_id,
            measurement_name=measurement_name, batch_size=batch_size,
        )

    def write_fcd_model(self, fcd_data: dict, batch_size: int = 5000):
        """Write to primary, then replicate to shadow (non-blocking)."""
        self.primary.write_fcd_model(fcd_data, batch_size)
        self._shadow_write(
            "write_fcd_model", fcd_data=fcd_data, batch_size=batch_size,
        )

    def _shadow_write(self, method_name: str, **kwargs):
        """Execute a write on the shadow manager, logging any failure."""
        try:
            getattr(self.shadow, method_name)(**kwargs)
            self.logger.debug(f"Shadow write succeeded: {method_name}")
        except Exception as e:
            self.logger.warning(
                f"Shadow write failed (non-fatal): {method_name} — {e}",
                extra={"method": method_name, "error": str(e)},
            )

    # ── Reads: primary (returned) + shadow (async comparison) ──────

    def get_last_update_timestamp(self, search_all: bool = False) -> datetime | None:
        result = self.primary.get_last_update_timestamp(search_all)
        self._shadow_read_compare(
            "get_last_update_timestamp", result, search_all=search_all,
        )
        return result

    def get_segment_update_timestamp(self, segment_id, measurement_name,
                                      first_or_last, interval_minutes=None):
        result = self.primary.get_segment_update_timestamp(
            segment_id, measurement_name, first_or_last, interval_minutes,
        )
        self._shadow_read_compare(
            "get_segment_update_timestamp", result,
            segment_id=segment_id, measurement_name=measurement_name,
            first_or_last=first_or_last, interval_minutes=interval_minutes,
        )
        return result

    def get_last_segment_update_timestamp(self, segment_id, measurement_name,
                                           interval_minutes=None):
        result = self.primary.get_last_segment_update_timestamp(
            segment_id, measurement_name, interval_minutes,
        )
        self._shadow_read_compare(
            "get_last_segment_update_timestamp", result,
            segment_id=segment_id, measurement_name=measurement_name,
            interval_minutes=interval_minutes,
        )
        return result

    def get_first_segment_update_timestamp(self, segment_id, measurement_name,
                                            interval_minutes=None):
        result = self.primary.get_first_segment_update_timestamp(
            segment_id, measurement_name, interval_minutes,
        )
        self._shadow_read_compare(
            "get_first_segment_update_timestamp", result,
            segment_id=segment_id, measurement_name=measurement_name,
            interval_minutes=interval_minutes,
        )
        return result

    def get_segment_data_dataframe(self, segment_id, measurement_name,
                                    start_time=None, end_time=None,
                                    latest_only=False, query_fields=None,
                                    interval_minutes=None):
        result = self.primary.get_segment_data_dataframe(
            segment_id, measurement_name, start_time, end_time,
            latest_only, query_fields, interval_minutes,
        )
        self._shadow_read_compare(
            "get_segment_data_dataframe", result,
            segment_id=segment_id, measurement_name=measurement_name,
            start_time=start_time, end_time=end_time,
            latest_only=latest_only, query_fields=query_fields,
            interval_minutes=interval_minutes,
        )
        return result

    def get_segment_data_csv(self, segment_id, measurement_name,
                              start_time=None, end_time=None,
                              latest_only=False, query_fields=None,
                              interval_minutes=None):
        result = self.primary.get_segment_data_csv(
            segment_id, measurement_name, start_time, end_time,
            latest_only, query_fields, interval_minutes,
        )
        self._shadow_read_compare(
            "get_segment_data_csv", result,
            segment_id=segment_id, measurement_name=measurement_name,
            start_time=start_time, end_time=end_time,
            latest_only=latest_only, query_fields=query_fields,
            interval_minutes=interval_minutes,
        )
        return result

    # ── Shadow read comparison engine ──────────────────────────────

    def _shadow_read_compare(self, method_name: str, primary_result, **kwargs):
        """Fire-and-forget: execute the same read on shadow, compare results."""

        def _compare():
            try:
                shadow_result = getattr(self.shadow, method_name)(**kwargs)
                self._log_comparison(method_name, kwargs, primary_result, shadow_result)
            except Exception as e:
                self.logger.warning(
                    f"Shadow read failed: {method_name} — {e}",
                    extra={"method": method_name, "error": str(e)},
                )

        _shadow_executor.submit(_compare)

    def _log_comparison(self, method_name, kwargs, primary_result, shadow_result):
        """Compare primary and shadow results, log discrepancies."""
        match = False

        if primary_result is None and shadow_result is None:
            match = True
        elif isinstance(primary_result, pd.DataFrame) and isinstance(shadow_result, pd.DataFrame):
            # DataFrame comparison: check shape and values
            if primary_result.shape == shadow_result.shape:
                try:
                    match = primary_result.equals(shadow_result)
                except Exception:
                    match = False
        elif isinstance(primary_result, datetime) and isinstance(shadow_result, datetime):
            # Allow 1-second tolerance for timestamp comparison
            match = abs((primary_result - shadow_result).total_seconds()) < 1.0
        elif isinstance(primary_result, str) and isinstance(shadow_result, str):
            match = primary_result == shadow_result
        else:
            match = primary_result == shadow_result

        if match:
            self.logger.debug(f"Shadow read match: {method_name}")
        else:
            # Structured log for analysis — grep "SHADOW_MISMATCH" to find all
            self.logger.warning(
                f"SHADOW_MISMATCH: {method_name}",
                extra={
                    "method": method_name,
                    "kwargs": str(kwargs),
                    "primary_type": type(primary_result).__name__,
                    "shadow_type": type(shadow_result).__name__,
                    "primary_summary": _summarize(primary_result),
                    "shadow_summary": _summarize(shadow_result),
                },
            )

    # ── Delegation ─────────────────────────────────────────────────

    def check_connection(self) -> bool:
        """Check primary connection (shadow connectivity is best-effort)."""
        primary_ok = self.primary.check_connection()
        shadow_ok = self.shadow.check_connection()
        if not shadow_ok:
            self.logger.warning("Shadow InfluxDB connection check failed (non-fatal)")
        return primary_ok

    def close(self):
        self.primary.close()
        try:
            self.shadow.close()
        except Exception as e:
            self.logger.warning(f"Shadow close failed (non-fatal): {e}")


def _summarize(value) -> str:
    """Create a short summary of a result for logging."""
    if value is None:
        return "None"
    if isinstance(value, pd.DataFrame):
        return f"DataFrame(shape={value.shape})"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and len(value) > 100:
        return f"str(len={len(value)})"
    return str(value)
```

### 4.3 Shadow Read Behavior Details

**Threading model**: Shadow reads use a bounded `ThreadPoolExecutor(max_workers=2)`. This is intentionally small — shadow reads are observational, not critical. If the pool is saturated, new shadow reads are queued rather than spawning unbounded threads.

**Why threads (not async)?** The callers in `IdeaHelsinkiRoadSegment` already use `asyncio.to_thread()` to call the synchronous InfluxDB manager. Adding another async layer inside the manager would create complexity. A simple thread pool is transparent to both sync and async callers.

**Comparison tolerance**:
- **Timestamps**: 1-second tolerance (clock differences between v2 local and v3 Cloud)
- **DataFrames**: Exact shape + value comparison via `pandas.DataFrame.equals()`
- **CSV strings**: Exact string match
- **None values**: Both None = match

**Log analysis**: All mismatches are tagged `SHADOW_MISMATCH`. To review:

```bash
# Find all mismatches
grep "SHADOW_MISMATCH" /var/log/idea-helsinki/*.log

# Count mismatches by method
grep "SHADOW_MISMATCH" /var/log/idea-helsinki/*.log | sort | uniq -c | sort -rn
```

### 4.4 Performance Impact

| Operation | v2 mode | Dual mode | Overhead |
|-----------|---------|-----------|----------|
| Write (blocking) | v2 write | v2 write + v3 write (sequential) | v3 write time added |
| Read (returned) | v2 read | v2 read (returned immediately) | None |
| Shadow read | — | v3 read (background thread) | None to caller |
| Connection check | v2 ping | v2 ping + v3 ping | v3 ping time added |

The only caller-visible overhead is on **writes** (v3 write is sequential after v2 to keep things simple) and **connection checks**. All reads return at v2 speed.

> **Note**: If the v3 write latency becomes a concern (e.g., network round-trip to Cloud), the `_shadow_write` can be moved to the thread pool to make writes fully non-blocking on the v3 side. This is a one-line change.

---

## 5. Query Migration — Flux → SQL (unchanged from previous plan)

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

## 6. Write Migration

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

## 7. Health Check Migration

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

## 8. Files Requiring Changes

### 8.1 New Files

| File | Purpose |
|------|---------|
| `shared/src/idea_shared/classes/FCDInfluxDBManagerV3.py` | v3 implementation with SQL queries |
| `shared/src/idea_shared/classes/DualWriteInfluxDBManager.py` | Dual-write + shadow-read decorator |
| `shared/src/idea_shared/classes/influxdb_factory.py` | Factory function reading feature flag |
| `shared/tests/unit/test_fcd_influxdb_manager_v3.py` | Unit tests for v3 manager |
| `shared/tests/unit/test_dual_write_influxdb_manager.py` | Unit tests for dual-write behavior |
| `shared/tests/unit/test_influxdb_factory.py` | Factory flag-switching tests |

### 8.2 Modified Files

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

### 8.3 Unchanged Files

- `k8s/influxdb-deployment.yaml` — local v2 remains as fallback
- `services/orchestrator/src/main.py` — uses health checks, no direct InfluxDB instantiation
- `services/traffic-monitor/src/main.py` — doesn't use InfluxDB directly

---

## 9. Implementation Phases

### Phase 1: Foundation (flag = `v2`, no production impact)

- [ ] Add `influxdb3-python` to `shared/pyproject.toml` (alongside `influxdb-client`)
- [ ] Add `INFLUXDB_VERSION` to `FeatureFlag` enum and `FlagDefaults`
- [ ] Add `INFLUX_DB_V3_*` env vars to `PrivateConstants.py`
- [ ] Create `FCDInfluxDBManagerV3` with full public interface and SQL queries
- [ ] Create `DualWriteInfluxDBManager` with shadow-read comparison
- [ ] Create `influxdb_factory.py` with three-mode routing
- [ ] Write unit tests for all three new classes
- [ ] Update `data/feature_flags.example.json`

### Phase 2: Wire Up (flag = `v2`, no production impact)

- [ ] Replace all 13 `FCDInfluxDBManager(...)` call sites with `create_influxdb_manager(...)`
- [ ] Refactor `check_backfill_mode()` to work with both v2 and v3
- [ ] Feature-flag the health check classes
- [ ] Feature-flag `InfluxDBConnectionManager`
- [ ] Update `k8s/secrets.yaml.tmpl` with v3 env vars
- [ ] Run full test suite with flag=v2 (verify no regression)

### Phase 3: Dual-Write Validation (flag = `dual`)

- [ ] Set up InfluxDB Cloud databases (`fcd-data`, `validation`)
- [ ] Configure `INFLUX_DB_V3_*` env vars pointing to Cloud
- [ ] Reprocess historical FCD data from Azure into InfluxDB Cloud
- [ ] Set flag=`dual` — production writes go to both, reads from v2
- [ ] Monitor `SHADOW_MISMATCH` logs for read comparison discrepancies
- [ ] Investigate and fix any mismatches between v2 and v3 results
- [ ] Run dual mode for sufficient period to build confidence (target: all query patterns exercised with 0 mismatches)

### Phase 4: Cutover (flag = `v3`)

- [ ] Set flag=`v3` — all reads and writes go to InfluxDB Cloud
- [ ] Monitor for errors, verify all services healthy
- [ ] Keep v2 running but idle as rollback safety net
- [ ] After stable period, proceed to cleanup

### Phase 5: Cleanup (after v3 is stable in production)

- [ ] Remove `influxdb-client` from `pyproject.toml`
- [ ] Remove `FCDInfluxDBManager.py` (v2)
- [ ] Remove `DualWriteInfluxDBManager.py`
- [ ] Remove factory, make v3 the only implementation
- [ ] Remove `INFLUXDB_VERSION` feature flag
- [ ] Remove v2 env vars from `PrivateConstants.py` and secrets
- [ ] Remove local InfluxDB StatefulSet from k8s manifests
- [ ] Update `CLAUDE.md`

---

## 10. Testing Strategy

### 10.1 Unit Tests

```
shared/tests/unit/
├── test_fcd_influxdb_manager.py           # Existing v2 tests (unchanged)
├── test_fcd_influxdb_manager_v3.py        # New v3 tests
├── test_dual_write_influxdb_manager.py    # Dual-write + shadow-read tests
└── test_influxdb_factory.py               # Factory flag-switching tests
```

**v3 manager tests**:
- Mock `InfluxDBClient3` — verify SQL queries are constructed correctly
- Test parameterized query generation (no injection)
- Test DataFrame conversion roundtrip
- Test error handling and retry behavior

**Dual-write manager tests**:
- Verify writes go to both primary and shadow
- Verify shadow write failure does not propagate to caller
- Verify reads return primary result (not shadow)
- Verify shadow reads execute in background thread
- Verify `SHADOW_MISMATCH` logging when results differ
- Verify matching results produce debug log (not warning)
- Verify shadow `close()` failure does not propagate
- Test thread pool saturation behavior

**Factory tests**:
- Test factory returns `FCDInfluxDBManager` when flag=`v2`
- Test factory returns `DualWriteInfluxDBManager` when flag=`dual`
- Test factory returns `FCDInfluxDBManagerV3` when flag=`v3`
- Test factory defaults to v2 on unknown flag value

### 10.2 Run Existing Tests with Flag = v2

After wiring up the factory, the entire existing test suite must pass with the default flag (`v2`). This proves the factory is transparent to callers.

```bash
# Must pass — proves no regression
FEATURE_FLAG_INFLUXDB_VERSION=v2 just test
```

### 10.3 Integration Tests (v3 and dual mode)

- Write/read roundtrip against real InfluxDB 3 (Cloud or local Docker)
- Validate data type preservation (int, float, str, bool, timestamp)
- Batch writing with 5000+ points
- Health check queries against live instance
- Test `check_backfill_mode()` with both fresh and stale data
- Dual-write integration: verify data appears in both v2 and v3 after write
- Shadow-read integration: verify comparison runs and logs correctly

---

## 11. Rollback Plan

Rollback is a single flag change at any point:

```bash
# Instant rollback from dual → v2
FEATURE_FLAG_INFLUXDB_VERSION=v2

# Instant rollback from v3 → dual (if v2 data still fresh)
FEATURE_FLAG_INFLUXDB_VERSION=dual

# Instant rollback from v3 → v2 (if v2 data still fresh)
FEATURE_FLAG_INFLUXDB_VERSION=v2
```

Or in `data/feature_flags.json`:
```json
{ "flags": { "influxdb_version": { "value": "v2" } } }
```

| Phase | Flag | Rollback action |
|-------|------|----------------|
| Phase 1 | `v2` | Delete new files, revert `pyproject.toml` |
| Phase 2 | `v2` | Set flag=`v2` (or revert factory wiring) |
| Phase 3 | `dual` | Set flag=`v2` — v2 was receiving all writes, no data loss |
| Phase 4 | `v3` | Set flag=`dual` or `v2` — v2 still running, but data since cutover only in v3 |
| Phase 5 | — | Not applicable (v2 code removed — point of no return) |

**Key safety property of dual mode**: Since v2 receives all writes during Phase 3, rolling back to `v2` loses nothing. The v3 Cloud instance can be wiped and repopulated at any time.

**Phase 5 should only happen after v3 has been stable in production for a sufficient period.**

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
