"""
Tests for multi-threaded mode in main.py.

This module tests the multi-threaded backfill functionality, particularly
focusing on timezone-aware datetime handling.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestMultithreadedMode:
    """Tests for multi-threaded mode functionality."""

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

    @patch("main.FCDInfluxDBManager")
    @patch("main.ThreadCoordinator")
    def test_run_multithreaded_with_empty_database(
        self, mock_thread_coordinator, mock_influx_manager
    ):
        """
        Integration test for run_multithreaded when database is empty.

        This ensures the full workflow uses timezone-aware datetimes.
        """
        # Mock InfluxDB manager to return None (empty database)
        mock_manager_instance = MagicMock()
        mock_manager_instance.check_connection.return_value = True
        mock_manager_instance.get_last_update_timestamp.return_value = None
        mock_influx_manager.return_value.__enter__.return_value = mock_manager_instance

        # Mock ThreadCoordinator
        mock_coordinator_instance = MagicMock()
        mock_thread_coordinator.return_value = mock_coordinator_instance

        # Mock stats to simulate immediate completion
        mock_coordinator_instance.get_progress_stats.return_value = {
            "date_queue": {"completed_ranges": 1, "total_ranges": 1},
            "write_queue": {"queue_size": 0, "completed_writes": 1},
            "workers_alive": False,
        }

        # Import and patch constants
        with (
            patch("main.FCD_HISTORY_START_DATE", "2024-06-01"),
            patch("main.INFLUX_DB_URL", "http://localhost:8086"),
            patch("main.INFLUX_DB_FCD_TOKEN", "test-token"),
            patch("main.INFLUX_DB_ORG", "test-org"),
            patch("main.INFLUX_DB_FCD_BUCKET", "test-bucket"),
            patch("main.FCD_BACKFILL_WORKER_COUNT", 2),
            patch("main.FCD_BACKFILL_CHUNK_DAYS", 7),
            patch("main.FCD_WRITE_QUEUE_MAX_SIZE", 100),
            patch("main.FCD_MAX_CHUNK_RETRIES", 3),
            patch("main.FCD_RETRY_DELAY_SECONDS", 5),
            patch("main.FCD_PROCESSING_BATCH_SIZE", 50),
            patch("main.process_date_range_streaming", MagicMock()),
            patch("main.logger", MagicMock()),
        ):
            from main import run_multithreaded

            # Mock azure manager
            azure_manager = MagicMock()

            # This should not raise timezone comparison error
            result = run_multithreaded(azure_manager)

            # Verify ThreadCoordinator.start_backfill was called with timezone-aware datetimes
            assert mock_coordinator_instance.start_backfill.called
            call_args = mock_coordinator_instance.start_backfill.call_args[0]
            start_date_arg = call_args[0]
            end_date_arg = call_args[1]

            # Both should be timezone-aware
            assert (
                start_date_arg.tzinfo is not None
            ), "start_date should be timezone-aware"
            assert end_date_arg.tzinfo is not None, "end_date should be timezone-aware"

            # Function should return True on success
            assert result is True
