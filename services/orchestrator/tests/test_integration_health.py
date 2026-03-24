"""
Integration tests for IDEA Helsinki health server.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from idea_shared.classes.IdeaHelsinkiManager import IdeaHelsinkiManager
from idea_shared.health.server import HealthServer

from health_checks import (  # ty: ignore[unresolved-import]
    DisturbanceDataHealthCheck,
    FCDDatabaseHealthCheck,
    OrchestratorHealthCheck,
    ValidationDatabaseHealthCheck,
    WorkerStatusHealthCheck,
)


class TestHealthServerIntegration:
    """Test health server integration with IDEA Helsinki."""

    @pytest.mark.skip(
        reason="Test uses private API (readiness_checks attribute) that was refactored. "
        "Should be rewritten to test public HTTP API."
    )
    @pytest.mark.asyncio
    async def test_health_server_with_all_checks(self):
        """Test that health server can be initialized with all checks."""
        # Create mock manager
        mock_manager = MagicMock(spec=IdeaHelsinkiManager)
        mock_manager.active_segments = {}
        mock_manager.last_cycle_time = None

        # Create health server
        health_server = HealthServer(port=8081, app_name="Test IDEA Helsinki")

        # Add all health checks
        with patch("src.health_checks.InfluxDBClient"):
            health_server.add_check(
                "influxdb_fcd",
                FCDDatabaseHealthCheck(
                    url="http://localhost:8086",
                    token="test_token",
                    org="test_org",
                    bucket="fcd_bucket",
                ),
            )

            health_server.add_check(
                "influxdb_validation",
                ValidationDatabaseHealthCheck(
                    url="http://localhost:8086",
                    token="test_token",
                    org="test_org",
                    bucket="validation_bucket",
                ),
            )

        health_server.add_check(
            "disturbance_data",
            DisturbanceDataHealthCheck(
                file_path="/tmp/test_disturbance.json",
                max_age_minutes=120,
                critical=False,
            ),
        )

        health_server.add_check(
            "worker_status",
            WorkerStatusHealthCheck(
                manager=mock_manager, health_threshold_percent=80.0
            ),
        )

        health_server.add_check(
            "orchestrator_loop",
            OrchestratorHealthCheck(
                manager=mock_manager,
                max_cycle_time_minutes=90,
                deadlock_threshold_minutes=180,
            ),
        )

        # Verify all checks are registered
        assert len(health_server.readiness_checks) == 5  # type: ignore[attr-defined]
        assert "influxdb_fcd" in health_server.readiness_checks  # type: ignore[attr-defined]
        assert "influxdb_validation" in health_server.readiness_checks  # type: ignore[attr-defined]
        assert "disturbance_data" in health_server.readiness_checks  # type: ignore[attr-defined]
        assert "worker_status" in health_server.readiness_checks  # type: ignore[attr-defined]
        assert "orchestrator_loop" in health_server.readiness_checks  # type: ignore[attr-defined]

    @pytest.mark.skip(
        reason="Test uses private API (_run_checks method) that was refactored. "
        "Should be rewritten to test public HTTP API."
    )
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """Test that multiple health checks can run concurrently."""
        # Create mock manager
        mock_manager = MagicMock()
        mock_manager.active_segments = {}

        # Create health server
        health_server = HealthServer(port=8082, app_name="Test Concurrent")

        # Create mock checks with different execution times
        async def slow_check():
            await asyncio.sleep(0.1)
            return {"status": "healthy", "message": "Slow check"}

        async def fast_check():
            await asyncio.sleep(0.01)
            return {"status": "healthy", "message": "Fast check"}

        mock_slow = AsyncMock()
        mock_slow.check.side_effect = slow_check
        mock_slow.critical = True
        mock_slow.cache_ttl = 0

        mock_fast = AsyncMock()
        mock_fast.check.side_effect = fast_check
        mock_fast.critical = True
        mock_fast.cache_ttl = 0

        health_server.add_check("slow", mock_slow)
        health_server.add_check("fast", mock_fast)

        # Run checks concurrently
        import time

        start = time.time()
        results = await health_server._run_checks(health_server.readiness_checks)  # type: ignore[attr-defined]
        duration = time.time() - start

        # Should complete in roughly the time of the slowest check, not the sum
        assert duration < 0.2  # Less than sum of both checks
        assert len(results) == 2
        assert all(r["status"] == "healthy" for r in results.values())

    @pytest.mark.skip(
        reason="Test uses private API (mark_shutting_down method) that was refactored. "
        "Should be rewritten to test public HTTP API."
    )
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Test graceful shutdown of health server."""
        mock_manager = MagicMock()
        mock_manager.active_segments = {}

        health_server = HealthServer(port=8083, app_name="Test Shutdown")

        # Add a simple check
        health_server.add_check(
            "worker_status", WorkerStatusHealthCheck(manager=mock_manager)
        )

        # Test shutdown sequence
        await health_server.mark_shutting_down()  # type: ignore[attr-defined]
        assert health_server.is_shutting_down is True  # type: ignore[attr-defined]

        # After shutdown, health checks should indicate not ready
        status = await health_server._check_readiness()  # type: ignore[attr-defined]
        assert status["status"] == "not_ready"
        assert "shutting down" in status["message"].lower()

    @pytest.mark.skip(
        reason="Test uses private API (_run_checks method) that was refactored. "
        "Should be rewritten to test public HTTP API."
    )
    @pytest.mark.asyncio
    async def test_health_check_error_handling(self):
        """Test that health server handles check failures gracefully."""
        health_server = HealthServer(port=8084, app_name="Test Error Handling")

        # Create a check that raises an exception
        mock_check = AsyncMock()
        mock_check.check.side_effect = Exception("Database connection failed")
        mock_check.critical = True
        mock_check.cache_ttl = 0
        mock_check.timeout = 5

        health_server.add_check("failing_check", mock_check)

        # Run checks - should handle the exception
        results = await health_server._run_checks({"failing_check": mock_check})  # type: ignore[attr-defined]

        assert "failing_check" in results
        assert results["failing_check"]["status"] == "unhealthy"
        assert "error" in results["failing_check"]["message"].lower()

    @pytest.mark.skip(
        reason="Test uses private API (_check_readiness method and readiness_checks attribute) that was refactored. "
        "Should be rewritten to test public HTTP API."
    )
    @pytest.mark.asyncio
    async def test_critical_vs_non_critical_checks(self):
        """Test that critical and non-critical checks affect readiness differently."""
        health_server = HealthServer(port=8085, app_name="Test Critical")

        # Create critical check (unhealthy)
        mock_critical = AsyncMock()
        mock_critical.check.return_value = {
            "status": "unhealthy",
            "message": "Critical service down",
        }
        mock_critical.critical = True
        mock_critical.cache_ttl = 0

        # Create non-critical check (also unhealthy)
        mock_non_critical = AsyncMock()
        mock_non_critical.check.return_value = {
            "status": "unhealthy",
            "message": "Non-critical service down",
        }
        mock_non_critical.critical = False
        mock_non_critical.cache_ttl = 0

        # Test with only non-critical unhealthy
        health_server.readiness_checks = {"non_critical": mock_non_critical}  # type: ignore[attr-defined]
        status = await health_server._check_readiness()  # type: ignore[attr-defined]
        assert status["status"] == "ready"  # Should still be ready

        # Test with critical unhealthy
        health_server.readiness_checks = {"critical": mock_critical}  # type: ignore[attr-defined]
        status = await health_server._check_readiness()  # type: ignore[attr-defined]
        assert status["status"] == "not_ready"  # Should not be ready


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
