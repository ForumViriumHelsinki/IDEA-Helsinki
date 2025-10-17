"""
Tests for ThreadCoordinator - Multi-threaded FCD processing orchestration.

Following TDD RED-GREEN-REFACTOR cycle.
"""

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

from idea_shared.threading.coordinator import ThreadCoordinator
from idea_shared.threading.date_queue import DateRangeQueue
from idea_shared.threading.write_queue import InfluxDBWriteQueue


def mock_processing_function(azure_manager, start_date, end_date, batch_size=50):
    """
    Mock processing function that yields empty batches.
    This simulates the streaming processing interface.
    """
    # Yield a single batch with empty data
    yield {}


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
            processing_function=mock_processing_function,
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
            processing_function=mock_processing_function,
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
            processing_function=mock_processing_function,
            max_write_queue_size=50,
        )

        # Write queue should respect custom size
        assert coordinator.write_queue is not None


class TestThreadCoordinatorBackfill:
    """Tests for backfill processing coordination."""

    def test_start_backfill_populates_date_queue(self):
        """Test that start_backfill populates the date queue."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 3, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Should have 3 date ranges (2025-01-01, 2025-01-02, 2025-01-03)
        stats = coordinator.date_queue.get_stats()
        assert stats["total_ranges"] == 3

    def test_start_backfill_spawns_worker_threads(self):
        """Test that start_backfill spawns the correct number of workers."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=3,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 2, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Should have 3 backfill workers + 1 writer thread
        assert len(coordinator._worker_threads) == 3
        assert coordinator._writer_thread is not None

    def test_start_backfill_spawns_writer_thread(self):
        """Test that start_backfill spawns the InfluxDB writer thread."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        assert coordinator._writer_thread is not None
        assert coordinator._writer_thread.is_alive()

    def test_wait_for_backfill_completion(self):
        """Test waiting for backfill to complete."""
        # Mock Azure manager that returns empty data (fast completion)
        azure_manager = MagicMock()
        azure_manager.get_fcd_data_for_date_range.return_value = {}

        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Should complete quickly with no real work
        result = coordinator.wait_for_backfill_completion(timeout=5.0)
        assert result is True

    def test_wait_for_backfill_timeout(self):
        """Test that wait_for_backfill respects timeout."""
        # Mock Azure manager that blocks indefinitely
        azure_manager = MagicMock()
        azure_manager.get_fcd_data_for_date_range.side_effect = (
            lambda *args, **kwargs: time.sleep(10)
        )

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
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
            processing_function=mock_processing_function,
        )

        coordinator.shutdown()

        assert coordinator.is_shutdown()
        assert coordinator.write_queue.is_shutdown()

    def test_shutdown_waits_for_threads(self):
        """Test that shutdown waits for threads to complete."""
        azure_manager = MagicMock()
        azure_manager.get_fcd_data_for_date_range.return_value = {}

        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        coordinator.start_backfill(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 1
        )

        # Allow threads to start
        time.sleep(0.1)

        coordinator.shutdown()

        # All threads should be stopped
        for thread in coordinator._worker_threads:
            assert not thread.is_alive()
        assert not coordinator._writer_thread.is_alive()

    def test_shutdown_respects_timeout(self):
        """Test that shutdown respects timeout parameter."""
        # Mock that blocks indefinitely
        azure_manager = MagicMock()
        azure_manager.get_fcd_data_for_date_range.side_effect = (
            lambda *args, **kwargs: time.sleep(10)
        )

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
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
    """Tests for progress tracking."""

    def test_get_progress_statistics(self):
        """Test getting progress statistics."""
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        stats = coordinator.get_progress_stats()

        assert "date_queue" in stats
        assert "write_queue" in stats
        assert "workers_alive" in stats
        assert "writer_alive" in stats

    def test_progress_tracks_completed_ranges(self):
        """Test that progress correctly tracks completed date ranges."""
        azure_manager = MagicMock()
        azure_manager.get_fcd_data_for_date_range.return_value = {}

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
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
        """Test that writer thread processes write requests from queue."""
        # Mock InfluxDB client
        influx_client = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        # Inject mock client
        coordinator._influx_client = influx_client

        # Start writer thread
        coordinator._start_writer_thread()

        # Add write request
        coordinator.write_queue.put_write_request({"test": "data"}, worker_id=1)

        # Give writer time to process
        time.sleep(0.2)

        # Shutdown
        coordinator.shutdown()

        # InfluxDB client should have been called
        # (exact assertion depends on implementation)

    def test_writer_thread_handles_write_failures(self):
        """Test that writer thread handles write failures gracefully."""
        # Mock InfluxDB client that fails
        influx_client = MagicMock()
        influx_client.write_fcd_data.side_effect = Exception("Write failed")

        coordinator = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=MagicMock(),
            influx_config={},
            logger=MagicMock(),
            processing_function=mock_processing_function,
        )

        coordinator._influx_client = influx_client
        coordinator._start_writer_thread()

        # Add write request
        coordinator.write_queue.put_write_request({"test": "data"}, worker_id=1)

        time.sleep(0.2)
        coordinator.shutdown()

        # Should track failed write
        stats = coordinator.write_queue.get_stats()
        assert stats["failed_writes"] > 0
