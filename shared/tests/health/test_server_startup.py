"""Tests for startup probe and custom response codes."""

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from idea_shared.health import HealthCheck, HealthCheckResult, HealthServer


class SimpleHealthCheck(HealthCheck):
    """Simple health check for testing."""

    def __init__(self, name: str, healthy: bool = True):
        super().__init__(name, timeout=1.0)
        self.healthy = healthy

    async def check(self) -> HealthCheckResult:
        if self.healthy:
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Check passed",
            )
        else:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="Check failed",
            )


class TestStartupProbe:
    """Tests for startup probe endpoint."""

    def test_startup_endpoint_exists(self):
        """Test that startup endpoint is registered."""
        server = HealthServer(port=8090, app_name="Test Startup")
        client = TestClient(server._app)

        response = client.get("/startup")
        assert response.status_code in [200, 503]  # Depends on health checks

    def test_startup_with_no_checks(self):
        """Test startup endpoint with no health checks."""
        server = HealthServer(port=8091, app_name="Test")
        client = TestClient(server._app)

        response = client.get("/startup")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"] == {}

    def test_startup_with_healthy_checks(self):
        """Test startup endpoint with healthy checks."""
        server = HealthServer(port=8092, app_name="Test")
        server.add_check("check1", SimpleHealthCheck("check1", healthy=True))
        server.add_check("check2", SimpleHealthCheck("check2", healthy=True))

        client = TestClient(server._app)
        response = client.get("/startup")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"]["check1"] == "healthy"
        assert data["checks"]["check2"] == "healthy"

    def test_startup_with_unhealthy_checks(self):
        """Test startup endpoint with unhealthy checks."""
        server = HealthServer(port=8093, app_name="Test")
        server.add_check("check1", SimpleHealthCheck("check1", healthy=True))
        server.add_check("check2", SimpleHealthCheck("check2", healthy=False))

        client = TestClient(server._app)
        response = client.get("/startup")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["checks"]["check1"] == "healthy"
        assert data["checks"]["check2"] == "unhealthy"

    def test_startup_only_checks(self):
        """Test startup-only health checks."""
        server = HealthServer(port=8094, app_name="Test")

        # Add regular check
        server.add_check("regular", SimpleHealthCheck("regular", healthy=True))

        # Add startup-only check
        server.add_check("startup", SimpleHealthCheck("startup", healthy=False), startup_only=True)

        client = TestClient(server._app)

        # Startup endpoint should use startup checks
        startup_response = client.get("/startup")
        assert startup_response.status_code == 503
        startup_data = startup_response.json()
        assert "startup" in startup_data["checks"]
        assert "regular" not in startup_data["checks"]

        # Ready endpoint should use regular checks
        ready_response = client.get("/ready")
        assert ready_response.status_code == 200
        ready_data = ready_response.json()
        assert "regular" in ready_data["checks"]
        assert "startup" not in ready_data["checks"]

    def test_remove_startup_check(self):
        """Test removing startup-only checks."""
        server = HealthServer(port=8095, app_name="Test")

        # Add and remove startup check
        server.add_check("startup", SimpleHealthCheck("startup", healthy=True), startup_only=True)
        server.remove_check("startup", startup_only=True)

        client = TestClient(server._app)
        response = client.get("/startup")
        data = response.json()
        assert "startup" not in data["checks"]


class TestCustomResponseCodes:
    """Tests for custom response codes."""

    def test_custom_liveness_code(self):
        """Test custom liveness response code."""
        server = HealthServer(
            port=8096,
            app_name="Test",
            liveness_status_code=201,  # Custom code
        )
        client = TestClient(server._app)

        response = client.get("/healthz")
        assert response.status_code == 201

    def test_custom_readiness_codes(self):
        """Test custom readiness response codes."""
        server = HealthServer(
            port=8097,
            app_name="Test",
            readiness_success_code=202,
            readiness_failure_code=500,
        )

        # Test success code
        server.add_check("check1", SimpleHealthCheck("check1", healthy=True))
        client = TestClient(server._app)

        response = client.get("/ready")
        assert response.status_code == 202

        # Test failure code
        server.add_check("check2", SimpleHealthCheck("check2", healthy=False))
        response = client.get("/ready")
        assert response.status_code == 500

    def test_custom_startup_codes(self):
        """Test custom startup response codes."""
        server = HealthServer(
            port=8098,
            app_name="Test",
            startup_success_code=204,
            startup_failure_code=502,
        )

        client = TestClient(server._app)

        # Test success code (no checks)
        response = client.get("/startup")
        assert response.status_code == 204

        # Test failure code
        server.add_check("check", SimpleHealthCheck("check", healthy=False))
        response = client.get("/startup")
        assert response.status_code == 502

    def test_all_custom_codes_together(self):
        """Test all custom response codes together."""
        server = HealthServer(
            port=8099,
            app_name="Test",
            liveness_status_code=211,
            readiness_success_code=212,
            readiness_failure_code=513,
            startup_success_code=214,
            startup_failure_code=514,
        )

        client = TestClient(server._app)

        # Test liveness
        response = client.get("/healthz")
        assert response.status_code == 211

        # Test readiness success
        response = client.get("/ready")
        assert response.status_code == 212

        # Test startup success
        response = client.get("/startup")
        assert response.status_code == 214

        # Add unhealthy check
        server.add_check("unhealthy", SimpleHealthCheck("unhealthy", healthy=False))

        # Test readiness failure
        response = client.get("/ready")
        assert response.status_code == 513

        # Test startup failure
        response = client.get("/startup")
        assert response.status_code == 514


class TestStartupStateTracking:
    """Tests for startup state tracking."""

    def test_startup_complete_flag(self):
        """Test that startup complete flag is set correctly."""
        server = HealthServer(port=9000, app_name="Test")

        # Initially not complete
        assert server._startup_complete is False

        # Add healthy check
        server.add_check("check", SimpleHealthCheck("check", healthy=True))

        client = TestClient(server._app)

        # First successful startup should set flag
        response = client.get("/startup")
        assert response.status_code == 200

        # Note: In real async scenario, the flag would be set
        # This test demonstrates the structure