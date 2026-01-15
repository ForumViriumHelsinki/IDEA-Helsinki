"""Integration tests for FCD Manager health server."""

import json
import signal
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from idea_shared.health.server import HealthServer

from health_checks import (
    ProcessingPipelineHealthCheck,
    SegmentMappingFreshnessHealthCheck,
    UpdateCycleHealthCheck,
)


class TestHealthServerIntegration:
    """Integration tests for the health server."""

    @pytest.fixture
    def temp_mapping_file(self):
        """Create a temporary mapping file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test_segment": {"geometry": {}, "properties": {}}}, f)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    @pytest.fixture
    def health_server(self, temp_mapping_file):
        """Create a health server instance for testing."""
        server = HealthServer(
            port=18080,  # Use a non-standard port for testing
            app_name="Test FCD Manager",
            enable_metrics=True,
        )

        # Add test health checks
        update_check = UpdateCycleHealthCheck(
            healthy_threshold_minutes=10,
            degraded_threshold_minutes=30,
        )
        server.add_check("update_cycle", update_check)

        mapping_check = SegmentMappingFreshnessHealthCheck(
            mapping_file_path=temp_mapping_file,
            max_age_minutes=15,
        )
        server.add_check("mapping_freshness", mapping_check)

        pipeline_check = ProcessingPipelineHealthCheck()
        server.add_check("processing_pipeline", pipeline_check)

        yield server, update_check, pipeline_check

        # Cleanup
        server.stop()

    def test_health_server_startup_and_shutdown(self, health_server):
        """Test that health server starts and stops correctly."""
        server, _, _ = health_server

        # Start the server
        server.start_background()

        # Give the server time to start
        time.sleep(2)

        # Check that the server is responding
        try:
            response = requests.get("http://localhost:18080/healthz", timeout=5)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Health server not responding: {e}")

        # Stop the server
        server.stop()
        time.sleep(1)

        # Server should no longer respond
        with pytest.raises(requests.exceptions.ConnectionError):
            requests.get("http://localhost:18080/healthz", timeout=1)

    def test_liveness_endpoint(self, health_server):
        """Test the /healthz liveness endpoint."""
        server, _, _ = health_server
        server.start_background()
        time.sleep(2)

        try:
            response = requests.get("http://localhost:18080/healthz", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "timestamp" in data
        finally:
            server.stop()

    def test_readiness_endpoint_initial_state(self, health_server):
        """Test the /ready endpoint in initial state."""
        server, _, _ = health_server
        server.start_background()
        time.sleep(2)

        try:
            response = requests.get("http://localhost:18080/ready", timeout=5)
            # During startup grace period, update_cycle should be healthy
            # mapping_freshness should be healthy (fresh file)
            # processing_pipeline should be healthy (not started)
            assert response.status_code == 200
            data = response.json()
            assert data["ready"] is True
            assert "checks" in data
            assert data["checks"]["update_cycle"] == "healthy"
            assert data["checks"]["mapping_freshness"] == "healthy"
            assert data["checks"]["processing_pipeline"] == "healthy"
        finally:
            server.stop()

    def test_readiness_endpoint_after_update(self, health_server):
        """Test the /ready endpoint after simulating updates."""
        server, update_check, pipeline_check = health_server
        server.start_background()
        time.sleep(2)

        try:
            # Simulate successful update
            update_check.update_timestamp()
            pipeline_check.record_processing_start()
            pipeline_check.record_processing_complete(5)

            response = requests.get("http://localhost:18080/ready", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data["ready"] is True
            assert data["checks"]["update_cycle"] == "healthy"
            assert data["checks"]["processing_pipeline"] == "healthy"
        finally:
            server.stop()

    def test_readiness_endpoint_degraded_state(self, health_server):
        """Test the /ready endpoint when checks are degraded."""
        server, update_check, pipeline_check = health_server

        # Simulate grace period has passed and no updates
        update_check.startup_time = update_check.startup_time - timedelta(minutes=15)

        # Simulate a recent error
        pipeline_check.record_error("Test error")

        server.start_background()
        time.sleep(2)

        try:
            response = requests.get("http://localhost:18080/ready", timeout=5)
            data = response.json()

            # Should still be ready even with degraded checks (non-critical)
            assert data["ready"] is True
            assert (
                data["checks"]["update_cycle"] == "unhealthy"
            )  # No updates after grace period
            assert data["checks"]["processing_pipeline"] == "degraded"  # Recent error
        finally:
            server.stop()

    def test_health_detail_endpoint(self, health_server):
        """Test the /health/detail endpoint."""
        server, update_check, _ = health_server
        update_check.update_timestamp()

        server.start_background()
        time.sleep(2)

        try:
            response = requests.get("http://localhost:18080/health/detail", timeout=5)
            assert response.status_code == 200
            data = response.json()

            assert "service" in data
            assert data["service"] == "Test FCD Manager"
            assert "timestamp" in data
            assert "checks" in data

            # Check detailed info for update_cycle
            update_detail = data["checks"]["update_cycle"]
            assert update_detail["status"] == "healthy"
            assert "message" in update_detail
            assert "metadata" in update_detail
            assert update_detail["critical"] is False
        finally:
            server.stop()

    def test_metrics_endpoint(self, health_server):
        """Test the /metrics endpoint when enabled."""
        server, _, _ = health_server
        server.start_background()
        time.sleep(2)

        try:
            response = requests.get("http://localhost:18080/metrics", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert "metrics" in data
            assert data["metrics"]["health_checks_total"] == 3
            assert data["metrics"]["service_name"] == "Test FCD Manager"
        finally:
            server.stop()

    def test_startup_endpoint(self, health_server):
        """Test the /startup endpoint."""
        server, _, _ = health_server
        server.start_background()
        time.sleep(2)

        try:
            response = requests.get("http://localhost:18080/startup", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data["ready"] is True
            assert "checks" in data
        finally:
            server.stop()

    def test_concurrent_health_checks(self, health_server):
        """Test that multiple concurrent health check requests are handled properly."""
        server, _, _ = health_server
        server.start_background()
        time.sleep(2)

        try:
            # Make multiple concurrent requests
            import concurrent.futures

            def make_request(endpoint):
                return requests.get(f"http://localhost:18080{endpoint}", timeout=5)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(make_request, "/healthz"),
                    executor.submit(make_request, "/ready"),
                    executor.submit(make_request, "/health/detail"),
                    executor.submit(make_request, "/metrics"),
                    executor.submit(make_request, "/startup"),
                ] * 2  # Make 10 total requests

                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            # All requests should succeed
            assert all(r.status_code in [200, 503] for r in results)
        finally:
            server.stop()

    def test_health_check_caching(self, health_server):
        """Test that health check results are cached appropriately."""
        server, update_check, _ = health_server

        # Set a known state
        update_check.update_timestamp()

        server.start_background()
        time.sleep(2)

        try:
            # Make first request
            response1 = requests.get("http://localhost:18080/health/detail", timeout=5)
            data1 = response1.json()

            # Make second request immediately (should be cached)
            response2 = requests.get("http://localhost:18080/health/detail", timeout=5)
            data2 = response2.json()

            # Results should be identical due to caching
            assert data1["checks"]["update_cycle"] == data2["checks"]["update_cycle"]

            # Wait for cache to expire (cache_ttl is 5 seconds for update_cycle)
            time.sleep(6)

            # Make third request (cache should be expired)
            response3 = requests.get("http://localhost:18080/health/detail", timeout=5)
            data3 = response3.json()

            # Timestamp should be different
            assert data1["timestamp"] != data3["timestamp"]
        finally:
            server.stop()


class TestStartupSpecificChecks:
    """Test startup-specific health checks (separate from readiness checks)."""

    @pytest.fixture
    def server_with_startup_checks(self):
        """Create a health server with separate startup and readiness checks."""
        from idea_shared.health.checks import HealthCheck
        from idea_shared.health.models import HealthCheckResult

        # Create a simple mock check that always passes
        class AlwaysHealthyCheck(HealthCheck):
            async def check(self) -> HealthCheckResult:
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message="Always healthy",
                )

        # Create a check that always fails
        class AlwaysUnhealthyCheck(HealthCheck):
            async def check(self) -> HealthCheckResult:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="Always unhealthy",
                )

        server = HealthServer(
            port=18081,  # Different port to avoid conflicts
            app_name="Test Startup Checks",
        )

        # Add a critical check that fails (simulates missing mapping file at startup)
        failing_check = AlwaysUnhealthyCheck(
            name="mapping_integrity",
            critical=True,
        )
        server.add_check("mapping_integrity", failing_check)

        # Add startup-only checks that pass (simulates connectivity checks)
        startup_check = AlwaysHealthyCheck(
            name="connectivity",
            critical=True,
        )
        server.add_check("connectivity", startup_check, startup_only=True)

        yield server

        server.stop()

    def test_startup_uses_startup_only_checks(self, server_with_startup_checks):
        """Test that /startup endpoint uses startup_only checks, not regular checks."""
        server = server_with_startup_checks
        server.start_background()
        time.sleep(2)

        try:
            # /startup should pass because it uses startup_only checks
            response = requests.get("http://localhost:18081/startup", timeout=5)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["ready"] is True
            assert "connectivity" in data["checks"]
            # mapping_integrity should NOT be in startup checks
            assert "mapping_integrity" not in data["checks"]
        finally:
            server.stop()

    def test_readiness_uses_regular_checks(self, server_with_startup_checks):
        """Test that /ready endpoint uses regular checks (not startup_only)."""
        server = server_with_startup_checks
        server.start_background()
        time.sleep(2)

        try:
            # /ready should fail because mapping_integrity is critical and unhealthy
            response = requests.get("http://localhost:18081/ready", timeout=5)
            assert response.status_code == 503, f"Expected 503, got {response.status_code}"
            data = response.json()
            assert data["ready"] is False
            assert data["checks"]["mapping_integrity"] == "unhealthy"
            # startup_only checks should NOT appear in readiness
            assert "connectivity" not in data["checks"]
        finally:
            server.stop()

    def test_startup_success_during_initial_sync(self):
        """
        Test scenario: startup passes while initial data sync is running.

        This simulates the real-world case where:
        - Azure/InfluxDB connectivity checks pass (startup_only)
        - Mapping integrity check fails (regular check) because file doesn't exist yet
        - Pod should pass startup probes but fail readiness until sync completes
        """
        from idea_shared.health.checks import HealthCheck
        from idea_shared.health.models import HealthCheckResult

        class ConnectivityCheck(HealthCheck):
            """Simulates Azure/InfluxDB connectivity check."""

            async def check(self) -> HealthCheckResult:
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message="Service reachable",
                )

        class MappingFileCheck(HealthCheck):
            """Simulates mapping file check during initial sync."""

            def __init__(self, file_exists: bool = False, **kwargs):
                super().__init__(**kwargs)
                self.file_exists = file_exists

            async def check(self) -> HealthCheckResult:
                if self.file_exists:
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="Mapping file exists",
                    )
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="Mapping file not found (initial sync in progress)",
                )

        server = HealthServer(
            port=18082,
            app_name="Initial Sync Simulation",
        )

        # Simulate startup checks (connectivity only)
        azure_startup = ConnectivityCheck(name="azure", critical=True)
        influx_startup = ConnectivityCheck(name="influxdb", critical=True)
        server.add_check("azure", azure_startup, startup_only=True)
        server.add_check("influxdb", influx_startup, startup_only=True)

        # Simulate regular readiness checks
        azure_ready = ConnectivityCheck(name="azure", critical=True)
        influx_ready = ConnectivityCheck(name="influxdb", critical=True)
        mapping_check = MappingFileCheck(
            name="mapping", file_exists=False, critical=True
        )
        server.add_check("azure", azure_ready)
        server.add_check("influxdb", influx_ready)
        server.add_check("mapping", mapping_check)

        server.start_background()
        time.sleep(2)

        try:
            # Startup should pass (only connectivity checks)
            startup_response = requests.get("http://localhost:18082/startup", timeout=5)
            assert startup_response.status_code == 200
            startup_data = startup_response.json()
            assert startup_data["ready"] is True

            # Readiness should fail (mapping file doesn't exist)
            ready_response = requests.get("http://localhost:18082/ready", timeout=5)
            assert ready_response.status_code == 503
            ready_data = ready_response.json()
            assert ready_data["ready"] is False
            assert ready_data["checks"]["mapping"] == "unhealthy"

            # Simulate sync completion: mapping file now exists
            mapping_check.file_exists = True

            # Now readiness should pass
            ready_response2 = requests.get("http://localhost:18082/ready", timeout=5)
            assert ready_response2.status_code == 200
            ready_data2 = ready_response2.json()
            assert ready_data2["ready"] is True
        finally:
            server.stop()


class TestSignalHandling:
    """Test signal handling for graceful shutdown."""

    def test_graceful_shutdown_sigterm(self):
        """Test that SIGTERM triggers graceful shutdown."""
        with patch("sys.exit") as mock_exit:
            from main import handle_shutdown

            # Mock health server
            with patch("main.health_server") as mock_server:
                mock_server.stop = MagicMock()

                # Call signal handler
                handle_shutdown(signal.SIGTERM, None)

                # Verify shutdown was initiated
                mock_server.stop.assert_called_once()
                mock_exit.assert_called_once_with(0)

    def test_graceful_shutdown_sigint(self):
        """Test that SIGINT triggers graceful shutdown."""
        with patch("sys.exit") as mock_exit:
            from main import handle_shutdown

            # Mock health server
            with patch("main.health_server") as mock_server:
                mock_server.stop = MagicMock()

                # Call signal handler
                handle_shutdown(signal.SIGINT, None)

                # Verify shutdown was initiated
                mock_server.stop.assert_called_once()
                mock_exit.assert_called_once_with(0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
