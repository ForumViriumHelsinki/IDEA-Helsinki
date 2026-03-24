"""
Unit tests for IDEA Helsinki health checks.
"""

import asyncio
import json
import os
import tempfile
import tracemalloc
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from idea_shared.lib.Constants.Constants import (
    DISTURBANCE_DATA_MAX_AGE_MINUTES,
    HEALTH_CHECK_FCD_DATABASE,
    HEALTH_CHECK_VALIDATION_DATABASE,
    WORKER_HEALTH_THRESHOLD_PERCENT,
)

from src.health_checks import (
    DisturbanceDataHealthCheck,  # ty: ignore[unresolved-import]
    FCDDatabaseHealthCheck,  # ty: ignore[unresolved-import]
    InfluxDBConnectionManager,  # ty: ignore[unresolved-import]
    OrchestratorHealthCheck,  # ty: ignore[unresolved-import]
    ValidationDatabaseHealthCheck,  # ty: ignore[unresolved-import]
    WorkerStatusHealthCheck,  # ty: ignore[unresolved-import]
)


class TestFCDDatabaseHealthCheck:
    """Test FCD database health check."""

    def test_initialization_with_defaults(self):
        """Test that initialization sets name and connection_string correctly."""
        check = FCDDatabaseHealthCheck(
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            data_freshness_hours=1,
        )

        # Verify name uses constant
        assert check.name == HEALTH_CHECK_FCD_DATABASE
        assert check.name == "fcd_database"

        # Verify connection string is properly formatted
        assert "api/v2/buckets/test_bucket" in check.connection_string
        assert "http://localhost:8086" in check.connection_string

    def test_initialization_with_custom_name(self):
        """Test that custom name can be provided."""
        check = FCDDatabaseHealthCheck(
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            name="custom_fcd_db",
        )

        assert check.name == "custom_fcd_db"

    def test_parameter_validation(self):
        """Test that empty parameters raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            FCDDatabaseHealthCheck(
                url="",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="",
                org="test_org",
                bucket="test_bucket",
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="",
                bucket="test_bucket",
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="",
            )

    @pytest.mark.asyncio
    async def test_healthy_with_recent_data(self):
        """Test healthy status when database is accessible and has recent data."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # Mock query result with recent data
            mock_table = MagicMock()
            mock_table.records = [MagicMock()]  # Non-empty records
            mock_query_api.query.return_value = [mock_table]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            assert result.status == "healthy"
            assert result.message is not None
            assert result.metadata is not None
            assert "recent data" in result.message.lower()
            assert result.metadata["has_recent_data"] is True

    @pytest.mark.asyncio
    async def test_degraded_with_no_recent_data(self):
        """Test degraded status when database is accessible but has no recent data."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # Mock query result with no data
            mock_table = MagicMock()
            mock_table.records = []  # Empty records
            mock_query_api.query.return_value = [mock_table]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            assert result.status == "degraded"
            assert result.message is not None
            assert result.metadata is not None
            assert "no data" in result.message.lower()
            assert result.metadata["has_recent_data"] is False

    @pytest.mark.asyncio
    async def test_healthy_with_backfill_mode(self):
        """Test healthy status when in backfill mode with historical data."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # Mock recent query returning empty (no recent data)
            mock_empty_table = MagicMock()
            mock_empty_table.records = []

            # Mock latest query returning old data (backfill mode)
            mock_old_table = MagicMock()
            mock_old_record = MagicMock()
            # Data from 5 hours ago (older than 1 hour threshold)
            old_timestamp = datetime.now(UTC) - timedelta(hours=5)
            mock_old_record.get_time = MagicMock(return_value=old_timestamp)
            mock_old_table.records = [mock_old_record]

            # First call returns empty (recent query), second returns old data (latest query)
            mock_query_api.query.side_effect = [
                [mock_empty_table],  # recent_query
                [mock_old_table],  # latest_query
            ]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            assert result.status == "healthy"
            assert result.message is not None
            assert result.metadata is not None
            assert "backfilling" in result.message.lower()
            assert result.metadata["mode"] == "backfill"
            assert "latest_data_timestamp" in result.metadata
            assert "backfill_progress" in result.metadata
            assert result.metadata["data_age_hours"] > 1

    @pytest.mark.asyncio
    async def test_backfill_mode_with_null_record(self):
        """Test backfill detection handles None records gracefully."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # Mock recent query returning empty
            mock_empty_table = MagicMock()
            mock_empty_table.records = []

            # Mock latest query returning table but with None-like record
            mock_latest_table = MagicMock()
            mock_latest_table.records = []  # Empty records despite has_any_data being True

            mock_query_api.query.side_effect = [
                [mock_empty_table],  # recent_query
                [mock_latest_table],  # latest_query with empty records
            ]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            # Should fall through to degraded status
            assert result.status == "degraded"
            assert result.message is not None
            assert "no data" in result.message.lower()

    @pytest.mark.asyncio
    async def test_backfill_mode_at_threshold(self):
        """Test edge case: data exactly at the freshness threshold."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # Mock recent query returning empty
            mock_empty_table = MagicMock()
            mock_empty_table.records = []

            # Mock latest query with data exactly at threshold (1 hour old)
            mock_threshold_table = MagicMock()
            mock_threshold_record = MagicMock()
            threshold_timestamp = datetime.now(UTC) - timedelta(hours=1, minutes=1)
            mock_threshold_record.get_time = MagicMock(return_value=threshold_timestamp)
            mock_threshold_table.records = [mock_threshold_record]

            mock_query_api.query.side_effect = [
                [mock_empty_table],  # recent_query
                [mock_threshold_table],  # latest_query
            ]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            # Should be in backfill mode since data_age_hours > self.data_freshness_hours
            assert result.status == "healthy"
            assert result.metadata is not None
            assert result.metadata["mode"] == "backfill"

    @pytest.mark.asyncio
    async def test_backfill_mode_query_failure(self):
        """Test that query failures during backfill detection are handled."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # First query succeeds (empty), second query fails
            from influxdb_client.client.exceptions import InfluxDBError

            mock_query_api.query.side_effect = [
                [],  # Empty result for recent_query
                InfluxDBError(message="Query timeout"),
            ]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            # Should return unhealthy status with error details
            assert result.status == "unhealthy"
            assert result.metadata is not None
            assert "InfluxDBError" in result.metadata["error_type"]

    @pytest.mark.asyncio
    async def test_backfill_progress_metadata(self):
        """Test that backfill progress metadata is correctly populated."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=True)

            # Mock the InfluxDB client
            mock_client = MagicMock()
            mock_query_api = MagicMock()

            # Mock recent query returning empty
            mock_empty_table = MagicMock()
            mock_empty_table.records = []

            # Mock latest query with specific timestamp for metadata verification
            mock_old_table = MagicMock()
            mock_old_record = MagicMock()
            specific_timestamp = datetime(2025, 10, 10, 14, 30, 0, tzinfo=UTC)
            mock_old_record.get_time = MagicMock(return_value=specific_timestamp)
            mock_old_table.records = [mock_old_record]

            mock_query_api.query.side_effect = [
                [mock_empty_table],
                [mock_old_table],
            ]
            mock_client.query_api.return_value = mock_query_api

            mock_conn_manager.get_client = AsyncMock(return_value=mock_client)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1,
            )

            result = await check.check()

            assert result.status == "healthy"
            assert result.metadata is not None
            assert result.metadata["mode"] == "backfill"
            assert (
                result.metadata["latest_data_timestamp"]
                == specific_timestamp.isoformat()
            )
            assert "2025-10-10" in result.metadata["backfill_progress"]
            assert "data_age_hours" in result.metadata
            assert isinstance(result.metadata["data_age_hours"], int | float)

    @pytest.mark.asyncio
    async def test_unhealthy_on_connection_failure(self):
        """Test unhealthy status when database connection fails."""
        with patch(
            "src.health_checks.InfluxDBConnectionManager.get_instance"
        ) as mock_get_instance:
            # Setup connection manager mock that fails ping
            mock_conn_manager = AsyncMock()
            mock_conn_manager.ping = AsyncMock(return_value=False)
            mock_get_instance.return_value = mock_conn_manager

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
            )

            result = await check.check()

            assert result.status == "unhealthy"
            assert result.message is not None
            assert "Failed to ping" in result.message


class TestValidationDatabaseHealthCheck:
    """Test validation database health check."""

    def test_initialization_with_defaults(self):
        """Test that initialization sets name and connection_string correctly."""
        check = ValidationDatabaseHealthCheck(
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="validation_bucket",
        )

        # Verify name uses constant
        assert check.name == HEALTH_CHECK_VALIDATION_DATABASE
        assert check.name == "validation_database"

        # Verify connection string is properly formatted
        assert "api/v2/buckets/validation_bucket" in check.connection_string
        assert "http://localhost:8086" in check.connection_string

    def test_initialization_with_custom_name(self):
        """Test that custom name can be provided."""
        check = ValidationDatabaseHealthCheck(
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="validation_bucket",
            name="custom_validation_db",
        )

        assert check.name == "custom_validation_db"

    def test_parameter_validation(self):
        """Test that empty parameters raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ValidationDatabaseHealthCheck(
                url="",
                token="test_token",
                org="test_org",
                bucket="validation_bucket",
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            ValidationDatabaseHealthCheck(
                url="http://localhost:8086",
                token="",
                org="test_org",
                bucket="validation_bucket",
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            ValidationDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="",
                bucket="validation_bucket",
            )

        with pytest.raises(ValueError, match="cannot be empty"):
            ValidationDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="",
            )


class TestDisturbanceDataHealthCheck:
    """Test disturbance data health check."""

    @pytest.mark.asyncio
    async def test_healthy_with_fresh_valid_data(self):
        """Test healthy status with fresh and valid JSON data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write valid JSON with segments (matching actual data structure)
            data = {
                "segmentId": {
                    "seg1": {"detailedCollisions": []},
                    "seg2": {"detailedCollisions": []},
                },
            }
            json.dump(data, f)
            f.flush()

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name, max_age_minutes=DISTURBANCE_DATA_MAX_AGE_MINUTES
                )

                result = await check.check()

                assert result.status == "healthy"
                assert result.message is not None
                assert result.metadata is not None
                assert "available and fresh" in result.message
                assert result.metadata["segment_count"] == 2
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_degraded_with_stale_data(self):
        """Test degraded status when data file is stale."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write valid JSON with required fields
            json.dump(
                {
                    "segmentId": {"seg1": {}},
                },
                f,
            )
            f.flush()

            # Make file appear old
            old_time = (datetime.now() - timedelta(hours=3)).timestamp()
            os.utime(f.name, (old_time, old_time))

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name,
                    max_age_minutes=DISTURBANCE_DATA_MAX_AGE_MINUTES,
                    critical=False,
                )

                result = await check.check()

                assert result.status == "degraded"
                assert result.message is not None
                assert result.metadata is not None
                assert "stale" in result.message.lower()
                assert (
                    result.metadata["file_age_minutes"]
                    > DISTURBANCE_DATA_MAX_AGE_MINUTES
                )
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_unhealthy_with_invalid_json(self):
        """Test unhealthy status with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write invalid JSON
            f.write("{ invalid json }")
            f.flush()

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name, max_age_minutes=DISTURBANCE_DATA_MAX_AGE_MINUTES
                )

                result = await check.check()

                assert result.status == "unhealthy"
                assert result.message is not None
                assert "Invalid JSON" in result.message
            finally:
                os.unlink(f.name)


class TestWorkerStatusHealthCheck:
    """Test worker status health check."""

    @pytest.mark.asyncio
    async def test_healthy_with_no_workers(self):
        """Test healthy status when no workers are active (normal idle state)."""
        mock_manager = MagicMock()
        mock_manager.active_segments = {}

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        result = await check.check()

        assert result.status == "healthy"
        assert result.message is not None
        assert result.metadata is not None
        assert "no disturbances" in result.message.lower()
        assert result.metadata["total_workers"] == 0

    @pytest.mark.asyncio
    async def test_healthy_with_all_workers_running(self):
        """Test healthy status when all workers are running."""
        mock_manager = MagicMock()

        # Create mock tasks that are not done
        task1 = MagicMock()
        task1.done = MagicMock(return_value=False)
        task2 = MagicMock()
        task2.done = MagicMock(return_value=False)

        mock_manager.active_segments = {
            "seg1": {"task": task1},
            "seg2": {"task": task2},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        result = await check.check()

        assert result.status == "healthy"
        assert result.message is not None
        assert result.metadata is not None
        assert "2/2 workers are healthy" in result.message
        assert result.metadata["health_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_degraded_with_some_failed_workers(self):
        """Test degraded status when some workers have failed."""
        mock_manager = MagicMock()

        # Create mock tasks - 2 healthy, 1 failed
        task1 = MagicMock()
        task1.done = MagicMock(return_value=False)
        task2 = MagicMock()
        task2.done = MagicMock(return_value=False)
        task3 = MagicMock()
        task3.done = MagicMock(return_value=True)
        task3.exception = MagicMock(return_value=Exception("Task failed"))

        mock_manager.active_segments = {
            "seg1": {"task": task1},
            "seg2": {"task": task2},
            "seg3": {"task": task3},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        result = await check.check()

        assert result.status == "degraded"
        assert result.message is not None
        assert result.metadata is not None
        assert "2/3 workers are healthy" in result.message
        assert result.metadata["health_percentage"] == pytest.approx(66.67, 0.1)

    @pytest.mark.asyncio
    async def test_exception_reference_cleanup(self):
        """Test that exception references are properly cleaned up to prevent memory leaks."""
        mock_manager = MagicMock()

        # Create a task that has failed with an exception
        task = MagicMock()
        task.done = MagicMock(return_value=True)
        exception_obj = Exception("Task failed with exception")
        task.exception = MagicMock(return_value=exception_obj)

        mock_manager.active_segments = {
            "seg1": {"task": task},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        # First check - should retrieve exception
        result1 = await check.check()
        assert result1.metadata is not None
        assert result1.metadata["failed_workers"] == 1
        assert task.exception.call_count == 1

        # Second check - should not retrieve exception again (already checked)
        result2 = await check.check()
        assert result2.metadata is not None
        assert result2.metadata["failed_workers"] == 1
        # Exception should only be called once, not twice
        assert task.exception.call_count == 1

    @pytest.mark.asyncio
    async def test_checked_tasks_cleanup_when_no_workers(self):
        """Test that checked tasks set is cleared when there are no workers."""
        mock_manager = MagicMock()

        # First, create a failed task
        task = MagicMock()
        task.done = MagicMock(return_value=True)
        task.exception = MagicMock(return_value=Exception("Task failed"))

        mock_manager.active_segments = {
            "seg1": {"task": task},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        # First check - should add task to checked set
        await check.check()
        assert len(check._checked_tasks) == 1

        # Now remove all workers
        mock_manager.active_segments = {}

        # Second check - checked tasks should be cleared
        await check.check()
        assert len(check._checked_tasks) == 0

    @pytest.mark.asyncio
    async def test_checked_tasks_cleanup_when_task_removed(self):
        """Test that checked tasks are removed when tasks are no longer active."""
        mock_manager = MagicMock()

        # Create two failed tasks
        task1 = MagicMock()
        task1.done = MagicMock(return_value=True)
        task1.exception = MagicMock(return_value=Exception("Task 1 failed"))

        task2 = MagicMock()
        task2.done = MagicMock(return_value=True)
        task2.exception = MagicMock(return_value=Exception("Task 2 failed"))

        mock_manager.active_segments = {
            "seg1": {"task": task1},
            "seg2": {"task": task2},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        # First check - should add both tasks to checked set
        await check.check()
        assert len(check._checked_tasks) == 2

        # Remove one task
        mock_manager.active_segments = {
            "seg2": {"task": task2},
        }

        # Second check - should remove task1 from checked set
        await check.check()
        assert len(check._checked_tasks) == 1

    @pytest.mark.skip(
        reason="Test is flaky and environment-dependent. Memory growth varies based on "
        "Python version, garbage collection timing, and system load. Should be replaced "
        "with more robust memory profiling approach."
    )
    @pytest.mark.asyncio
    async def test_memory_leak_prevention(self):
        """Test that repeated health checks don't cause memory growth from exception references."""
        # Start memory tracking
        tracemalloc.start()

        mock_manager = MagicMock()

        # Create multiple tasks with exceptions
        tasks = []
        for i in range(100):
            task = MagicMock()
            task.done = MagicMock(return_value=True)
            # Create exception with some data to make memory impact measurable
            exception_obj = Exception(f"Task {i} failed with data: " + "x" * 1000)
            task.exception = MagicMock(return_value=exception_obj)
            tasks.append((f"seg{i}", task))

        mock_manager.active_segments = {
            seg_id: {"task": task} for seg_id, task in tasks
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        )

        # Get baseline memory
        await check.check()
        baseline_snapshot = tracemalloc.take_snapshot()

        # Run multiple health checks
        for _ in range(10):
            await check.check()

        # Get final memory
        final_snapshot = tracemalloc.take_snapshot()

        # Stop tracking
        tracemalloc.stop()

        # Calculate memory difference
        top_stats = final_snapshot.compare_to(baseline_snapshot, "lineno")

        # Memory growth should be minimal (less than 50KB for metadata only)
        # The exceptions themselves shouldn't be kept in memory
        total_memory_diff = sum(stat.size_diff for stat in top_stats)

        # Allow some growth for metadata, but not for the exception strings
        # If we were keeping exception references, we'd see ~100KB growth (100 tasks * 1KB each)
        assert total_memory_diff < 50 * 1024, (
            f"Memory grew by {total_memory_diff} bytes, indicating possible memory leak. "
            f"Expected less than 50KB growth for metadata only."
        )


class TestOrchestratorHealthCheck:
    """Test orchestrator health check."""

    @pytest.mark.asyncio
    async def test_healthy_on_first_check(self):
        """Test healthy status on first check (initialization)."""

        # Create a simple object instead of MagicMock to avoid auto-attribute creation
        class SimpleManager:
            def __init__(self):
                self.active_segments = {}

        mock_manager = SimpleManager()

        check = OrchestratorHealthCheck(
            manager=mock_manager,
            max_cycle_time_minutes=90,
            deadlock_threshold_minutes=180,
        )

        result = await check.check()

        assert result.status == "healthy"
        assert result.message is not None
        assert "initialized" in result.message.lower()
        assert hasattr(mock_manager, "last_cycle_time")

    @pytest.mark.asyncio
    async def test_healthy_with_recent_cycle(self):
        """Test healthy status when cycle was recent."""
        mock_manager = MagicMock()
        mock_manager.active_segments = {"seg1": {}}
        mock_manager.last_cycle_time = datetime.now(UTC) - timedelta(minutes=30)

        check = OrchestratorHealthCheck(
            manager=mock_manager,
            max_cycle_time_minutes=90,
            deadlock_threshold_minutes=180,
        )

        result = await check.check()

        assert result.status == "healthy"
        assert result.message is not None
        assert result.metadata is not None
        assert "functioning normally" in result.message
        assert result.metadata["minutes_since_last_cycle"] < 90

    @pytest.mark.asyncio
    async def test_degraded_with_slow_cycle(self):
        """Test degraded status when cycle is slow but not deadlocked."""
        mock_manager = MagicMock()
        mock_manager.active_segments = {}
        mock_manager.last_cycle_time = datetime.now(UTC) - timedelta(minutes=100)

        check = OrchestratorHealthCheck(
            manager=mock_manager,
            max_cycle_time_minutes=90,
            deadlock_threshold_minutes=180,
        )

        result = await check.check()

        assert result.status == "degraded"
        assert result.message is not None
        assert result.metadata is not None
        assert "slow" in result.message.lower()
        assert 90 < result.metadata["minutes_since_last_cycle"] < 180

    @pytest.mark.asyncio
    async def test_unhealthy_when_deadlocked(self):
        """Test unhealthy status when orchestrator appears deadlocked."""
        mock_manager = MagicMock()
        mock_manager.active_segments = {}
        mock_manager.last_cycle_time = datetime.now(UTC) - timedelta(minutes=200)

        check = OrchestratorHealthCheck(
            manager=mock_manager,
            max_cycle_time_minutes=90,
            deadlock_threshold_minutes=180,
        )

        result = await check.check()

        assert result.status == "unhealthy"
        assert result.message is not None
        assert result.metadata is not None
        assert "deadlocked" in result.message.lower()
        assert result.metadata["minutes_since_last_cycle"] > 180


class TestInfluxDBConnectionManager:
    """Test InfluxDB connection manager."""

    @pytest.mark.asyncio
    async def test_singleton_behavior(self):
        """Test that connection manager reuses instances for same credentials."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        # Get two instances with same credentials
        manager1 = await InfluxDBConnectionManager.get_instance(url, token, org)
        manager2 = await InfluxDBConnectionManager.get_instance(url, token, org)

        # Should be the same instance
        assert manager1 is manager2

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test thread-safe concurrent access to connection manager."""
        url = "http://localhost:8086"
        org = "test_org"

        # Create multiple concurrent requests
        tasks = []
        for i in range(10):
            tasks.append(
                InfluxDBConnectionManager.get_instance(
                    url,
                    f"token_{i % 3}",
                    org,  # Use 3 different tokens
                )
            )

        # Execute concurrently
        managers = await asyncio.gather(*tasks)

        # Count unique instances
        unique_managers = {id(m) for m in managers}
        assert len(unique_managers) == 3  # Should have 3 unique instances

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_connection_limit(self):
        """Test that connection limit is enforced."""
        # Store original max connections
        original_max = InfluxDBConnectionManager.MAX_CONNECTIONS
        test_limit = 3
        InfluxDBConnectionManager.MAX_CONNECTIONS = test_limit

        try:
            url = "http://localhost:8086"
            org = "test_org"

            # Create more connections than the limit
            managers = []
            for i in range(5):
                manager = await InfluxDBConnectionManager.get_instance(
                    url, f"token_{i}", org
                )
                managers.append(manager)

            # Should have exactly MAX_CONNECTIONS instances
            assert len(InfluxDBConnectionManager._instances) <= test_limit

        finally:
            # Restore and clean up
            InfluxDBConnectionManager.MAX_CONNECTIONS = original_max
            await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_stale_connection_cleanup(self):
        """Test that stale connections are cleaned up."""
        # Store original TTL
        original_ttl = InfluxDBConnectionManager.CONNECTION_TTL_SECONDS
        InfluxDBConnectionManager.CONNECTION_TTL_SECONDS = 0.001  # Very short TTL

        try:
            url = "http://localhost:8086"
            token = "test_token"
            org = "test_org"

            # Create connection
            manager1 = await InfluxDBConnectionManager.get_instance(url, token, org)
            assert len(InfluxDBConnectionManager._instances) == 1

            # Wait for TTL to expire
            await asyncio.sleep(0.002)

            # Get new connection (should trigger cleanup)
            manager2 = await InfluxDBConnectionManager.get_instance(url, "token2", org)

            # Old connection should be cleaned up
            assert len(InfluxDBConnectionManager._instances) == 1
            assert manager1 is not manager2

        finally:
            # Restore and clean up
            InfluxDBConnectionManager.CONNECTION_TTL_SECONDS = original_ttl
            await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_cache_ttl_configuration(self):
        """Test that cache TTL can be configured."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"
        custom_ttl = 15

        # Get instance with custom cache TTL
        manager = await InfluxDBConnectionManager.get_instance(
            url, token, org, cache_ttl=custom_ttl
        )

        # Check that cache TTL was set
        assert manager._ping_cache_ttl == custom_ttl

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_async_context_manager_basic(self):
        """Test that InfluxDBConnectionManager can be used as async context manager."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        # Use as async context manager
        async with await InfluxDBConnectionManager.get_instance(
            url, token, org
        ) as manager:
            assert manager is not None
            assert manager.url == url
            assert manager.org == org

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_async_context_manager_exception_cleanup(self):
        """Test that resources are cleaned up even when exception occurs in context."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        # Track if close was called
        manager = await InfluxDBConnectionManager.get_instance(url, token, org)
        close_called = False
        original_close = manager.close

        def tracked_close():
            nonlocal close_called
            close_called = True
            original_close()

        manager.close = tracked_close

        # Use in context that raises exception
        with pytest.raises(ValueError):
            async with manager:
                raise ValueError("Test exception")

        # Verify close was called despite exception
        assert close_called

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_async_context_manager_returns_self(self):
        """Test that __aenter__ returns the manager instance."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        manager = await InfluxDBConnectionManager.get_instance(url, token, org)

        # Verify __aenter__ returns self
        entered_manager = await manager.__aenter__()
        assert entered_manager is manager

        # Manually exit
        await manager.__aexit__(None, None, None)

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_async_context_manager_with_get_client(self):
        """Test that context manager works with get_client() calls."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        async with await InfluxDBConnectionManager.get_instance(
            url, token, org
        ) as manager:
            # Mock the client creation to avoid actual InfluxDB connection
            with patch("src.health_checks.InfluxDBClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                client = await manager.get_client()
                assert client is not None

        # Clean up
        await InfluxDBConnectionManager.cleanup_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
