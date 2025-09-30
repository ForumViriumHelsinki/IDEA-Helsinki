"""Integration tests for FCD Manager health server."""

import asyncio
import json
import signal
import sys
import tempfile
import time
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
            assert response.json()["status"] == "alive"
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
            assert data["status"] == "alive"
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
        update_check.startup_time = update_check.startup_time - asyncio.timedelta(
            minutes=15
        )

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
