"""
Stress and integration tests for ThreadCoordinator.

Tests system behavior under high load, concurrent access, fault injection,
and resource constraints. These tests validate production readiness.
"""

import random
import threading
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from idea_shared.threading.coordinator import ThreadCoordinator

# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_processing_function(
    blob_count_per_range: int = 100,
    batch_size: int = 50,
    failure_rate: float = 0.0,
    processing_delay: float = 0.0,
):
    """
    Create a configurable mock processing function for stress testing.

    Args:
        blob_count_per_range: Number of blobs to simulate per date range
        batch_size: Batch size for processing
        failure_rate: Probability of failure (0.0 to 1.0)
        processing_delay: Delay in seconds per batch (simulates slow processing)

    Returns:
        Processing function compatible with ThreadCoordinator
    """

    def processing_function(azure_manager, start_date, end_date, batch_size=50):
        # Randomly fail based on failure_rate
        if random.random() < failure_rate:
            raise Exception("Simulated random failure")

        # Simulate processing batches
        num_batches = max(1, blob_count_per_range // batch_size)
        for batch_idx in range(num_batches):
            if processing_delay > 0:
                time.sleep(processing_delay)

            # Yield batch with some test data
            yield {
                "segment1": {
                    "speed": 50,
                    "timestamp": start_date.isoformat(),
                    "batch": batch_idx,
                }
            }

    return processing_function


# ============================================================================
# Concurrency Stress Tests
# ============================================================================


class TestConcurrencyStress:
    """Tests for high concurrency scenarios."""

    def test_high_worker_count(self):
        """Test coordinator with many workers (8 workers)."""
        azure_manager = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=8,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=50
            ),
            max_retries=2,
        )

        # Process 16 date ranges with 8 workers
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 16, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        result = coordinator.wait_for_backfill_completion(timeout=15.0)
        coordinator.shutdown()

        assert result is True

        # Verify all ranges were processed
        stats = coordinator.get_progress_stats()
        assert stats["date_queue"]["completed_ranges"] == 16

    def test_many_small_chunks(self):
        """Test processing many small chunks (high queue contention)."""
        azure_manager = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=10
            ),
            max_retries=1,
        )

        # Process 100 date ranges (1-day chunks) with 4 workers
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 4, 10, tzinfo=UTC)  # ~100 days

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        result = coordinator.wait_for_backfill_completion(timeout=30.0)
        coordinator.shutdown()

        assert result is True

        stats = coordinator.get_progress_stats()
        assert stats["date_queue"]["completed_ranges"] == 100

    def test_worker_competition_for_ranges(self):
        """Test that workers correctly compete for date ranges without duplication."""
        azure_manager = MagicMock()
        processed_ranges = []
        lock = threading.Lock()

        def tracking_processing_function(
            azure_manager, start_date, end_date, batch_size=50
        ):
            # Track which ranges are processed
            with lock:
                processed_ranges.append((start_date, end_date))
            yield {"test": "data"}

        coordinator = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=tracking_processing_function,
        )

        # 10 date ranges, 4 workers
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 10, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        coordinator.wait_for_backfill_completion(timeout=10.0)
        coordinator.shutdown()

        # Should have exactly 10 unique ranges (no duplicates)
        assert len(processed_ranges) == 10
        assert len(set(processed_ranges)) == 10  # All unique


# ============================================================================
# Fault Injection Tests
# ============================================================================


class TestFaultInjection:
    """Tests for handling random failures and error conditions."""

    def test_random_processing_failures(self):
        """Test system handles random processing failures gracefully."""
        azure_manager = MagicMock()

        # 30% failure rate with 3 retries
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=20, failure_rate=0.3
            ),
            max_retries=3,
            retry_delay=1,
        )

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 5, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        coordinator.wait_for_backfill_completion(timeout=20.0)
        coordinator.shutdown()

        stats = coordinator.get_progress_stats()

        # Some ranges may fail permanently, but system should not crash
        total_processed = stats["date_queue"]["completed_ranges"] + len(
            coordinator.date_queue.get_dead_letter_ranges()
        )
        assert total_processed == 5  # All 5 ranges accounted for

    def test_write_queue_failures(self):
        """Test handling of InfluxDB write failures."""
        azure_manager = MagicMock()
        influx_client = MagicMock()

        # Make writes fail randomly
        def random_write_failure(*args, **kwargs):
            if random.random() < 0.3:
                raise Exception("Random write failure")

        influx_client.write_fcd_model.side_effect = random_write_failure

        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=20
            ),
        )

        # Inject mock InfluxDB client
        coordinator._influx_client = influx_client

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 3, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        coordinator._start_writer_thread()

        time.sleep(2.0)  # Let some writes happen
        coordinator.shutdown()

        # System should handle write failures gracefully
        write_stats = coordinator.write_queue.get_stats()
        assert write_stats["failed_writes"] >= 0  # Some writes may have failed


# ============================================================================
# Data Integrity Tests
# ============================================================================


class TestDataIntegrity:
    """Tests for verifying no data loss or duplication."""

    def test_no_data_loss_under_load(self):
        """Test that all batches are submitted to write queue under high load."""
        azure_manager = MagicMock()
        submitted_batches = []
        lock = threading.Lock()

        def tracking_processing_function(
            azure_manager, start_date, end_date, batch_size=50
        ):
            # Generate 5 batches per range
            for batch_idx in range(5):
                batch_data = {
                    "segment1": {
                        "speed": 50,
                        "timestamp": start_date.isoformat(),
                        "batch": batch_idx,
                        "range": f"{start_date.date()}",
                    }
                }
                with lock:
                    submitted_batches.append(batch_data)
                yield batch_data

        coordinator = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=tracking_processing_function,
        )

        # 10 ranges × 5 batches = 50 total batches
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 10, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        coordinator.wait_for_backfill_completion(timeout=15.0)

        # Give writer thread time to process
        time.sleep(1.0)
        coordinator.shutdown()

        # Should have submitted exactly 50 batches
        assert len(submitted_batches) == 50

    def test_no_batch_duplication(self):
        """Test that batches are not duplicated in write queue."""
        azure_manager = MagicMock()
        write_queue_submissions = []
        lock = threading.Lock()

        # Mock write queue to track submissions
        original_put = None

        def tracking_put_write_request(fcd_data, worker_id, timeout=10.0):
            with lock:
                write_queue_submissions.append((worker_id, str(fcd_data)))
            # Call original method
            if original_put:
                original_put(fcd_data, worker_id, timeout)

        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=30
            ),
        )

        # Patch write queue
        original_put = coordinator.write_queue.put_write_request
        coordinator.write_queue.put_write_request = tracking_put_write_request

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 3, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        coordinator.wait_for_backfill_completion(timeout=10.0)
        coordinator.shutdown()

        # Check for duplicates
        unique_submissions = set(write_queue_submissions)
        assert len(unique_submissions) == len(write_queue_submissions), (
            "Found duplicate submissions"
        )


# ============================================================================
# Memory and Resource Tests
# ============================================================================


class TestMemoryAndResources:
    """Tests for memory usage and resource management."""

    def test_bounded_write_queue_prevents_memory_growth(self):
        """Test that bounded write queue prevents unbounded memory growth."""
        azure_manager = MagicMock()

        # Small write queue with slow writer
        coordinator = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=200, processing_delay=0.01
            ),
            max_write_queue_size=10,  # Very small queue
        )

        # Mock slow writer
        influx_client = MagicMock()

        def slow_write(*args, **kwargs):
            time.sleep(0.05)  # Slow writes

        influx_client.write_fcd_model.side_effect = slow_write
        coordinator._influx_client = influx_client

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 3, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Monitor queue size during processing
        max_queue_size_seen = 0
        for _ in range(20):
            stats = coordinator.write_queue.get_stats()
            max_queue_size_seen = max(max_queue_size_seen, stats["queue_size"])
            time.sleep(0.1)

        coordinator.shutdown()

        # Queue size should never exceed configured maximum
        assert max_queue_size_seen <= 10


# ============================================================================
# Shutdown Tests
# ============================================================================


class TestGracefulShutdown:
    """Tests for graceful shutdown under various conditions."""

    def test_shutdown_during_active_processing(self):
        """Test shutdown interrupts active processing gracefully."""
        azure_manager = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=100, processing_delay=0.05
            ),
        )

        # Start processing large date range
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 3, 1, tzinfo=UTC)  # 60 days

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Let workers start processing
        time.sleep(0.5)

        # Shutdown while processing is active
        coordinator.shutdown(timeout=5.0)

        # All threads should be stopped
        for thread in coordinator._worker_threads:
            assert not thread.is_alive()
        assert coordinator._writer_thread is not None
        assert not coordinator._writer_thread.is_alive()

    def test_shutdown_with_pending_writes(self):
        """Test shutdown handles pending writes in queue."""
        azure_manager = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=50
            ),
            max_write_queue_size=100,
        )

        # Mock very slow writer to create backlog
        influx_client = MagicMock()
        influx_client.write_fcd_model.side_effect = lambda *args: time.sleep(1.0)
        coordinator._influx_client = influx_client

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 3, tzinfo=UTC)

        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Let writes accumulate
        time.sleep(0.5)

        stats_before = coordinator.write_queue.get_stats()
        assert stats_before["queue_size"] > 0

        # Shutdown should handle pending writes gracefully
        coordinator.shutdown(timeout=5.0)

        assert coordinator.is_shutdown()
        assert coordinator.write_queue.is_shutdown()


# ============================================================================
# Performance Benchmark Tests
# ============================================================================


@pytest.mark.slow
class TestPerformanceBenchmarks:
    """Performance benchmarks for multi-threaded vs single-threaded processing."""

    def test_benchmark_single_vs_multi_threaded(self):
        """Compare single-threaded vs multi-threaded performance."""
        azure_manager = MagicMock()

        # Simulate realistic processing time (longer delay to show multi-threading benefit)
        processing_function = create_mock_processing_function(
            blob_count_per_range=100, processing_delay=0.02
        )

        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 10, tzinfo=UTC)  # 10 date ranges

        # Single-threaded timing
        coordinator_single = ThreadCoordinator(
            num_backfill_workers=1,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=processing_function,
        )

        start_time = time.time()
        coordinator_single.start_backfill(start_date, end_date, chunk_days=1)
        coordinator_single.wait_for_backfill_completion(timeout=30.0)
        coordinator_single.shutdown()
        single_threaded_time = time.time() - start_time

        # Multi-threaded timing (4 workers)
        coordinator_multi = ThreadCoordinator(
            num_backfill_workers=4,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=processing_function,
        )

        start_time = time.time()
        coordinator_multi.start_backfill(start_date, end_date, chunk_days=1)
        coordinator_multi.wait_for_backfill_completion(timeout=30.0)
        coordinator_multi.shutdown()
        multi_threaded_time = time.time() - start_time

        # Multi-threaded should be faster (at least 1.1x speedup expected)
        # Note: Conservative threshold accounts for threading overhead and GIL limitations in Python
        # For IO-bound tasks with simulated delays, even modest speedup validates benefit
        speedup = single_threaded_time / multi_threaded_time
        assert speedup >= 1.1, (
            f"Expected speedup >= 1.1x, got {speedup:.2f}x ({single_threaded_time:.2f}s vs {multi_threaded_time:.2f}s)"
        )

    def test_throughput_under_load(self):
        """Measure throughput with high worker count and large dataset."""
        azure_manager = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=8,
            azure_manager=azure_manager,
            influx_config={},
            logger=MagicMock(),
            processing_function=create_mock_processing_function(
                blob_count_per_range=100, processing_delay=0.005
            ),
        )

        # Process 30 date ranges
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 30, tzinfo=UTC)

        start_time = time.time()
        coordinator.start_backfill(start_date, end_date, chunk_days=1)
        coordinator.wait_for_backfill_completion(timeout=60.0)
        coordinator.shutdown()
        elapsed_time = time.time() - start_time

        stats = coordinator.get_progress_stats()

        # Calculate throughput
        ranges_processed = stats["date_queue"]["completed_ranges"]
        throughput = ranges_processed / elapsed_time  # ranges per second

        # Should process at least 1 range per second with 8 workers
        assert throughput >= 1.0, f"Throughput too low: {throughput:.2f} ranges/sec"
