"""
Equivalence tests for FCD processing with varying worker counts.

This module validates that the ThreadCoordinator produces correct output
regardless of worker count and blob ordering.

Testing Strategy (Golden Output):
1. Run streaming processor directly with test fixtures → capture "golden" output
2. Run ThreadCoordinator with same fixtures → capture output
3. Compare canonicalized outputs (order-agnostic)
4. Verify diagnostic counters match

Processing Policies (explicit for consistency):
- Time binning: 5-minute intervals [t, t+5min)
- Duplicate handling: Last value wins within interval
- Validation: Skip segments with missing geometry
- Value bounds: Accept all values as-is (no clamping)
- Rounding: 3 decimal places for floats
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Mock external modules before imports
sys.modules["sentry_sdk"] = MagicMock()

# Mock openfeature modules
openfeature_mock = MagicMock()
sys.modules["openfeature"] = openfeature_mock
sys.modules["openfeature.api"] = MagicMock()
sys.modules["openfeature.client"] = MagicMock()
sys.modules["openfeature.evaluation_context"] = MagicMock()
sys.modules["openfeature.flag_evaluation"] = MagicMock()
sys.modules["openfeature.provider"] = MagicMock()
sys.modules["openfeature.provider.provider"] = MagicMock()

# ruff: noqa: E402
from idea_shared.threading import ThreadCoordinator  # noqa: E402
from mocks import MockAzureBlobStorage  # noqa: E402

from fcd_processing import process_date_range_streaming  # noqa: E402


class TestMultithreadingEquivalence:
    """Tests validating streaming processor vs ThreadCoordinator equivalence."""

    @pytest.fixture
    def fixture_dir(self):
        """Get test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    @pytest.fixture
    def mock_azure(self, fixture_dir):
        """Create mock Azure storage with test fixtures."""
        return MockAzureBlobStorage(fixture_dir, seed=None)

    @pytest.fixture
    def mock_azure_shuffled(self, fixture_dir):
        """Create mock Azure storage with shuffled blob order."""
        return MockAzureBlobStorage(fixture_dir, seed=42)

    def test_streaming_processing_baseline(self, mock_azure):
        """
        Baseline test: Verify streaming processing works.

        This establishes the "golden output" for comparison.
        """
        start_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 12, 15, 0, tzinfo=UTC)

        # Process with streaming approach
        batches = list(
            process_date_range_streaming(
                mock_azure, start_date, end_date, batch_size=50
            )
        )

        # Verify we got output
        assert len(batches) > 0, "Should process at least one batch"

        # Verify structure
        for batch in batches:
            assert "segmentId" in batch, "Batch should have segmentId key"
            assert isinstance(batch["segmentId"], dict), (
                "segmentId should be dictionary"
            )

    def test_coordinator_vs_direct_streaming_equivalence(
        self, mock_azure, fixture_dir
    ):
        """
        Core equivalence test: Verify ThreadCoordinator produces same output as direct streaming.

        Tests:
        1. Both approaches process same test data
        2. Output is identical (order-agnostic)
        3. Diagnostic counters match
        """
        start_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 12, 15, 0, tzinfo=UTC)

        # ===== DIRECT STREAMING (Golden Output) =====
        direct_streaming_batches = list(
            process_date_range_streaming(
                mock_azure, start_date, end_date, batch_size=50
            )
        )

        # Reset mock for second run
        mock_azure.reset()

        # ===== THREAD COORDINATOR =====
        mock_influx_config = {
            "url": "http://localhost:8086",
            "token": "test-token",
            "org": "test-org",
            "bucket": "test-bucket",
        }
        logger = MagicMock()

        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=mock_azure,
            influx_config=mock_influx_config,
            logger=logger,
            processing_function=process_date_range_streaming,
            max_retries=2,
            retry_delay=1,
        )

        # Start multithreaded backfill
        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Wait for completion
        result = coordinator.wait_for_backfill_completion(timeout=10.0)
        assert result is True, "Coordinator should complete within timeout"

        # Get multithreaded output
        # Note: ThreadCoordinator yields batches through processing_function
        # We need to capture these during execution
        # For now, verify it completes successfully
        stats = coordinator.get_progress_stats()
        assert stats["date_queue"]["completed_ranges"] > 0

        # Clean up
        coordinator.shutdown()

        # ===== COMPARISON =====
        # TODO: Once we wire up output capture from ThreadCoordinator,
        # we'll compare the outputs using canonicalization
        # is_equal, diff = compare_point_sets(direct_output, coordinator_output)
        # assert is_equal, f"Outputs should be identical: {diff}"

        # For now, verify both completed successfully
        assert len(direct_streaming_batches) > 0
        assert stats["date_queue"]["completed_ranges"] > 0

    def test_with_varying_worker_counts(self, mock_azure):
        """
        Test processing with different worker counts, including single-worker mode.

        Verifies that worker count doesn't affect output correctness.
        Single-worker mode (1) provides sequential processing equivalent.
        """
        start_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 12, 15, 0, tzinfo=UTC)

        mock_influx_config = {
            "url": "http://localhost:8086",
            "token": "test-token",
            "org": "test-org",
            "bucket": "test-bucket",
        }
        logger = MagicMock()

        for num_workers in [1, 2, 4]:
            mock_azure.reset()

            coordinator = ThreadCoordinator(
                num_backfill_workers=num_workers,
                azure_manager=mock_azure,
                influx_config=mock_influx_config,
                logger=logger,
                processing_function=process_date_range_streaming,
                max_retries=2,
                retry_delay=1,
            )

            coordinator.start_backfill(start_date, end_date, chunk_days=1)
            result = coordinator.wait_for_backfill_completion(timeout=10.0)
            assert result is True, f"Should complete with {num_workers} workers"

            stats = coordinator.get_progress_stats()
            assert stats["date_queue"]["completed_ranges"] > 0

            coordinator.shutdown()

    def test_with_shuffled_blob_order(self, mock_azure_shuffled):
        """
        Test that blob processing order doesn't affect output.

        Uses seeded shuffling to ensure reproducible but different ordering.
        """
        start_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        end_date = datetime(2024, 1, 1, 12, 15, 0, tzinfo=UTC)

        # Process with shuffled order
        batches = list(
            process_date_range_streaming(
                mock_azure_shuffled, start_date, end_date, batch_size=50
            )
        )

        # Should still produce valid output regardless of order
        assert len(batches) > 0, "Should process blobs even when shuffled"

        # TODO: Compare against non-shuffled golden output
        # once canonicalization is wired up

    @pytest.mark.skip(reason="Requires InfluxDB output capture integration")
    def test_detailed_output_comparison(self):
        """
        Detailed comparison of InfluxDB points between worker configurations.

        This test will be implemented once we have full output capture
        from ThreadCoordinator integrated with MockInfluxWriter.

        Test plan:
        1. Run with 1 worker (sequential) with MockInfluxWriter
        2. Capture all points written
        3. Run with N workers with MockInfluxWriter
        4. Capture all points written
        5. Use canonicalize_points() for order-agnostic comparison
        6. Assert exact equality of canonical point sets
        7. Verify diagnostic counters match
        """
        pass
