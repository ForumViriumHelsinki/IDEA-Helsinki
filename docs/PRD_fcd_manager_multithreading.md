# Product Requirements Document: Multi-threaded FCD Manager

**Version:** 1.0
**Date:** 2025-10-15
**Status:** Draft
**Related Issue:** [#105](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/105)

## Executive Summary

This PRD outlines the implementation of multi-threaded processing capabilities in the FCD Manager service to significantly improve historical data backfill performance by leveraging multiple CPU cores.

## Problem Statement

### Current State
The fcd-manager service (`services/fcd-manager/src/main.py`) is single-threaded, processing FCD data from Azure blob storage to InfluxDB sequentially. This creates a significant performance bottleneck during historical data backfill operations.

**Current Architecture:**
- Single thread in `main()` function running continuous 5-minute update loop
- `initialize_database_update()` processes historical data day-by-day sequentially
- `update_fcd_database()` handles recent updates (< 24 hours) every 5 minutes
- `_process_and_update_blob_list()` downloads and processes blobs sequentially

**Performance Constraints:**
- Cannot utilize multiple CPU cores (current Kubernetes limit: 1500m)
- Historical backfill is slow despite available compute resources
- Single-threaded bottleneck in both blob downloading and data processing

### Impact
- Long startup times when catching up historical data
- Inefficient resource utilization
- Slow recovery from service outages
- Unable to scale processing with increased CPU allocation

## Goals and Non-Goals

### Goals
1. Implement multi-threaded architecture for parallel FCD data processing
2. Maintain real-time processing performance (5-minute update cycle)
3. Accelerate historical data backfill by 3-4x with 4 worker threads
4. Ensure thread-safe operations with no data loss or duplication
5. Make threading configurable and backwards-compatible

### Non-Goals
1. Rewriting the entire FCD processing logic
2. Changing the data model or InfluxDB schema
3. Modifying Azure blob storage access patterns
4. Implementing distributed processing across multiple pods

## Proposed Solution

### Architecture Overview

The solution introduces a **thread-coordinated architecture** with three main components:

#### 1. Real-time Processing Thread
- **Purpose:** Handle current/recent FCD data updates (< 24 hours old)
- **Function:** Runs the existing `update_fcd_database()` logic
- **Schedule:** Every 5 minutes (existing `FCD_UPDATE_FREQUENCY`)
- **Priority:** High - ensures low latency for validation workflows

#### 2. Historical Backfill Thread Pool
- **Purpose:** Process historical data in parallel during initialization
- **Strategy:** Process multiple day ranges concurrently
- **Workers:** Configurable thread count (default: 4)
- **Function:** Parallel execution of `initialize_database_update()` logic

#### 3. Thread Coordination System
- **Purpose:** Prevent duplicate processing and ensure data consistency
- **Components:**
  - Date range assignment queue
  - InfluxDB write lock/queue
  - Progress tracking with resume capability
  - Health monitoring per thread

### Threading Strategy

#### Initial Startup Flow
```
1. Start health server (existing, single thread)
2. Determine last update timestamp from InfluxDB
3. If historical backfill needed:
   a. Create date range queue (from last_update to today)
   b. Spawn N backfill worker threads
   c. Each thread:
      - Dequeues a date range
      - Downloads blobs for that range
      - Processes and aggregates data
      - Thread-safe write to InfluxDB
      - Reports progress
4. Simultaneously spawn real-time processing thread
5. Once backfill complete, backfill threads terminate
6. Real-time thread continues indefinitely
```

#### Date Range Assignment
```python
# Example: If last_update = 2025-09-01 and today = 2025-10-15
# Total days to process: 44 days

# Strategy: Divide into chunks for parallel processing
# With 4 workers:
# Worker 1: 2025-09-01 to 2025-09-11 (11 days)
# Worker 2: 2025-09-12 to 2025-09-22 (11 days)
# Worker 3: 2025-09-23 to 2025-10-03 (11 days)
# Worker 4: 2025-10-04 to 2025-10-15 (11 days)
```

### Thread Safety Requirements

#### 1. InfluxDB Write Coordination
**Problem:** `FCDInfluxDBManager.write_fcd_model()` uses SYNCHRONOUS writes but is not thread-safe for concurrent access.

**Solution Options:**
- **Option A (Preferred):** Use a thread-safe write queue
  - Dedicated writer thread consumes from queue
  - Worker threads produce write requests to queue
  - Single point of serialization for InfluxDB writes

- **Option B:** Use a threading lock
  - Shared lock across all threads
  - Lock acquired before `write_fcd_model()` calls
  - Simpler but less efficient

**Implementation:** Option A (write queue) for better performance

#### 2. Azure Blob Access
**Analysis:** The `AzureBlobContainerManager` uses Azure Storage SDK which is thread-safe for reads. No coordination needed.

#### 3. Segment Mapping Updates
**Problem:** `update_fcd_segment_mapping()` writes to local JSON files which must not be accessed concurrently.

**Solution:**
- Serialize segment mapping updates using a dedicated thread or lock
- Only the real-time thread performs segment mapping updates
- Backfill threads skip mapping updates (not needed for historical data)

#### 4. Health Check Updates
**Problem:** Health check objects are shared across threads.

**Solution:**
- Make health check methods thread-safe with internal locks
- Or use thread-local health tracking

### Configuration

New constants in `shared/src/idea_shared/lib/Constants/Constants.py`:

```python
# Multi-threading configuration
FCD_BACKFILL_WORKER_COUNT = 4  # Number of parallel backfill workers
FCD_BACKFILL_CHUNK_DAYS = 7    # Days per chunk for parallel processing
FCD_ENABLE_MULTITHREADING = True  # Feature flag
```

## Technical Implementation Plan

### Phase 1: Thread Coordination Infrastructure (TDD)
**Files to create:**
- `shared/src/idea_shared/threading/coordinator.py` - Thread coordination system
- `shared/src/idea_shared/threading/write_queue.py` - Thread-safe InfluxDB write queue
- `shared/tests/test_threading_coordinator.py` - Unit tests
- `shared/tests/test_write_queue.py` - Unit tests

**Key Classes:**
```python
class DateRangeQueue:
    """Thread-safe queue for distributing date ranges to workers."""

class InfluxDBWriteQueue:
    """Thread-safe queue for coordinating InfluxDB writes."""

class BackfillCoordinator:
    """Coordinates multiple backfill worker threads."""
```

### Phase 2: Backfill Worker Thread (TDD)
**Files to modify:**
- `services/fcd-manager/src/main.py`

**New Functions:**
```python
def backfill_worker(
    date_queue: DateRangeQueue,
    write_queue: InfluxDBWriteQueue,
    azure_manager: AzureBlobContainerManager,
    worker_id: int
) -> None:
    """Worker thread function for processing historical date ranges."""

def create_date_range_chunks(
    start_date: datetime,
    end_date: datetime,
    chunk_days: int
) -> list:
    """Split date range into chunks for parallel processing."""
```

### Phase 3: Real-time Processing Thread (TDD)
**Files to modify:**
- `services/fcd-manager/src/main.py`

**New Functions:**
```python
def realtime_worker(
    azure_manager: AzureBlobContainerManager,
    write_queue: InfluxDBWriteQueue,
    shutdown_event: threading.Event
) -> None:
    """Worker thread for continuous real-time FCD updates."""
```

### Phase 4: Main Orchestration
**Files to modify:**
- `services/fcd-manager/src/main.py`

**Refactored `main()` function:**
```python
def main():
    # Initialize health server (existing)
    # Create Azure manager (existing)

    if FCD_ENABLE_MULTITHREADING:
        # Create coordination objects
        write_queue = InfluxDBWriteQueue(...)
        shutdown_event = threading.Event()

        # Start InfluxDB writer thread
        writer_thread = threading.Thread(target=influxdb_writer, args=(write_queue,))
        writer_thread.start()

        # Determine if backfill needed
        if backfill_needed:
            # Create date range chunks
            # Spawn backfill workers
            # Wait for backfill completion

        # Start real-time worker
        realtime_thread = threading.Thread(target=realtime_worker, args=(...))
        realtime_thread.start()

        # Wait for shutdown signal
        realtime_thread.join()
    else:
        # Existing single-threaded logic (backwards compatibility)
        # ...existing code...
```

### Phase 5: Testing & Validation

**Unit Tests:**
- Thread coordination logic
- Date range chunking
- Write queue operations
- Worker thread lifecycle

**Integration Tests:**
- Multi-threaded backfill with mock data
- Verify no duplicate timestamps
- Verify no missing timestamps
- Thread-safe InfluxDB writes

**Performance Tests:**
- Benchmark single-threaded vs multi-threaded
- Measure speedup with different worker counts
- Monitor memory usage during parallel processing

## Success Metrics

### Performance Metrics
- **Historical Backfill Speed:** 3-4x improvement with 4 workers
- **Real-time Processing:** Maintain < 5 minute update cycle
- **CPU Utilization:** 80%+ of allocated CPU during backfill
- **Memory Usage:** < 2x increase vs single-threaded

### Quality Metrics
- **Data Integrity:** Zero data loss or duplication
- **Test Coverage:** 90%+ coverage for threading code
- **Error Rate:** No increase in processing errors
- **Stability:** No thread deadlocks or race conditions

## Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Thread deadlocks | High | Low | Comprehensive testing, timeout mechanisms |
| Data duplication | High | Medium | Date range coordination, thorough integration tests |
| Increased memory usage | Medium | High | Chunked processing, memory monitoring |
| InfluxDB connection limits | Medium | Low | Connection pooling, write queue buffering |
| Regression in single-threaded mode | Medium | Low | Feature flag, maintain existing code paths |

## Dependencies

### Technical Dependencies
- Python threading module (standard library)
- queue module for thread-safe queues (standard library)
- Existing InfluxDB client (thread-safe for separate clients)
- Existing Azure SDK (thread-safe for reads)

### External Dependencies
- InfluxDB must handle concurrent writes (verified: yes)
- Azure blob storage must handle concurrent reads (verified: yes)
- Kubernetes resource limits must accommodate increased usage

## Testing Strategy

### Test-Driven Development Workflow

Following strict **RED-GREEN-REFACTOR**:

1. **RED Phase:**
   - Write failing test for thread coordination
   - Write failing test for write queue
   - Write failing test for backfill worker

2. **GREEN Phase:**
   - Implement minimal code to pass tests
   - Focus on correctness over optimization

3. **REFACTOR Phase:**
   - Optimize performance
   - Improve code structure
   - Ensure tests still pass

### Test Categories

**Unit Tests (fast, no external dependencies):**
```bash
pytest -m unit services/fcd-manager/tests/
pytest -m unit shared/tests/test_threading*
```

**Integration Tests (require InfluxDB, may be slower):**
```bash
pytest -m integration services/fcd-manager/tests/
```

**Performance Tests:**
```bash
pytest -m performance services/fcd-manager/tests/test_performance.py
```

## Rollout Plan

### Phase 1: Development & Testing (Week 1-2)
- Implement thread coordination infrastructure with TDD
- Unit tests for all threading components
- Integration tests with mock data

### Phase 2: Integration (Week 2-3)
- Integrate threading into fcd-manager main.py
- End-to-end testing in development environment
- Performance benchmarking

### Phase 3: Staging Deployment (Week 3)
- Deploy to staging with feature flag OFF
- Enable feature flag for controlled testing
- Monitor performance and stability

### Phase 4: Production Rollout (Week 4)
- Gradual rollout with feature flag
- Monitor metrics closely
- Rollback plan: Disable feature flag

## Open Questions

1. **InfluxDB connection pooling:** Should we create separate InfluxDB clients per thread or use a single client with a write queue?
   - **Recommendation:** Single write queue approach for simplicity

2. **Optimal worker count:** Should this be auto-detected based on CPU cores?
   - **Recommendation:** Start with fixed configuration, add auto-detection later

3. **Progress persistence:** Should we persist backfill progress to resume after crashes?
   - **Recommendation:** Phase 2 feature, not MVP

4. **Dynamic worker scaling:** Should worker count adjust based on load?
   - **Recommendation:** Phase 2 feature, not MVP

## Acceptance Criteria

- [ ] Multi-threaded processing implemented with configurable worker count
- [ ] Thread coordination prevents duplicate timeframe processing
- [ ] All existing tests pass
- [ ] New tests cover thread safety and coordination (90%+ coverage)
- [ ] Performance improvement measurable (3-4x with 4 threads)
- [ ] No data loss or duplication during parallel processing
- [ ] Documentation updated with threading architecture
- [ ] Configuration options documented
- [ ] Feature can be disabled via configuration flag
- [ ] Health checks work correctly with multi-threading

## References

- Issue: [#105 - Multi-threaded processing in fcd-manager](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/105)
- Podio Ticket: https://podio.com/fvh/iot-workspace/apps/datadev-kanban/items/800
- Testing Infrastructure: commits `fbef989` to `158f0a4`
- InfluxDB Python Client Docs: https://docs.influxdata.com/influxdb/cloud/api-guide/client-libraries/python/
- Python Threading Docs: https://docs.python.org/3/library/threading.html

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-15 | Claude Code | Initial PRD creation |
