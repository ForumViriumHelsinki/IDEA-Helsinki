"""Unit tests for the health check server."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from idea_shared.health.checks import HealthCheck, HealthCheckResult
from idea_shared.health.server import HealthServer


class MockHealthCheck(HealthCheck):
    """Mock health check for testing."""

    def __init__(self, name: str, result: HealthCheckResult, critical: bool = True):
        super().__init__(name=name, critical=critical)
        self._mock_result = result

    async def check(self) -> HealthCheckResult:
        """Return the mock result."""
        return self._mock_result


class TestHealthServer:
    """Tests for HealthServer class."""

    def test_server_initialization(self):
        """Test server initialization with default values."""
        server = HealthServer()
        assert server.port == 8080
        assert server.host == "0.0.0.0"
        assert server.app_name == "Service Health Check"
        assert server.enable_metrics is False
        assert len(server._health_checks) == 0

    def test_server_custom_initialization(self):
        """Test server initialization with custom values."""
        server = HealthServer(
            port=9090,
            host="localhost",
            app_name="Test Service",
            enable_metrics=True,
        )
        assert server.port == 9090
        assert server.host == "localhost"
        assert server.app_name == "Test Service"
        assert server.enable_metrics is True

    def test_add_health_check(self):
        """Test adding health checks."""
        server = HealthServer()
        check = MockHealthCheck(
            "test",
            HealthCheckResult(name="test", status="healthy"),
        )
        server.add_check("test", check)
        assert "test" in server._health_checks
        assert server._health_checks["test"] == check

    def test_remove_health_check(self):
        """Test removing health checks."""
        server = HealthServer()
        check = MockHealthCheck(
            "test",
            HealthCheckResult(name="test", status="healthy"),
        )
        server.add_check("test", check)
        server.remove_check("test")
        assert "test" not in server._health_checks

    def test_overwrite_health_check(self):
        """Test overwriting an existing health check."""
        server = HealthServer()
        check1 = MockHealthCheck(
            "test",
            HealthCheckResult(name="test", status="healthy"),
        )
        check2 = MockHealthCheck(
            "test",
            HealthCheckResult(name="test", status="unhealthy"),
        )

        server.add_check("test", check1)
        assert server._health_checks["test"] == check1

        server.add_check("test", check2)
        assert server._health_checks["test"] == check2


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_liveness_endpoint(self):
        """Test the /healthz liveness endpoint."""
        server = HealthServer()
        client = TestClient(server._app)

        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_readiness_endpoint_all_healthy(self):
        """Test the /ready endpoint when all checks are healthy."""
        server = HealthServer()

        # Add healthy checks
        server.add_check(
            "database",
            MockHealthCheck(
                "database",
                HealthCheckResult(name="database", status="healthy"),
                critical=True,
            ),
        )
        server.add_check(
            "filesystem",
            MockHealthCheck(
                "filesystem",
                HealthCheckResult(name="filesystem", status="healthy"),
                critical=True,
            ),
        )

        client = TestClient(server._app)
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["filesystem"] == "healthy"
        assert "timestamp" in data

    def test_readiness_endpoint_critical_failure(self):
        """Test the /ready endpoint when a critical check fails."""
        server = HealthServer()

        # Add mixed health checks
        server.add_check(
            "database",
            MockHealthCheck(
                "database",
                HealthCheckResult(name="database", status="unhealthy"),
                critical=True,
            ),
        )
        server.add_check(
            "cache",
            MockHealthCheck(
                "cache",
                HealthCheckResult(name="cache", status="healthy"),
                critical=False,
            ),
        )

        client = TestClient(server._app)
        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["checks"]["database"] == "unhealthy"
        assert data["checks"]["cache"] == "healthy"

    def test_readiness_endpoint_non_critical_failure(self):
        """Test the /ready endpoint when only non-critical checks fail."""
        server = HealthServer()

        server.add_check(
            "database",
            MockHealthCheck(
                "database",
                HealthCheckResult(name="database", status="healthy"),
                critical=True,
            ),
        )
        server.add_check(
            "cache",
            MockHealthCheck(
                "cache",
                HealthCheckResult(name="cache", status="degraded"),
                critical=False,
            ),
        )

        client = TestClient(server._app)
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["cache"] == "degraded"

    def test_metrics_endpoint_enabled(self):
        """Test the /metrics endpoint when enabled."""
        server = HealthServer(enable_metrics=True)
        server.add_check(
            "test",
            MockHealthCheck(
                "test",
                HealthCheckResult(name="test", status="healthy"),
            ),
        )

        client = TestClient(server._app)
        response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert data["metrics"]["health_checks_total"] == 1
        assert data["metrics"]["service_name"] == "Service Health Check"
        assert "timestamp" in data

    def test_metrics_endpoint_disabled(self):
        """Test that /metrics endpoint is not available when disabled."""
        server = HealthServer(enable_metrics=False)
        client = TestClient(server._app)

        response = client.get("/metrics")
        assert response.status_code == 404

    def test_health_detail_endpoint(self):
        """Test the /health/detail endpoint."""
        server = HealthServer()

        server.add_check(
            "database",
            MockHealthCheck(
                "database",
                HealthCheckResult(
                    name="database",
                    status="healthy",
                    message="Connected",
                    metadata={"connections": 10},
                ),
                critical=True,
            ),
        )
        server.add_check(
            "api",
            MockHealthCheck(
                "api",
                HealthCheckResult(
                    name="api",
                    status="degraded",
                    message="High latency",
                ),
                critical=False,
            ),
        )

        client = TestClient(server._app)
        response = client.get("/health/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Service Health Check"
        assert "timestamp" in data
        assert "checks" in data

        # Check database details
        db_check = data["checks"]["database"]
        assert db_check["status"] == "healthy"
        assert db_check["message"] == "Connected"
        assert db_check["metadata"]["connections"] == 10
        assert db_check["critical"] is True

        # Check API details
        api_check = data["checks"]["api"]
        assert api_check["status"] == "degraded"
        assert api_check["message"] == "High latency"
        assert api_check["critical"] is False


class TestHealthServerLifecycle:
    """Tests for server lifecycle management."""

    @patch("uvicorn.Server")
    @patch("uvicorn.Config")
    def test_start_background(self, mock_config, mock_server):
        """Test starting server in background thread."""
        server = HealthServer(port=8888)

        # Mock the server
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance

        # Start the server
        with patch("threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            server.start_background()

            # Verify thread was created and started
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()

    def test_stop_server(self):
        """Test stopping the server."""
        server = HealthServer()
        server._server = MagicMock()
        server._thread = MagicMock()
        server._thread.is_alive.return_value = True

        with patch.object(server._shutdown_event, "wait") as mock_wait:
            server.stop()
            assert server._server.should_exit is True
            mock_wait.assert_called_once_with(timeout=5)

    @pytest.mark.asyncio
    async def test_stop_async_server(self):
        """Test stopping the async server."""
        server = HealthServer()
        server._server = MagicMock()

        await server.stop_async()
        assert server._server.should_exit is True

    def test_context_manager(self):
        """Test using server as a context manager."""
        with patch.object(HealthServer, "start_background") as mock_start:
            with patch.object(HealthServer, "stop") as mock_stop:
                with HealthServer() as server:
                    mock_start.assert_called_once()
                    assert isinstance(server, HealthServer)
                mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test using server as an async context manager."""
        with patch.object(HealthServer, "start_async") as mock_start:
            mock_start.return_value = asyncio.sleep(0)  # Mock async coroutine
            with patch.object(HealthServer, "stop_async") as mock_stop:
                mock_stop.return_value = asyncio.sleep(0)  # Mock async coroutine
                async with HealthServer() as server:
                    # Give asyncio time to process
                    await asyncio.sleep(0.2)
                    assert isinstance(server, HealthServer)
                mock_stop.assert_called_once()


class TestHealthCheckException:
    """Tests for exception handling in health checks."""

    def test_health_check_exception_in_readiness(self):
        """Test that exceptions in health checks are handled properly."""

        class ExceptionHealthCheck(HealthCheck):
            async def check(self):
                raise Exception("Simulated failure")

        server = HealthServer()
        server.add_check(
            "failing", ExceptionHealthCheck(name="failing", critical=True)
        )

        client = TestClient(server._app)
        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["checks"]["failing"] == "unhealthy"

    def test_health_check_exception_in_detail(self):
        """Test exception handling in detail endpoint."""

        class ExceptionHealthCheck(HealthCheck):
            async def check(self):
                raise Exception("Simulated failure")

        server = HealthServer()
        server.add_check(
            "failing", ExceptionHealthCheck(name="failing", critical=True)
        )

        client = TestClient(server._app)
        response = client.get("/health/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["failing"]["status"] == "error"
        assert "Simulated failure" in data["checks"]["failing"]["message"]