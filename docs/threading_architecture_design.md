# FCD Manager Multi-Threading Architecture Design

**Version:** 1.0
**Date:** 2025-10-15
**Related:** [PRD - Multi-threaded FCD Manager](./PRD_fcd_manager_multithreading.md)

## Overview

This document details the technical architecture for implementing multi-threaded processing in the FCD Manager service.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Main Thread                                 │
│  ┌────────────────┐                                                  │
│  │  Health Server │  (existing, runs in background)                  │
│  └────────────────┘                                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │           Thread Coordinator & Manager                          │ │
│  │  - Creates worker threads                                       │ │
│  │  - Manages shutdown                                             │ │
│  │  - Monitors health                                              │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Backfill        │  │  Backfill        │  │  Real-time       │
│  Worker Thread 1 │  │  Worker Thread N │  │  Worker Thread   │
│                  │  │                  │  │                  │
│ ┌──────────────┐ │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│ │Get date range│ │  │ │Get date range│ │  │ │5-min cycle   │ │
│ │from queue    │ │  │ │from queue    │ │  │ │Get recent    │ │
│ └──────┬───────┘ │  │ └──────┬───────┘ │  │ │blobs         │ │
│        │         │  │        │         │  │ └──────┬───────┘ │
│        ▼         │  │        ▼         │  │        │         │
│ ┌──────────────┐ │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│ │Download blobs│ │  │ │Download blobs│ │  │ │Download blobs│ │
│ │from Azure    │ │  │ │from Azure    │  │  │ │from Azure    │ │
│ └──────┬───────┘ │  │ └──────┬───────┘ │  │ └──────┬───────┘ │
│        │         │  │        │         │  │        │         │
│        ▼         │  │        ▼         │  │        ▼         │
│ ┌──────────────┐ │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│ │Process &     │ │  │ │Process &     │ │  │ │Process &     │ │
│ │aggregate data│ │  │ │aggregate data│ │  │ │aggregate data│ │
│ └──────┬───────┘ │  │ └──────┬───────┘ │  │ └──────┬───────┘ │
│        │         │  │        │         │  │        │         │
│        ▼         │  │        ▼         │  │        ▼         │
│ ┌──────────────┐ │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│ │Put to write  │ │  │ │Put to write  │ │  │ │Put to write  │ │
│ │queue         │ │  │ │queue         │ │  │ │queue +       │ │
│ └──────┬───────┘ │  │ └──────┬───────┘ │  │ │update mapping│ │
└────────┼─────────┘  └────────┼─────────┘  └────────┼─────────┘
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  InfluxDB Write Queue  │
                  │  (thread-safe Queue)   │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │   Writer Thread        │
                  │                        │
                  │ ┌────────────────────┐ │
                  │ │ Get from queue     │ │
                  │ └─────────┬──────────┘ │
                  │           ▼            │
                  │ ┌────────────────────┐ │
                  │ │Write to InfluxDB   │ │
                  │ │(FCDInfluxDBManager)│ │
                  │ └────────────────────┘ │
                  └────────────────────────┘
```

## Core Components

### 1. Date Range Queue

**Purpose:** Distribute historical date ranges to backfill worker threads

**Implementation:**
```python
from datetime import datetime, timedelta
from queue import Queue
from dataclasses import dataclass

@dataclass
class DateRange:
    """Represents a range of dates to process."""
    start: datetime
    end: datetime
    worker_id: int = 0  # For tracking which worker processes it

class DateRangeQueue:
    """Thread-safe queue for distributing date ranges to workers."""

    def __init__(self):
        self._queue = Queue()
        self._total_ranges = 0
        self._completed_ranges = 0
        self._lock = threading.Lock()

    def populate(self, start_date: datetime, end_date: datetime, chunk_days: int = 7):
        """
        Divide the date range into chunks and populate the queue.

        Args:
            start_date: Start of the overall date range
            end_date: End of the overall date range
            chunk_days: Size of each chunk in days
        """
        current = start_date
        range_count = 0

        while current <= end_date:
            chunk_end = min(current + timedelta(days=chunk_days), end_date)
            self._queue.put(DateRange(start=current, end=chunk_end))
            current = chunk_end + timedelta(days=1)
            range_count += 1

        with self._lock:
            self._total_ranges = range_count

    def get_next_range(self, timeout: float = 1.0) -> DateRange | None:
        """
        Get the next date range to process.

        Args:
            timeout: How long to wait for a range (seconds)

        Returns:
            DateRange or None if queue is empty
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def mark_completed(self):
        """Mark a range as completed."""
        with self._lock:
            self._completed_ranges += 1
        self._queue.task_done()

    def get_progress(self) -> tuple[int, int]:
        """
        Get progress information.

        Returns:
            (completed_ranges, total_ranges)
        """
        with self._lock:
            return (self._completed_ranges, self._total_ranges)

    def is_complete(self) -> bool:
        """Check if all ranges have been processed."""
        with self._lock:
            return self._completed_ranges >= self._total_ranges
```

### 2. InfluxDB Write Queue

**Purpose:** Coordinate thread-safe writes to InfluxDB using producer-consumer pattern

**Implementation:**
```python
from queue import Queue
from threading import Event
from dataclasses import dataclass

@dataclass
class WriteRequest:
    """Represents a request to write FCD data to InfluxDB."""
    fcd_data: dict
    worker_id: int
    timestamp: datetime

class InfluxDBWriteQueue:
    """Thread-safe queue for coordinating InfluxDB writes."""

    def __init__(self, max_queue_size: int = 100):
        """
        Initialize the write queue.

        Args:
            max_queue_size: Maximum number of write requests to buffer
        """
        self._queue = Queue(maxsize=max_queue_size)
        self._shutdown = Event()
        self._total_writes = 0
        self._failed_writes = 0
        self._lock = threading.Lock()

    def put_write_request(self, fcd_data: dict, worker_id: int, timeout: float = 10.0):
        """
        Add a write request to the queue.

        Args:
            fcd_data: FCD data dictionary to write
            worker_id: ID of the worker submitting this request
            timeout: How long to wait if queue is full (seconds)

        Raises:
            queue.Full: If queue is full and timeout expires
        """
        request = WriteRequest(
            fcd_data=fcd_data,
            worker_id=worker_id,
            timestamp=datetime.now(UTC)
        )
        self._queue.put(request, timeout=timeout)

    def get_next_request(self, timeout: float = 1.0) -> WriteRequest | None:
        """
        Get the next write request (called by writer thread).

        Args:
            timeout: How long to wait for a request (seconds)

        Returns:
            WriteRequest or None if timeout or shutdown
        """
        if self._shutdown.is_set():
            return None

        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def mark_completed(self, success: bool = True):
        """
        Mark a write request as completed.

        Args:
            success: Whether the write succeeded
        """
        with self._lock:
            self._total_writes += 1
            if not success:
                self._failed_writes += 1
        self._queue.task_done()

    def shutdown(self):
        """Signal shutdown to writer thread."""
        self._shutdown.set()

    def is_shutdown(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown.is_set()

    def get_stats(self) -> dict:
        """Get write statistics."""
        with self._lock:
            return {
                "total_writes": self._total_writes,
                "failed_writes": self._failed_writes,
                "queue_size": self._queue.qsize(),
            }
```

### 3. Thread Coordinator

**Purpose:** Manage lifecycle of all worker threads

**Implementation:**
```python
from threading import Thread, Event
import time

class ThreadCoordinator:
    """Coordinates multiple worker threads for FCD processing."""

    def __init__(
        self,
        num_backfill_workers: int,
        azure_manager,
        influx_config: dict,
        logger,
    ):
        """
        Initialize the thread coordinator.

        Args:
            num_backfill_workers: Number of backfill worker threads
            azure_manager: AzureBlobContainerManager instance
            influx_config: Dict with InfluxDB connection params
            logger: Logger instance
        """
        self.num_backfill_workers = num_backfill_workers
        self.azure_manager = azure_manager
        self.influx_config = influx_config
        self.logger = logger

        # Thread management
        self.date_queue = DateRangeQueue()
        self.write_queue = InfluxDBWriteQueue()
        self.shutdown_event = Event()

        # Thread references
        self.backfill_threads = []
        self.realtime_thread = None
        self.writer_thread = None

    def start_backfill(self, start_date: datetime, end_date: datetime, chunk_days: int = 7):
        """
        Start backfill workers for historical data processing.

        Args:
            start_date: Start of historical data range
            end_date: End of historical data range
            chunk_days: Days per chunk for parallel processing
        """
        self.logger.info(f"Starting backfill from {start_date.date()} to {end_date.date()}")

        # Populate date range queue
        self.date_queue.populate(start_date, end_date, chunk_days)

        # Start writer thread first
        self.writer_thread = Thread(
            target=self._influxdb_writer_worker,
            name="InfluxDB-Writer",
            daemon=False
        )
        self.writer_thread.start()

        # Start backfill workers
        for worker_id in range(self.num_backfill_workers):
            thread = Thread(
                target=self._backfill_worker,
                args=(worker_id,),
                name=f"Backfill-Worker-{worker_id}",
                daemon=False
            )
            thread.start()
            self.backfill_threads.append(thread)

        self.logger.info(f"Started {self.num_backfill_workers} backfill workers")

    def start_realtime(self):
        """Start the real-time processing thread."""
        self.realtime_thread = Thread(
            target=self._realtime_worker,
            name="Realtime-Worker",
            daemon=False
        )
        self.realtime_thread.start()
        self.logger.info("Started real-time worker")

    def wait_for_backfill_completion(self, timeout: float = None):
        """
        Wait for all backfill workers to complete.

        Args:
            timeout: Maximum time to wait (seconds), None for no timeout
        """
        start_time = time.time()

        for thread in self.backfill_threads:
            if timeout:
                elapsed = time.time() - start_time
                remaining = max(0, timeout - elapsed)
                thread.join(timeout=remaining)
            else:
                thread.join()

        self.logger.info("All backfill workers completed")

    def shutdown(self):
        """Gracefully shutdown all threads."""
        self.logger.info("Initiating coordinator shutdown...")

        # Signal shutdown
        self.shutdown_event.set()
        self.write_queue.shutdown()

        # Wait for backfill threads
        for thread in self.backfill_threads:
            thread.join(timeout=30)

        # Wait for realtime thread
        if self.realtime_thread:
            self.realtime_thread.join(timeout=30)

        # Wait for writer thread (after all producers done)
        if self.writer_thread:
            self.writer_thread.join(timeout=60)

        self.logger.info("Coordinator shutdown complete")

    def _backfill_worker(self, worker_id: int):
        """
        Worker thread function for processing historical date ranges.

        Args:
            worker_id: Unique identifier for this worker
        """
        self.logger.info(f"Backfill worker {worker_id} started")

        while not self.shutdown_event.is_set():
            # Get next date range
            date_range = self.date_queue.get_next_range(timeout=1.0)
            if date_range is None:
                # Queue is empty, we're done
                break

            date_range.worker_id = worker_id
            self.logger.info(
                f"Worker {worker_id} processing {date_range.start.date()} to {date_range.end.date()}"
            )

            try:
                # Process this date range (downloads, aggregates)
                fcd_data = self._process_date_range(date_range)

                if fcd_data:
                    # Submit to write queue
                    self.write_queue.put_write_request(fcd_data, worker_id)
                    self.logger.info(f"Worker {worker_id} submitted write request")

                # Mark as completed
                self.date_queue.mark_completed()

            except Exception as e:
                self.logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                self.date_queue.mark_completed()  # Mark as done even on error

        self.logger.info(f"Backfill worker {worker_id} finished")

    def _realtime_worker(self):
        """Worker thread for continuous real-time FCD updates."""
        self.logger.info("Real-time worker started")

        last_mapping_update = datetime.now(UTC)

        while not self.shutdown_event.is_set():
            try:
                current_time = datetime.now(UTC)

                # Determine if mapping should be updated
                update_mapping = (current_time - last_mapping_update) >= timedelta(
                    minutes=FCD_UPDATE_FREQUENCY
                )

                # Get recent blobs and process
                fcd_data = self._process_realtime_update(current_time)

                if fcd_data:
                    # Submit to write queue
                    self.write_queue.put_write_request(fcd_data, worker_id=-1)  # -1 for realtime

                    # Update segment mapping if needed
                    if update_mapping:
                        self._update_segment_mapping(fcd_data)
                        last_mapping_update = current_time

                # Sleep until next update cycle
                self._wait_for_next_cycle(current_time)

            except Exception as e:
                self.logger.error(f"Real-time worker error: {e}", exc_info=True)

        self.logger.info("Real-time worker finished")

    def _influxdb_writer_worker(self):
        """Dedicated writer thread for InfluxDB writes."""
        self.logger.info("InfluxDB writer thread started")

        with FCDInfluxDBManager(**self.influx_config) as manager:
            while not (self.write_queue.is_shutdown() and self.write_queue._queue.empty()):
                request = self.write_queue.get_next_request(timeout=1.0)

                if request is None:
                    continue

                try:
                    self.logger.info(
                        f"Writing data from worker {request.worker_id} to InfluxDB"
                    )
                    manager.write_fcd_model(request.fcd_data)
                    self.write_queue.mark_completed(success=True)

                except Exception as e:
                    self.logger.error(f"InfluxDB write failed: {e}", exc_info=True)
                    self.write_queue.mark_completed(success=False)

        self.logger.info("InfluxDB writer thread finished")

    def _process_date_range(self, date_range: DateRange) -> dict:
        """Process a date range and return aggregated FCD data."""
        # This will call the existing logic from initialize_database_update
        # Refactored into a reusable function
        pass  # Implementation in next phase

    def _process_realtime_update(self, current_time: datetime) -> dict:
        """Process real-time updates and return FCD data."""
        # This will call the existing logic from update_fcd_database
        # Refactored into a reusable function
        pass  # Implementation in next phase

    def _update_segment_mapping(self, fcd_data: dict):
        """Update segment mapping from FCD data."""
        # Calls existing update_fcd_segment_mapping
        pass  # Implementation in next phase

    def _wait_for_next_cycle(self, current_time: datetime):
        """Wait until the next update cycle."""
        # Existing pause logic
        pass  # Implementation in next phase
```

## Integration with Existing Code

### Modified main.py Structure

```python
def main():
    """Main entry point with optional multi-threading."""
    global health_server, update_cycle_check, pipeline_check

    # Setup signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Initialize health server (existing code)
    # ...

    # Create Azure manager
    azure_manager = AzureBlobContainerManager(...)

    # Check if multi-threading is enabled via feature flag
    flags = get_feature_flags()
    if flags.is_enabled(FeatureFlag.FCD_ENABLE_MULTITHREADING):
        run_multithreaded(azure_manager)
    else:
        run_singlethreaded(azure_manager)  # Existing logic

def run_multithreaded(azure_manager):
    """Run with multi-threading enabled."""
    logger.info("Starting FCD manager with multi-threading enabled")

    # Create coordinator
    coordinator = ThreadCoordinator(
        num_backfill_workers=FCD_BACKFILL_WORKER_COUNT,
        azure_manager=azure_manager,
        influx_config={
            "url": INFLUX_DB_URL,
            "token": INFLUX_DB_FCD_TOKEN,
            "org": INFLUX_DB_ORG,
            "bucket": INFLUX_DB_FCD_BUCKET,
        },
        logger=logger,
    )

    # Check if backfill is needed
    last_update = get_last_update_timestamp()
    if last_update is None or (datetime.now(UTC) - last_update).days > 0:
        coordinator.start_backfill(
            start_date=last_update or FCD_HISTORY_START_DATE,
            end_date=datetime.now(UTC),
            chunk_days=FCD_BACKFILL_CHUNK_DAYS
        )
        coordinator.wait_for_backfill_completion()

    # Start real-time processing
    coordinator.start_realtime()

    # Wait for shutdown signal
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        coordinator.shutdown()

def run_singlethreaded(azure_manager):
    """Run with existing single-threaded logic (backwards compatibility)."""
    # Existing main() logic here
    pass
```

## Thread Safety Analysis

### Thread-Safe Components
1. **queue.Queue:** Built-in thread-safe queue
2. **threading.Lock:** Used for protecting shared state
3. **threading.Event:** Used for signaling shutdown
4. **Azure SDK:** Thread-safe for concurrent reads

### Not Thread-Safe (Requires Coordination)
1. **FCDInfluxDBManager writes:** Protected by write queue pattern
2. **Segment mapping file updates:** Only done by real-time thread
3. **Health check state:** Protected by internal locks

## Error Handling

### Worker Thread Errors
- Catch and log exceptions within worker threads
- Mark work as completed even on error (prevents hangs)
- Continue processing remaining work

### Write Queue Errors
- Retry logic in writer thread
- Failed writes logged with full context
- Statistics tracking for monitoring

### Shutdown Handling
- Graceful shutdown with timeout
- Flush write queue before exit
- Join all threads with timeout

## Performance Considerations

### Memory Usage
- Limit write queue size to prevent unbounded growth
- Process data in chunks (existing batching)
- Release data after write completion

### CPU Usage
- Configurable worker count
- IO-bound tasks (most time in network waits)
- Minimal CPU contention expected

### Network
- Parallel Azure blob downloads
- InfluxDB writes serialized but batched
- Connection pooling handled by SDK

## Testing Strategy

### Unit Tests
- DateRangeQueue operations
- InfluxDBWriteQueue operations
- ThreadCoordinator lifecycle
- Progress tracking
- Shutdown handling

### Integration Tests
- Multi-threaded backfill with mock data
- Verify no duplicate timestamps
- Verify no missing data
- Thread safety under concurrent access

### Performance Tests
- Benchmark against single-threaded
- Test different worker counts
- Monitor resource usage

## Monitoring & Observability

### Metrics to Track
- Backfill progress (completed/total ranges)
- Write queue depth
- Write success/failure rates
- Per-worker statistics
- Thread health status

### Health Checks
- Extend existing health checks for threading
- Monitor for stuck threads
- Track write queue backlog

## Next Steps

1. Create shared threading module structure
2. Implement DateRangeQueue with TDD
3. Implement InfluxDBWriteQueue with TDD
4. Implement ThreadCoordinator with TDD
5. Integrate into main.py
6. Add configuration options
7. Testing and validation
8. Documentation updates

## Appendix: File Structure

```
IDEA-Helsinki/
├── shared/
│   └── src/
│       └── idea_shared/
│           ├── threading/             # NEW
│           │   ├── __init__.py
│           │   ├── date_queue.py     # DateRangeQueue
│           │   ├── write_queue.py    # InfluxDBWriteQueue
│           │   └── coordinator.py    # ThreadCoordinator
│           └── tests/
│               └── threading/         # NEW
│                   ├── test_date_queue.py
│                   ├── test_write_queue.py
│                   └── test_coordinator.py
└── services/
    └── fcd-manager/
        └── src/
            └── main.py                # MODIFIED
```
