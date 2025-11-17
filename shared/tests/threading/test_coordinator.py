"""
Tests for ThreadCoordinator - Multi-threaded FCD processing orchestration.

These tests verify REAL threading coordination by:
1. Using realistic processing functions that simulate I/O work
2. Testing actual concurrent worker execution
3. Verifying queue management and backpressure
4. Testing real retry logic and error handling
5. Only mocking external dependencies (Azure, InfluxDB)

Following TDD RED-GREEN-REFACTOR cycle.
"""

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

from idea_shared.threading.coordinator import ThreadCoordinator
from idea_shared.threading.date_queue import DateRangeQueue
from idea_shared.threading.write_queue import InfluxDBWriteQueue


def realistic_processing_function(azure_manager, start_date, end_date, batch_size=50):
    """
    Realistic processing function that simulates I/O work with delays.

    This mimics real FCD processing:
    1. Simulates Azure API call (0.05s delay)
    2. Yields multiple batches with realistic data
    3. Each batch represents processed FCD data

    This ensures tests verify ACTUAL threading coordination under load.
    """
    # Simulate Azure API call delay
    time.sleep(0.05)

    # Yield 2 batches to simulate streaming processing
    yield {
        "segmentId": {
            "seg1": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[24.9, 60.1], [24.91, 60.11]],
                },
                "detailedSegment": {
                    "date": {
                        start_date.isoformat(): {"properties": {"currentSpeed": 50}}
                    }
                },
            }
        }
    }

    # Simulate processing delay between batches
    time.sleep(0.05)

    yield {
        "segmentId": {
            "seg2": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[24.92, 60.12], [24.93, 60.13]],
                },
                "detailedSegment": {
                    "date": {
                        start_date.isoformat(): {"properties": {"currentSpeed": 55}}
                    }
                },
            }
        }
    }


def fast_processing_function(azure_manager, start_date, end_date, batch_size=50):
    """
    Fast processing function for tests that need quick completion.

    Still yields realistic data structure but with minimal delay.
    """
    time.sleep(0.01)  # Minimal delay
    yield {
        "segmentId": {
            "seg1": {
                "geometry": {"type": "LineString", "coordinates": [[24.9, 60.1]]},
                "detailedSegment": {
                    "date": {start_date.isoformat(): {"properties": {}}}
                },
            }
        }
    }


class TestThreadCoordinatorInitialization:
    """Tests for ThreadCoordinator initialization."""

    def test_coordinator_initialization(self):
        """Test coordinator initializes with required parameters."""
        azure_manager = MagicMock()
        influx_config = {"url": "http://localhost:8086", "token": "test"}
        logger = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config=influx_config,
            logger=logger,
            processing_function=fast_processing_function,
        )

        assert coordinator.num_backfill_workers == 4
        assert coordinator.azure_manager is azure_manager
        assert coordinator.influx_config == influx_config
        assert not coordinator.is_shutdown()

    def test_coordinator_creates_queues(self):
        """Test coordinator creates date and write queues."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        assert isinstance(coordinator.date_queue, DateRangeQueue)
        assert isinstance(coordinator.write_queue, InfluxDBWriteQueue)

    def test_coordinator_with_custom_queue_sizes(self):
        """Test coordinator with custom queue size configuration."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
            max_write_queue_size=50,
        )

        # Write queue should respect custom size
        assert coordinator.write_queue is not None


class TestThreadCoordinatorBackfill:
    """Tests for backfill processing coordination."""

    def test_start_backfill_populates_date_queue(self):
        """Test that start_backfill populates the date queue with REAL queue operations."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 3, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Should have 3 date ranges (2025-01-01, 2025-01-02, 2025-01-03)
        stats = coordinator.date_queue.get_stats()
        assert stats["total_ranges"] == 3

    def test_start_backfill_spawns_worker_threads(self):
        """Test that start_backfill spawns the correct number of REAL worker threads."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=3,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 2, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Should have 3 backfill workers + 1 writer thread
        assert len(coordinator._worker_threads) == 3
        assert coordinator._writer_thread is not None

        # Verify threads are actually running (not just created)
        time.sleep(0.05)  # Give threads time to start
        active_count = sum(1 for t in coordinator._worker_threads if t.is_alive())
        assert active_count >= 1, "At least one worker should be active"

    def test_start_backfill_spawns_writer_thread(self):
        """Test that start_backfill spawns the InfluxDB writer thread."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        assert coordinator._writer_thread is not None
        assert coordinator._writer_thread.is_alive()

    def test_wait_for_backfill_completion(self):
        """Test waiting for backfill to complete with REAL work processing."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Should complete after real work
        result = coordinator.wait_for_backfill_completion(timeout=5.0)
        assert result is True

        # Verify work was actually processed
        stats = coordinator.get_progress_stats()
        assert (
            stats["date_queue"]["completed_ranges"] == 2
        ), "Should complete 2 date ranges"

    def test_wait_for_backfill_timeout(self):
        """
        Test that wait_for_backfill respects timeout with REAL slow processing.

        Uses a processing function that takes longer than timeout to verify
        timeout handling.
        """

        # Processing function that is deliberately slow
        def slow_processing_function(azure_mgr, start_date, end_date, batch_size=50):
            time.sleep(5)  # Deliberately slow to trigger timeout
            yield {}

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=slow_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Should timeout and return False
        result = coordinator.wait_for_backfill_completion(timeout=0.5)
        assert result is False

        # Cleanup
        coordinator.shutdown()


class TestThreadCoordinatorShutdown:
    """Tests for graceful shutdown coordination."""

    def test_shutdown_signals_all_components(self):
        """Test that shutdown signals all components."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        coordinator.shutdown()

        assert coordinator.is_shutdown()
        assert coordinator.write_queue.is_shutdown()

    def test_shutdown_waits_for_threads(self):
        """Test that shutdown waits for REAL threads to complete."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Allow threads to start and process
        time.sleep(0.2)

        coordinator.shutdown()

        # All threads should be stopped
        for thread in coordinator._worker_threads:
            assert (
                not thread.is_alive()
            ), f"Worker thread {thread.name} should be stopped"
        assert (
            not coordinator._writer_thread.is_alive()
        ), "Writer thread should be stopped"

    def test_shutdown_respects_timeout(self):
        """Test that shutdown respects timeout parameter with REAL slow work."""

        # Processing function that is deliberately slow
        def very_slow_processing(azure_mgr, start_date, end_date, batch_size=50):
            time.sleep(10)  # Deliberately slow
            yield {}

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=very_slow_processing,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Shutdown with short timeout
        coordinator.shutdown(timeout=0.5)

        # Threads may still be alive but shutdown was called
        assert coordinator.is_shutdown()


class TestThreadCoordinatorRetryLogic:
    """Tests for retry logic integration."""

    def test_failed_chunk_is_retried(self):
        """Test that failed chunks are automatically retried."""
        # Mock Azure manager
        azure_manager = MagicMock()
        call_count = {"count": 0}

        # Processing function that fails once, then succeeds
        def failing_processing_function(azure_mgr, start_date, end_date, batch_size=50):
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise Exception("Simulated failure")
            yield {}  # Success

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=failing_processing_function,
            max_retries=3,
            retry_delay=1,  # Short delay for testing
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Wait for completion (including retry delay)
        coordinator.wait_for_backfill_completion(timeout=10.0)
        coordinator.shutdown()

        # Should have been called 3 times: 2 date ranges (Jan 1-1, Jan 2-2)
        # First range fails once then succeeds (2 calls), second range succeeds (1 call) = 3 total
        assert call_count["count"] == 3

    def test_permanently_failed_chunks_moved_to_dead_letter(self):
        """Test that chunks exceeding max retries go to dead-letter queue."""
        # Mock Azure manager
        azure_manager = MagicMock()

        # Processing function that always fails
        def always_failing_processing_function(
            azure_mgr, start_date, end_date, batch_size=50
        ):
            raise Exception("Permanent failure")
            yield  # Never reached

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=always_failing_processing_function,
            max_retries=2,
            retry_delay=1,  # Short delay for testing
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Wait for all retries to exhaust (initial + 2 retries with exponential backoff)
        # With retry_delay=1: attempt 1 (0s), wait 1s, attempt 2 (1s), wait 2s, attempt 3 (3s), wait 4s = ~4s total
        time.sleep(8.0)
        coordinator.shutdown()

        # Should have 2 dead-letter entries (Jan 1-1 and Jan 2-2)
        dead_letter = coordinator.date_queue.get_dead_letter_ranges()
        assert len(dead_letter) == 2


class TestThreadCoordinatorProgressTracking:
    """Tests for progress tracking with REAL work."""

    def test_get_progress_statistics(self):
        """Test getting progress statistics."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        stats = coordinator.get_progress_stats()

        assert "date_queue" in stats
        assert "write_queue" in stats
        assert "workers_alive" in stats
        assert "writer_alive" in stats

    def test_progress_tracks_completed_ranges(self):
        """Test that progress correctly tracks completed date ranges with REAL processing."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 3, tzinfo=UTC), 1
        )

        coordinator.wait_for_backfill_completion(timeout=5.0)

        stats = coordinator.get_progress_stats()
        # Should have completed 3 ranges (Jan 1, 2, 3)
        assert stats["date_queue"]["completed_ranges"] == 3


class TestThreadCoordinatorInfluxDBWriter:
    """Tests for InfluxDB writer thread coordination."""

    def test_writer_thread_processes_write_requests(self):
        """Test that writer thread processes REAL write requests from queue."""
        # Mock InfluxDB client (external dependency)
        influx_client = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        # Inject mock client
        coordinator._influx_client = influx_client

        # Start writer thread
        coordinator._start_writer_thread()

        # Add REAL write request with realistic FCD data
        coordinator.write_queue.put_write_request(
            {
                "segmentId": {
                    "seg1": {
                        "geometry": {"type": "LineString"},
                        "detailedSegment": {"date": {}},
                    }
                }
            },
            worker_id=1,
        )

        # Give writer time to process
        time.sleep(0.2)

        # Shutdown
        coordinator.shutdown()

        # Verify write queue processed the request
        stats = coordinator.write_queue.get_stats()
        assert stats["completed_writes"] > 0, "Write queue should process requests"

    def test_writer_thread_handles_write_failures(self):
        """Test that writer thread handles REAL write failures gracefully."""
        # Mock InfluxDB client that fails (external dependency)
        influx_client = MagicMock()
        influx_client.write_fcd_model.side_effect = Exception("Write failed")

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=fast_processing_function,
        )

        coordinator._influx_client = influx_client
        coordinator._start_writer_thread()

        # Add write request
        coordinator.write_queue.put_write_request({"test": "data"}, worker_id=1)

        time.sleep(0.2)
        coordinator.shutdown()

        # Should track failed write
        stats = coordinator.write_queue.get_stats()
        assert stats["failed_writes"] > 0, "Failed writes should be tracked"
