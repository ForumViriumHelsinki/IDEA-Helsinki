"""
Unit tests for IDEA Helsinki health checks.
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.health_checks import (
    FCDDatabaseHealthCheck,
    ValidationDatabaseHealthCheck,
    DisturbanceDataHealthCheck,
    WorkerStatusHealthCheck,
    OrchestratorHealthCheck,
)
from idea_shared.health.models import HealthCheckResult


class TestFCDDatabaseHealthCheck:
    """Test FCD database health check."""

    @pytest.mark.asyncio
    async def test_healthy_with_recent_data(self):
        """Test healthy status when database is accessible and has recent data."""
        with patch("src.health_checks.InfluxDBClient") as mock_client:
            # Setup mocks
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            mock_instance.ping.return_value = True

            # Mock query result with recent data
            mock_table = MagicMock()
            mock_table.records = [MagicMock()]
            mock_instance.query_api.return_value.query.return_value = [mock_table]

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1
            )

            result = await check.check()

            assert result.status == "healthy"
            assert "recent data" in result.message.lower()
            assert result.metadata["has_recent_data"] is True

    @pytest.mark.asyncio
    async def test_degraded_with_no_recent_data(self):
        """Test degraded status when database is accessible but has no recent data."""
        with patch("src.health_checks.InfluxDBClient") as mock_client:
            # Setup mocks
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            mock_instance.ping.return_value = True

            # Mock query result with no data
            mock_table = MagicMock()
            mock_table.records = []
            mock_instance.query_api.return_value.query.return_value = [mock_table]

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket",
                data_freshness_hours=1
            )

            result = await check.check()

            assert result.status == "degraded"
            assert "no data" in result.message.lower()
            assert result.metadata["has_recent_data"] is False

    @pytest.mark.asyncio
    async def test_unhealthy_on_connection_failure(self):
        """Test unhealthy status when database connection fails."""
        with patch("src.health_checks.InfluxDBClient") as mock_client:
            # Setup mocks
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            mock_instance.ping.return_value = False

            check = FCDDatabaseHealthCheck(
                url="http://localhost:8086",
                token="test_token",
                org="test_org",
                bucket="test_bucket"
            )

            result = await check.check()

            assert result.status == "unhealthy"
            assert "Failed to ping" in result.message


class TestDisturbanceDataHealthCheck:
    """Test disturbance data health check."""

    @pytest.mark.asyncio
    async def test_healthy_with_fresh_valid_data(self):
        """Test healthy status with fresh and valid JSON data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Write valid JSON with segments
            data = {
                "segmentId": {
                    "seg1": {"detailedCollisions": []},
                    "seg2": {"detailedCollisions": []}
                }
            }
            json.dump(data, f)
            f.flush()

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name,
                    max_age_minutes=120
                )

                result = await check.check()

                assert result.status == "healthy"
                assert "available and fresh" in result.message
                assert result.metadata["segment_count"] == 2
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_degraded_with_stale_data(self):
        """Test degraded status when data file is stale."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Write valid JSON
            json.dump({"segmentId": {}}, f)
            f.flush()

            # Make file appear old
            old_time = (datetime.now() - timedelta(hours=3)).timestamp()
            os.utime(f.name, (old_time, old_time))

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name,
                    max_age_minutes=120,
                    critical=False
                )

                result = await check.check()

                assert result.status == "degraded"
                assert "stale" in result.message.lower()
                assert result.metadata["file_age_minutes"] > 120
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_unhealthy_with_invalid_json(self):
        """Test unhealthy status with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Write invalid JSON
            f.write("{ invalid json }")
            f.flush()

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name,
                    max_age_minutes=120
                )

                result = await check.check()

                assert result.status == "unhealthy"
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
            health_threshold_percent=80.0
        )

        result = await check.check()

        assert result.status == "healthy"
        assert "no disturbances" in result.message.lower()
        assert result.metadata["total_workers"] == 0

    @pytest.mark.asyncio
    async def test_healthy_with_all_workers_running(self):
        """Test healthy status when all workers are running."""
        mock_manager = MagicMock()

        # Create mock tasks
        task1 = AsyncMock()
        task1.done.return_value = False
        task2 = AsyncMock()
        task2.done.return_value = False

        mock_manager.active_segments = {
            "seg1": {"task": task1},
            "seg2": {"task": task2}
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=80.0
        )

        result = await check.check()

        assert result.status == "healthy"
        assert "2/2 workers are healthy" in result.message
        assert result.metadata["health_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_degraded_with_some_failed_workers(self):
        """Test degraded status when some workers have failed."""
        mock_manager = MagicMock()

        # Create mock tasks - 2 healthy, 1 failed
        task1 = AsyncMock()
        task1.done.return_value = False
        task2 = AsyncMock()
        task2.done.return_value = False
        task3 = AsyncMock()
        task3.done.return_value = True
        task3.exception.side_effect = Exception("Task failed")

        mock_manager.active_segments = {
            "seg1": {"task": task1},
            "seg2": {"task": task2},
            "seg3": {"task": task3}
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager,
            health_threshold_percent=80.0
        )

        result = await check.check()

        assert result.status == "degraded"
        assert "2/3 workers are healthy" in result.message
        assert result.metadata["health_percentage"] == pytest.approx(66.67, 0.1)


class TestOrchestratorHealthCheck:
    """Test orchestrator health check."""

    @pytest.mark.asyncio
    async def test_healthy_on_first_check(self):
        """Test healthy status on first check (initialization)."""
        mock_manager = MagicMock()
        mock_manager.active_segments = {}

        check = OrchestratorHealthCheck(
            manager=mock_manager,
            max_cycle_time_minutes=90,
            deadlock_threshold_minutes=180
        )

        result = await check.check()

        assert result.status == "healthy"
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
            deadlock_threshold_minutes=180
        )

        result = await check.check()

        assert result.status == "healthy"
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
            deadlock_threshold_minutes=180
        )

        result = await check.check()

        assert result.status == "degraded"
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
            deadlock_threshold_minutes=180
        )

        result = await check.check()

        assert result.status == "unhealthy"
        assert "deadlocked" in result.message.lower()
        assert result.metadata["minutes_since_last_cycle"] > 180


if __name__ == "__main__":
    pytest.main([__file__, "-v"])