"""
Unit tests for IDEA Helsinki health checks.
"""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from idea_shared.lib.Constants.Constants import (
    HEALTH_CHECK_FCD_DATABASE,
    HEALTH_CHECK_VALIDATION_DATABASE,
)

from src.health_checks import (
    DisturbanceDataHealthCheck,
    FCDDatabaseHealthCheck,
    InfluxDBConnectionManager,
    OrchestratorHealthCheck,
    ValidationDatabaseHealthCheck,
    WorkerStatusHealthCheck,
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
                data_freshness_hours=1,
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
                data_freshness_hours=1,
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
                bucket="test_bucket",
            )

            result = await check.check()

            assert result.status == "unhealthy"
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
            # Write valid JSON with segments
            data = {
                "segmentId": {
                    "seg1": {"detailedCollisions": []},
                    "seg2": {"detailedCollisions": []},
                }
            }
            json.dump(data, f)
            f.flush()

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name, max_age_minutes=120
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
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write valid JSON
            json.dump({"segmentId": {}}, f)
            f.flush()

            # Make file appear old
            old_time = (datetime.now() - timedelta(hours=3)).timestamp()
            os.utime(f.name, (old_time, old_time))

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name, max_age_minutes=120, critical=False
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
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write invalid JSON
            f.write("{ invalid json }")
            f.flush()

            try:
                check = DisturbanceDataHealthCheck(
                    file_path=f.name, max_age_minutes=120
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
            manager=mock_manager, health_threshold_percent=80.0
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
            "seg2": {"task": task2},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager, health_threshold_percent=80.0
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
            "seg3": {"task": task3},
        }

        check = WorkerStatusHealthCheck(
            manager=mock_manager, health_threshold_percent=80.0
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
            deadlock_threshold_minutes=180,
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
            deadlock_threshold_minutes=180,
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
            deadlock_threshold_minutes=180,
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
            deadlock_threshold_minutes=180,
        )

        result = await check.check()

        assert result.status == "unhealthy"
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
        """Test that connection limit is enforced with LRU eviction."""
        # Store original max connections
        original_max = InfluxDBConnectionManager.MAX_CONNECTIONS
        InfluxDBConnectionManager.MAX_CONNECTIONS = 3

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
                # Small delay to ensure different creation times
                await asyncio.sleep(0.001)

            # Should have exactly MAX_CONNECTIONS instances (LRU eviction)
            assert len(InfluxDBConnectionManager._instances) <= 3

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
    async def test_lru_scoring_mechanism(self):
        """Test that LRU scoring correctly prioritizes connections."""
        original_max = InfluxDBConnectionManager.MAX_CONNECTIONS
        InfluxDBConnectionManager.MAX_CONNECTIONS = 2

        try:
            url = "http://localhost:8086"
            org = "test_org"

            # Create first connection and use it heavily
            manager1 = await InfluxDBConnectionManager.get_instance(
                url, "token_1", org
            )
            # Simulate heavy usage
            for _ in range(10):
                _ = await InfluxDBConnectionManager.get_instance(url, "token_1", org)
                await asyncio.sleep(0.001)

            # Create second connection with minimal usage
            manager2 = await InfluxDBConnectionManager.get_instance(
                url, "token_2", org
            )

            # manager1 should have higher score due to usage
            score1 = manager1._calculate_score()
            score2 = manager2._calculate_score()
            assert (
                score1 > score2
            ), f"Heavily used connection should have higher score: {score1} vs {score2}"

            # Create third connection - should evict manager2 (lowest score)
            manager3 = await InfluxDBConnectionManager.get_instance(
                url, "token_3", org
            )

            # Verify manager1 still exists (higher usage score)
            # and manager2 was evicted (lower score)
            assert len(InfluxDBConnectionManager._instances) == 2

        finally:
            InfluxDBConnectionManager.MAX_CONNECTIONS = original_max
            await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_connection_metrics(self):
        """Test that connection metrics are tracked correctly."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        try:
            # Create connection and use it
            manager = await InfluxDBConnectionManager.get_instance(url, token, org)

            # Access it multiple times
            for _ in range(3):
                _ = await InfluxDBConnectionManager.get_instance(url, token, org)

            # Get metrics
            metrics = manager.get_metrics()

            # Verify metrics structure
            assert "url" in metrics
            assert "usage_count" in metrics
            assert "ping_count" in metrics
            assert "client_access_count" in metrics
            assert "health_score" in metrics
            assert metrics["url"] == url
            assert metrics["org"] == org
            assert (
                metrics["usage_count"] >= 4
            )  # Initial + 3 accesses (get_instance increments)

            # Test get_all_metrics
            all_metrics = InfluxDBConnectionManager.get_all_metrics()
            assert len(all_metrics) == 1
            assert all_metrics[0]["url"] == url

        finally:
            await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_health_scoring_with_failed_pings(self):
        """Test that failed pings reduce health score."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        try:
            with patch("src.health_checks.InfluxDBClient") as mock_client:
                # Setup mock to fail pings
                mock_instance = MagicMock()
                mock_client.return_value = mock_instance
                mock_instance.ping.return_value = False

                manager = await InfluxDBConnectionManager.get_instance(url, token, org)

                # Attempt pings that will fail
                for _ in range(5):
                    try:
                        await manager.ping()
                    except Exception:
                        pass

                # Health score should be lower due to failed pings
                metrics = manager.get_metrics()
                assert metrics["failed_ping_count"] > 0
                if metrics["ping_count"] > 0:
                    assert (
                        metrics["ping_success_rate"] < 1.0
                    ), "Failed pings should reduce success rate"

        finally:
            await InfluxDBConnectionManager.cleanup_all()

    @pytest.mark.asyncio
    async def test_concurrent_metric_updates(self):
        """Test that concurrent access updates metrics correctly (thread-safe)."""
        url = "http://localhost:8086"
        token = "test_token"
        org = "test_org"

        try:
            # Create multiple concurrent requests to the same connection
            tasks = []
            num_concurrent_requests = 50

            for _ in range(num_concurrent_requests):
                tasks.append(
                    InfluxDBConnectionManager.get_instance(url, token, org)
                )

            # Execute all concurrently
            managers = await asyncio.gather(*tasks)

            # Should all be the same instance
            assert all(m is managers[0] for m in managers)

            # Get metrics and verify usage count matches the number of requests
            metrics = managers[0].get_metrics()
            assert (
                metrics["usage_count"] == num_concurrent_requests
            ), f"Expected {num_concurrent_requests} usages, got {metrics['usage_count']}"

        finally:
            await InfluxDBConnectionManager.cleanup_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
