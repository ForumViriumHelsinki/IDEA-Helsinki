"""
Tests for ThreadCoordinator backfill functionality in main.py.

This module tests backfill functionality, particularly focusing on
timezone-aware datetime handling.

Following TDD principles: Tests use REAL ThreadCoordinator execution with
minimal mocking (only external dependencies like InfluxDB).
"""

import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Mock external modules that aren't needed for tests
sys.modules["sentry_sdk"] = MagicMock()

# Mock openfeature modules (feature flags library)
openfeature_mock = MagicMock()
sys.modules["openfeature"] = openfeature_mock
sys.modules["openfeature.api"] = MagicMock()
sys.modules["openfeature.client"] = MagicMock()
sys.modules["openfeature.evaluation_context"] = MagicMock()
sys.modules["openfeature.flag_evaluation"] = MagicMock()
sys.modules["openfeature.provider"] = MagicMock()
sys.modules["openfeature.provider.provider"] = MagicMock()


def fast_processing_function(azure_manager, start_date, end_date, batch_size=50):
    """
    Fast processing function for integration tests.

    Returns realistic FCD data structure with minimal delay.
    """
    time.sleep(0.01)  # Minimal delay to simulate work
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


class TestMultithreadedMode:
    """Tests for ThreadCoordinator backfill functionality."""

    def test_naive_datetime_comparison_raises_error(self):
        """
        Test that comparing naive and aware datetimes raises TypeError.

        This demonstrates the bug that was fixed: when FCD_HISTORY_START_DATE
        was parsed without timezone info, it created a naive datetime that
        couldn't be compared with the timezone-aware end_date.
        """
        FCD_HISTORY_START_DATE = "2024-06-01"

        # INCORRECT: Creates a NAIVE datetime (no timezone)
        naive_start_date = datetime.strptime(FCD_HISTORY_START_DATE, "%Y-%m-%d")

        # This creates an AWARE datetime (UTC timezone)
        aware_end_date = datetime.now(UTC)

        # Mock the azure manager to test comparison
        azure_manager = MagicMock()

        def mock_get_blobs_in_range(start_time, end_time):
            # This comparison will fail if one is naive and one is aware
            if start_time > end_time:
                raise ValueError("Start time cannot be after end time.")
            # This date arithmetic will also fail with mixed timezone awareness
            _ = (end_time.date() - start_time.date()).days
            return []

        azure_manager.get_blobs_in_range = mock_get_blobs_in_range

        # This raises TypeError when mixing naive and aware datetimes
        with pytest.raises(
            TypeError, match="can't compare offset-naive and offset-aware"
        ):
            azure_manager.get_blobs_in_range(naive_start_date, aware_end_date)

    def test_timezone_aware_dates_can_be_compared(self):
        """
        Test that timezone-aware dates can be compared without errors.

        This test demonstrates the correct behavior after the fix.
        """
        FCD_HISTORY_START_DATE = "2024-06-01"

        # CORRECT: Make the parsed date timezone-aware
        aware_start_date = datetime.strptime(
            FCD_HISTORY_START_DATE, "%Y-%m-%d"
        ).replace(tzinfo=UTC)
        aware_end_date = datetime.now(UTC)

        # Mock azure manager
        azure_manager = MagicMock()

        def mock_get_blobs_in_range(start_time, end_time):
            # These comparisons should work fine with both dates being aware
            if start_time > end_time:
                raise ValueError("Start time cannot be after end time.")
            # Date arithmetic works correctly with both being timezone-aware
            _ = (end_time.date() - start_time.date()).days
            return []

        azure_manager.get_blobs_in_range = mock_get_blobs_in_range

        # This should NOT raise any error
        result = azure_manager.get_blobs_in_range(aware_start_date, aware_end_date)
        assert result == []

    def test_thread_coordinator_timezone_aware_workflow(self):
        """
        Integration test for ThreadCoordinator with timezone-aware datetimes.

        This test uses REAL ThreadCoordinator execution to verify timezone-aware
        datetime handling throughout the multithreaded workflow, which was the root
        cause of the bug that prompted this test.

        Verifies:
        1. Timezone-aware datetimes work correctly with ThreadCoordinator
        2. Date range processing completes without timezone errors
        3. Real threading coordination with proper datetime handling
        """
        from idea_shared.threading import ThreadCoordinator

        # Create timezone-aware datetimes (this is what the bug was about)
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        end_date = datetime(2025, 1, 2, tzinfo=UTC)

        # Mock only external dependencies
        azure_manager = MagicMock()
        influx_config = {
            "url": "http://localhost:8086",
            "token": "test-token",
            "org": "test-org",
            "bucket": "test-bucket",
        }
        logger = MagicMock()

        # Create REAL coordinator
        coordinator = ThreadCoordinator(
            num_backfill_workers=2,
            azure_manager=azure_manager,
            influx_config=influx_config,
            logger=logger,
            processing_function=fast_processing_function,
            max_retries=2,
            retry_delay=1,
        )

        # Start backfill with timezone-aware datetimes
        # This should NOT raise "can't compare offset-naive and offset-aware" error
        coordinator.start_backfill(start_date, end_date, chunk_days=1)

        # Wait for completion
        result = coordinator.wait_for_backfill_completion(timeout=10.0)
        assert result is True, "Coordinator should complete within timeout"

        # Verify work was actually processed
        stats = coordinator.get_progress_stats()
        assert stats["date_queue"]["completed_ranges"] == 2, (
            "Should complete 2 date ranges (Jan 1-1, Jan 2-2)"
        )

        # Clean up
        coordinator.shutdown()
