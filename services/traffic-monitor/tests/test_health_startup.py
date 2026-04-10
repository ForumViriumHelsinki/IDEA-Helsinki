"""Tests for startup-specific health checks in traffic-monitor service.

These tests verify that the traffic-monitor properly separates startup
and readiness checks, allowing pods to pass startup probes while
waiting for the FCD mapping file (created by fcd-manager).

Issue: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/135
"""

import time

import pytest
import requests
from idea_shared.health.checks import HealthCheck
from idea_shared.health.models import HealthCheckResult
from idea_shared.health.server import HealthServer


class AlwaysHealthyCheck(HealthCheck):
    """Test check that always returns healthy."""

    async def check(self) -> HealthCheckResult:
        """Return a healthy result unconditionally."""
        return HealthCheckResult(
            name=self.name,
            status="healthy",
            message="Always healthy",
        )


class AlwaysUnhealthyCheck(HealthCheck):
    """Test check that always returns unhealthy."""

    async def check(self) -> HealthCheckResult:
        """Return an unhealthy result unconditionally."""
        return HealthCheckResult(
            name=self.name,
            status="unhealthy",
            message="Always unhealthy",
        )


class TestStartupSpecificChecks:
    """Test startup-specific health checks (separate from readiness checks).

    This test class validates the separation of startup and readiness checks
    as described in issue #135. During startup, the traffic-monitor should only
    verify WFS API connectivity (which can be checked immediately), not
    fcd_mapping or update_freshness (which require other services or time).
    """

    @pytest.fixture
    def server_with_startup_checks(self):
        """Create a health server with separate startup and readiness checks.

        This fixture simulates the traffic-monitor's health check setup where:
        - Startup checks: WFS API connectivity only (can pass immediately)
        - Readiness checks: All checks including fcd_mapping and update_freshness
        """
        server = HealthServer(
            port=18087,  # Unique port to avoid conflicts
            app_name="Test Traffic Monitor Startup Checks",
        )

        # Add startup-only check (WFS connectivity only)
        wfs_startup = AlwaysHealthyCheck(
            name="wfs_api_startup",
            critical=True,
        )
        server.add_check("wfs_api", wfs_startup, startup_only=True)

        # Add regular readiness checks (all checks)
        wfs_ready = AlwaysHealthyCheck(
            name="wfs_api",
            critical=True,
        )
        server.add_check("wfs_api", wfs_ready)

        # FCD mapping check - may fail if mapping file not ready (created by fcd-manager)
        fcd_mapping = AlwaysUnhealthyCheck(
            name="fcd_mapping",
            critical=True,
        )
        server.add_check("fcd_mapping", fcd_mapping)

        # Update freshness check - fails before first update cycle
        update_freshness = AlwaysUnhealthyCheck(
            name="update_freshness",
            critical=True,
        )
        server.add_check("update_freshness", update_freshness)

        # Detector status - should be OK immediately
        detector_status = AlwaysHealthyCheck(
            name="detector_status",
            critical=True,
        )
        server.add_check("detector_status", detector_status)

        yield server

        server.stop()

    def test_startup_uses_startup_only_checks(self, server_with_startup_checks):
        """Test that /startup endpoint uses startup_only checks, not regular checks.

        The /startup endpoint should only run WFS connectivity check,
        allowing the pod to pass startup probes while fcd-manager creates
        the mapping file.
        """
        server = server_with_startup_checks
        server.start_background()
        time.sleep(2)

        try:
            # /startup should pass because it uses startup_only checks
            response = requests.get("http://localhost:18087/startup", timeout=5)
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}"
            )
            data = response.json()
            assert data["ready"] is True

            # Startup checks should only include WFS connectivity
            assert "wfs_api" in data["checks"]

            # These checks should NOT be in startup checks
            assert "fcd_mapping" not in data["checks"]
            assert "update_freshness" not in data["checks"]
            assert "detector_status" not in data["checks"]
        finally:
            server.stop()

    def test_readiness_uses_regular_checks(self, server_with_startup_checks):
        """Test that /ready endpoint uses regular checks (not startup_only).

        The /ready endpoint should run all checks including fcd_mapping
        and update_freshness, which may fail during initialization.
        """
        server = server_with_startup_checks
        server.start_background()
        time.sleep(2)

        try:
            # /ready should fail because fcd_mapping and update_freshness are unhealthy
            response = requests.get("http://localhost:18087/ready", timeout=5)
            assert response.status_code == 503, (
                f"Expected 503, got {response.status_code}"
            )
            data = response.json()
            assert data["ready"] is False

            # All regular checks should appear in readiness
            assert "wfs_api" in data["checks"]
            assert "fcd_mapping" in data["checks"]
            assert "update_freshness" in data["checks"]
            assert "detector_status" in data["checks"]

            # The failing checks should show as unhealthy
            assert data["checks"]["fcd_mapping"] == "unhealthy"
            assert data["checks"]["update_freshness"] == "unhealthy"
        finally:
            server.stop()

    def test_startup_success_during_initialization(self):
        """Test scenario: startup passes while waiting for FCD mapping.

        This simulates the real-world case where:
        - WFS API connectivity check passes (startup_only)
        - FCD mapping check fails (regular check) because fcd-manager hasn't
          created the file yet
        - Pod should pass startup probes but fail readiness until mapping exists
        """
        server = HealthServer(
            port=18088,
            app_name="Traffic Monitor Initialization Simulation",
        )

        # Startup check (WFS connectivity only)
        wfs_startup = AlwaysHealthyCheck(name="wfs_api", critical=True)
        server.add_check("wfs_api", wfs_startup, startup_only=True)

        # Regular readiness checks
        wfs_ready = AlwaysHealthyCheck(name="wfs_api", critical=True)
        detector_ready = AlwaysHealthyCheck(name="detector_status", critical=True)

        # Check that simulates waiting for FCD mapping file
        class MappingFileCheck(HealthCheck):
            """Check that simulates FCD mapping file availability."""

            def __init__(self, file_exists: bool = False, **kwargs):
                super().__init__(**kwargs)
                self.file_exists = file_exists

            async def check(self) -> HealthCheckResult:
                if self.file_exists:
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="FCD mapping file exists",
                    )
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="FCD mapping file not found (waiting for fcd-manager)",
                )

        # Check that simulates update freshness
        class FreshnessCheck(HealthCheck):
            """Check that simulates update cycle completion."""

            def __init__(self, has_updated: bool = False, **kwargs):
                super().__init__(**kwargs)
                self.has_updated = has_updated

            async def check(self) -> HealthCheckResult:
                if self.has_updated:
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="Update cycle completed",
                    )
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="No update cycle completed yet",
                )

        mapping_check = MappingFileCheck(
            name="fcd_mapping", file_exists=False, critical=True
        )
        freshness_check = FreshnessCheck(
            name="update_freshness", has_updated=False, critical=True
        )

        server.add_check("wfs_api", wfs_ready)
        server.add_check("detector_status", detector_ready)
        server.add_check("fcd_mapping", mapping_check)
        server.add_check("update_freshness", freshness_check)

        server.start_background()
        time.sleep(2)

        try:
            # Phase 1: During initialization (waiting for fcd-manager)
            # Startup should pass (only WFS connectivity check)
            startup_response = requests.get("http://localhost:18088/startup", timeout=5)
            assert startup_response.status_code == 200
            startup_data = startup_response.json()
            assert startup_data["ready"] is True

            # Readiness should fail (mapping file doesn't exist, no update cycle)
            ready_response = requests.get("http://localhost:18088/ready", timeout=5)
            assert ready_response.status_code == 503
            ready_data = ready_response.json()
            assert ready_data["ready"] is False
            assert ready_data["checks"]["fcd_mapping"] == "unhealthy"
            assert ready_data["checks"]["update_freshness"] == "unhealthy"

            # Phase 2: Simulate fcd-manager creating the mapping file
            mapping_check.file_exists = True

            # Readiness should still fail (no update cycle yet)
            ready_response2 = requests.get("http://localhost:18088/ready", timeout=5)
            assert ready_response2.status_code == 503
            ready_data2 = ready_response2.json()
            assert ready_data2["checks"]["fcd_mapping"] == "healthy"
            assert ready_data2["checks"]["update_freshness"] == "unhealthy"

            # Phase 3: Simulate first update cycle completion
            freshness_check.has_updated = True

            # Now readiness should pass
            ready_response3 = requests.get("http://localhost:18088/ready", timeout=5)
            assert ready_response3.status_code == 200
            ready_data3 = ready_response3.json()
            assert ready_data3["ready"] is True
        finally:
            server.stop()


class TestTrafficMonitorStartupCheckConfiguration:
    """Test that traffic-monitor main.py correctly configures startup checks."""

    def test_startup_checks_registered_correctly(self):
        """Verify startup checks are registered with startup_only=True.

        This is a unit test that verifies the health server correctly
        separates startup and readiness checks.
        """
        server = HealthServer(
            port=18089,
            app_name="Test Registration",
        )

        # Add startup-only check
        startup_check = AlwaysHealthyCheck(name="startup", critical=True)
        server.add_check("test_check", startup_check, startup_only=True)

        # Add regular check
        ready_check = AlwaysHealthyCheck(name="ready", critical=True)
        server.add_check("test_check", ready_check)

        # Verify internal state
        assert "test_check" in server._startup_checks
        assert "test_check" in server._health_checks
        assert server._startup_checks["test_check"] is startup_check
        assert server._health_checks["test_check"] is ready_check


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
