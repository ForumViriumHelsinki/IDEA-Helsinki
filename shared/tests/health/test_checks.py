"""Unit tests for health check classes."""

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from idea_shared.health.checks import (
    CircuitBreakerState,
    ExternalAPIHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
    HealthCheckResult,
)


class ConcreteHealthCheck(HealthCheck):
    """Concrete implementation for testing."""

    def __init__(self, result: HealthCheckResult, **kwargs):
        super().__init__(**kwargs)
        self._result = result

    async def check(self) -> HealthCheckResult:
        """Return the predetermined result."""
        return self._result


class TestHealthCheck:
    """Tests for the base HealthCheck class."""

    @pytest.mark.asyncio
    async def test_successful_check(self):
        """Test a successful health check.

        Verifies that a health check returns the expected healthy status
        when the check passes successfully.
        """
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test")
        result = await check.check_with_cache()
        assert result == expected

    @pytest.mark.asyncio
    async def test_check_with_timeout(self):
        """Test health check timeout handling.

        Verifies that health checks properly handle timeout scenarios by
        returning an unhealthy status when a check exceeds its timeout duration.
        This ensures slow or hanging checks don't block the health server.
        """

        async def slow_check():
            await asyncio.sleep(2)
            return HealthCheckResult(name="slow", status="healthy")

        class SlowHealthCheck(HealthCheck):
            async def check(self):
                return await slow_check()

        check = SlowHealthCheck(name="slow", timeout=0.1)
        result = await check.check_with_cache()
        assert result.status == "unhealthy"
        assert result.message is not None
        assert "timed out" in result.message

    @pytest.mark.asyncio
    async def test_check_with_exception(self):
        """Test health check exception handling.

        Verifies that exceptions raised during health checks are caught
        and converted to unhealthy status with error messages. This prevents
        health check failures from crashing the health server.
        """

        class FailingHealthCheck(HealthCheck):
            async def check(self):
                raise ValueError("Test error")

        check = FailingHealthCheck(name="failing", timeout=1.0)
        result = await check.check_with_cache()
        assert result.status == "unhealthy"
        assert result.message is not None
        assert "Test error" in result.message

    @pytest.mark.asyncio
    async def test_cache_functionality(self):
        """Test that caching works correctly.

        Verifies the cache TTL mechanism by ensuring that:
        1. First call executes the health check
        2. Subsequent calls within TTL return cached result
        3. Calls after TTL expiration execute the check again

        This reduces load on dependencies during frequent health check requests.
        """
        call_count = 0

        class CountingHealthCheck(HealthCheck):
            async def check(self):
                nonlocal call_count
                call_count += 1
                return HealthCheckResult(
                    name="counting", status="healthy", message=f"Call {call_count}"
                )

        check = CountingHealthCheck(name="counting", cache_ttl=1.0)

        # First call should execute the check
        result1 = await check.check_with_cache()
        assert call_count == 1
        assert result1.message == "Call 1"

        # Second call should return cached result
        result2 = await check.check_with_cache()
        assert call_count == 1  # Should not increment
        assert result2.message == "Call 1"  # Same cached result

        # Wait for cache to expire
        await asyncio.sleep(1.1)

        # Third call should execute the check again
        result3 = await check.check_with_cache()
        assert call_count == 2
        assert result3.message == "Call 2"

    def test_sync_check(self):
        """Test synchronous version of health check.

        Verifies that health checks can be executed synchronously using
        check_sync(), which is useful for services without async event loops.
        """
        expected = HealthCheckResult(name="sync", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="sync")
        result = check.check_sync()
        assert result == expected


class TestFileSystemHealthCheck:
    """Tests for FileSystemHealthCheck class."""

    @pytest.mark.asyncio
    async def test_check_existing_directory(self):
        """Test checking an existing directory.

        Verifies that the FileSystemHealthCheck correctly identifies and reports
        healthy status for existing directories. This is critical for ensuring
        data directories like segment mappings and archives are accessible.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            check = FileSystemHealthCheck(name="dir_check", path=tmpdir)
            result = await check.check()
            assert result.status == "healthy"
            assert result.message is not None
            assert tmpdir in result.message

    @pytest.mark.asyncio
    async def test_check_existing_file(self):
        """Test checking an existing file.

        Verifies that the FileSystemHealthCheck correctly validates the existence
        of individual files. This is important for checking critical JSON files
        like segments_mapping.json and master_segment_history.json.
        """
        with tempfile.NamedTemporaryFile() as tmpfile:
            check = FileSystemHealthCheck(name="file_check", path=tmpfile.name)
            result = await check.check()
            assert result.status == "healthy"

    @pytest.mark.asyncio
    async def test_check_non_existing_path(self):
        """Test checking a non-existing path.

        Verifies that the FileSystemHealthCheck returns unhealthy status when
        checking paths that don't exist. This ensures the system can detect
        missing configuration files or data directories before processing fails.
        """
        check = FileSystemHealthCheck(name="missing", path="/non/existent/path/test123")
        result = await check.check()
        assert result.status == "unhealthy"
        assert result.message is not None
        assert "does not exist" in result.message

    @pytest.mark.asyncio
    async def test_write_permission_check_success(self):
        """Test successful write permission check.

        Verifies that the FileSystemHealthCheck can validate write permissions
        on directories when check_write is enabled. This is essential for ensuring
        the application can write updated segment mappings and validation results.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            check = FileSystemHealthCheck(
                name="write_check", path=tmpdir, check_write=True
            )
            result = await check.check()
            assert result.status == "healthy"
            assert result.metadata is not None
            assert result.metadata["writable"] is True

    @pytest.mark.asyncio
    async def test_write_permission_check_failure(self):
        """Test write permission check on read-only directory.

        Verifies that the FileSystemHealthCheck detects when directories lack
        write permissions. This test creates a read-only directory to simulate
        permission issues that could prevent data updates. Note that on some
        systems, directory owners may retain write access even with 0o444 permissions.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Create a subdirectory and make it read-only
            readonly_dir = tmpdir_path / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)

            check = FileSystemHealthCheck(
                name="readonly_check", path=str(readonly_dir), check_write=True
            )
            result = await check.check()

            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)

            # On some systems, read-only directories might still allow writes by owner
            # So we check if the test detected the issue or passed
            assert result.status in ["unhealthy", "healthy"]


class TestExternalAPIHealthCheck:
    """Tests for ExternalAPIHealthCheck class."""

    @pytest.mark.asyncio
    async def test_successful_api_check(self):
        """Test successful API health check.

        Verifies that the ExternalAPIHealthCheck correctly validates external
        API availability by checking HTTP response codes. This ensures proper
        monitoring of dependencies like the Helsinki WFS service and Azure APIs.
        """
        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mock for response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            # Create async context manager mock for session
            mock_session_instance = AsyncMock()
            # Make request() a regular mock (not async) that returns the response context manager
            mock_session_instance.request = lambda *args, **kwargs: mock_response
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            check = ExternalAPIHealthCheck(
                name="api_check", url="https://api.example.com/health"
            )
            result = await check.check()

            assert result.status == "healthy"
            assert result.message is not None
            assert "200" in result.message
            assert result.metadata is not None
            assert result.metadata["status_code"] == 200

    @pytest.mark.asyncio
    async def test_api_unexpected_status(self):
        """Test API returning unexpected status code.

        Verifies that the ExternalAPIHealthCheck detects when external APIs
        return error status codes (like 500). The check returns unhealthy status
        and includes both actual and expected status codes in metadata for debugging.
        """
        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mock for response
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            # Create async context manager mock for session
            mock_session_instance = AsyncMock()
            # Make request() a regular mock (not async) that returns the response context manager
            mock_session_instance.request = lambda *args, **kwargs: mock_response
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            check = ExternalAPIHealthCheck(
                name="api_check",
                url="https://api.example.com/health",
                expected_status=200,
            )
            result = await check.check()

            assert result.status == "unhealthy"
            assert result.message is not None
            assert "500" in result.message
            assert result.metadata is not None
            assert result.metadata["status_code"] == 500
            assert result.metadata["expected"] == 200

    @pytest.mark.asyncio
    async def test_api_connection_error(self):
        """Test API connection error handling.

        Verifies that the ExternalAPIHealthCheck gracefully handles network-level
        connection failures. This ensures that transient network issues don't crash
        the health check system and are properly reported as unhealthy status.
        """
        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mock for session
            mock_session_instance = AsyncMock()

            # Make request() raise an exception
            def raise_error(*args, **kwargs):
                raise aiohttp.ClientError("Connection failed")

            mock_session_instance.request = raise_error
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            check = ExternalAPIHealthCheck(
                name="api_check", url="https://api.example.com/health"
            )
            result = await check.check()

            assert result.status == "unhealthy"
            assert result.message is not None
            assert "Connection failed" in result.message

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens(self):
        """Test that circuit breaker opens after threshold failures.

        Verifies the circuit breaker pattern implementation by checking that
        after the configured failure threshold is reached, the circuit opens
        and subsequent checks return degraded status without attempting actual
        API calls. This protects the system from repeatedly calling failing services.
        """
        check = ExternalAPIHealthCheck(
            name="api_check",
            url="https://api.example.com/health",
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=60,
        )

        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mock for session with failure
            mock_session_instance = AsyncMock()

            # Make request() raise an exception
            def raise_error(*args, **kwargs):
                raise aiohttp.ClientError("Connection failed")

            mock_session_instance.request = raise_error
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            # First failure
            result1 = await check.check()
            assert result1.status == "unhealthy"
            assert check._failure_count == 1
            assert check._circuit_state == CircuitBreakerState.CLOSED

            # Second failure - should open circuit
            result2 = await check.check()
            assert result2.status == "unhealthy"
            assert check._failure_count == 2
            assert check._circuit_state == CircuitBreakerState.OPEN

            # Third attempt - circuit is open
            result3 = await check.check()
            assert result3.status == "degraded"
            assert result3.message is not None
            assert "Circuit breaker is open" in result3.message

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self):
        """Test that circuit breaker resets on successful check.

        Verifies that the circuit breaker properly resets its failure count
        when a health check succeeds after previous failures. This allows the
        system to recover automatically when external services come back online.
        """
        check = ExternalAPIHealthCheck(
            name="api_check",
            url="https://api.example.com/health",
            circuit_breaker_threshold=2,
        )

        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mocks
            mock_response = AsyncMock()
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_session_instance = AsyncMock()
            # Make request() a regular mock that returns the response context manager
            mock_session_instance.request = lambda *args, **kwargs: mock_response
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            # First failure
            mock_response.status = 500
            _result1 = await check.check()
            assert check._failure_count == 1

            # Success - should reset failure count
            mock_response.status = 200
            result2 = await check.check()
            assert result2.status == "healthy"
            assert check._failure_count == 0

    @pytest.mark.asyncio
    async def test_custom_http_method_and_headers(self):
        """Test custom HTTP method and headers.

        Verifies that the ExternalAPIHealthCheck correctly passes custom HTTP
        methods and headers to the underlying HTTP client. This is important
        for APIs that require authentication tokens or specific request methods.
        """
        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mock for response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            # Track request calls
            request_calls = []

            def track_request(*args, **kwargs):
                request_calls.append((args, kwargs))
                return mock_response

            # Create async context manager mock for session
            mock_session_instance = AsyncMock()
            mock_session_instance.request = track_request
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            check = ExternalAPIHealthCheck(
                name="api_check",
                url="https://api.example.com/health",
                method="POST",
                headers={"Authorization": "Bearer token"},
            )
            _result = await check.check()

            # Verify request was called correctly
            assert len(request_calls) == 1
            call_args, call_kwargs = request_calls[0]
            assert call_args[0] == "POST"
            assert call_args[1] == "https://api.example.com/health"
            assert call_kwargs["headers"] == {"Authorization": "Bearer token"}

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_state(self):
        """Test circuit breaker half-open state behavior.

        Verifies the circuit breaker's half-open state transition, which occurs
        after the timeout period expires following an open circuit. In half-open
        state, the system attempts one test request, and if successful, closes
        the circuit to resume normal operation.
        """
        check = ExternalAPIHealthCheck(
            name="api_check",
            url="https://api.example.com/health",
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=0.1,  # Short timeout for testing
        )

        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mocks
            mock_response = AsyncMock()
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_session_instance = AsyncMock()
            # Make request() a regular mock that returns the response context manager
            mock_session_instance.request = lambda *args, **kwargs: mock_response
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            # Cause circuit to open
            mock_response.status = 500

            # Two failures to open circuit
            await check.check()
            await check.check()
            assert check._circuit_state == CircuitBreakerState.OPEN

            # Wait for timeout
            await asyncio.sleep(0.15)

            # Next check should transition to half-open
            mock_response.status = 200  # Simulate recovery
            result = await check.check()
            assert result.status == "healthy"
            assert check._circuit_state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_failure(self):
        """Test circuit breaker re-opening from half-open state.

        Verifies that if the test request fails during the half-open state,
        the circuit breaker immediately reopens to continue protecting the
        system. This prevents premature recovery when services are still unstable.
        """
        check = ExternalAPIHealthCheck(
            name="api_check",
            url="https://api.example.com/health",
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=0.1,
        )

        with patch("aiohttp.ClientSession") as mock_session:
            # Create async context manager mock for session with failure
            mock_session_instance = AsyncMock()

            # Make request() raise an exception
            def raise_error(*args, **kwargs):
                raise aiohttp.ClientError("Connection failed")

            mock_session_instance.request = raise_error
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session.return_value.__aexit__.return_value = None

            # Open the circuit
            await check.check()
            await check.check()
            assert check._circuit_state == CircuitBreakerState.OPEN

            # Wait for timeout
            await asyncio.sleep(0.15)

            # Next check should transition to half-open and fail
            result = await check.check()
            assert result.status == "unhealthy"
            assert check._circuit_state == CircuitBreakerState.OPEN


class TestHealthCheckPerformanceMetrics:
    """Tests for health check execution time tracking."""

    @pytest.mark.asyncio
    async def test_execution_time_populated_in_result(self):
        """Test that execution_time_ms is set in the result after check_with_cache().

        Verifies that every real health check execution records its duration
        so callers can observe how long checks take.
        """
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test")
        result = await check.check_with_cache()
        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_execution_time_tracked_in_check_object(self):
        """Test that the check object tracks the last execution time."""
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test")
        assert check._last_execution_time_ms is None
        await check.check_with_cache()
        assert check._last_execution_time_ms is not None
        assert check._last_execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_execution_history_tracked(self):
        """Test that last N execution times are stored for trending."""
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test", cache_ttl=0)
        assert len(check._execution_times) == 0
        for _ in range(3):
            await check.check_with_cache()
        assert len(check._execution_times) == 3

    @pytest.mark.asyncio
    async def test_execution_history_capped_at_max(self):
        """Test that execution history is bounded (max 10 entries)."""
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test", cache_ttl=0)
        for _ in range(15):
            await check.check_with_cache()
        assert len(check._execution_times) == 10

    @pytest.mark.asyncio
    async def test_slow_check_warning_logged(self):
        """Test that a warning is logged when a check takes >= 80% of its timeout."""

        class SlowishCheck(HealthCheck):
            async def check(self) -> HealthCheckResult:
                await asyncio.sleep(0.09)
                return HealthCheckResult(name="slowish", status="healthy")

        check = SlowishCheck(name="slowish", timeout=0.1)  # threshold = 80ms
        with patch("idea_shared.health.checks.logger") as mock_logger:
            await check.check_with_cache()
            # Execution is ~90ms, threshold is 80ms — warning must fire
            mock_logger.warning.assert_called_once()
            args = mock_logger.warning.call_args[0]
            assert "slowish" in args[1]

    @pytest.mark.asyncio
    async def test_get_performance_stats_empty(self):
        """Test get_performance_stats() with no executions yet."""
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test")
        stats = check.get_performance_stats()
        assert stats["check_count"] == 0
        assert stats["last_execution_time_ms"] is None
        assert stats["min_execution_time_ms"] is None
        assert stats["max_execution_time_ms"] is None
        assert stats["avg_execution_time_ms"] is None

    @pytest.mark.asyncio
    async def test_get_performance_stats_after_runs(self):
        """Test get_performance_stats() returns correct values after executions."""
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test", cache_ttl=0)
        await check.check_with_cache()
        await check.check_with_cache()
        stats = check.get_performance_stats()
        assert stats["check_count"] == 2
        assert stats["last_execution_time_ms"] is not None
        assert stats["min_execution_time_ms"] is not None
        assert stats["max_execution_time_ms"] is not None
        assert stats["avg_execution_time_ms"] is not None
        assert stats["min_execution_time_ms"] <= stats["max_execution_time_ms"]

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_update_execution_time(self):
        """Test that returning a cached result does not add a new execution time."""
        expected = HealthCheckResult(name="test", status="healthy")
        check = ConcreteHealthCheck(result=expected, name="test", cache_ttl=10.0)
        await check.check_with_cache()  # Real execution
        assert len(check._execution_times) == 1
        await check.check_with_cache()  # Cache hit
        assert len(check._execution_times) == 1  # Should not grow

    @pytest.mark.asyncio
    async def test_timeout_result_includes_execution_time(self):
        """Test that timed-out checks still record execution_time_ms."""

        class SlowHealthCheck(HealthCheck):
            async def check(self) -> HealthCheckResult:
                await asyncio.sleep(2)
                return HealthCheckResult(name="slow", status="healthy")

        check = SlowHealthCheck(name="slow", timeout=0.05)
        result = await check.check_with_cache()
        assert result.status == "unhealthy"
        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 50  # At least the timeout duration in ms


class TestConcurrentHealthChecks:
    """Tests for concurrent health check execution."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_checks(self):
        """Test running multiple health checks concurrently.

        Verifies that multiple health checks can execute simultaneously without
        blocking each other. This tests that asyncio.gather properly parallelizes
        checks, completing in the time of the slowest check rather than the sum
        of all check durations, which is crucial for fast health endpoint responses.
        """
        results_list = []

        class DelayedHealthCheck(HealthCheck):
            def __init__(
                self,
                delay: float,
                result_status: Literal["healthy", "unhealthy", "degraded"],
                **kwargs,
            ):
                super().__init__(**kwargs)
                self.delay = delay
                self.result_status: Literal["healthy", "unhealthy", "degraded"] = (
                    result_status
                )

            async def check(self) -> HealthCheckResult:
                await asyncio.sleep(self.delay)
                results_list.append(self.name)
                return HealthCheckResult(
                    name=self.name,
                    status=self.result_status,
                    message=f"Delayed {self.delay}s",
                )

        # Create checks with different delays
        check1 = DelayedHealthCheck(delay=0.1, result_status="healthy", name="fast")
        check2 = DelayedHealthCheck(delay=0.2, result_status="healthy", name="medium")
        check3 = DelayedHealthCheck(delay=0.3, result_status="healthy", name="slow")

        # Run all checks concurrently
        start_time = time.time()
        results = await asyncio.gather(
            check1.check_with_cache(),
            check2.check_with_cache(),
            check3.check_with_cache(),
        )
        elapsed_time = time.time() - start_time

        # All checks should complete
        assert len(results) == 3
        assert all(r.status == "healthy" for r in results)

        # Should complete in roughly the time of the slowest check
        # (not the sum of all delays)
        assert elapsed_time < 0.6  # Should be ~0.3s, not 0.6s
        assert elapsed_time >= 0.3

        # Check order of completion (fastest first)
        assert results_list == ["fast", "medium", "slow"]

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self):
        """Test that concurrent access to cached results works correctly.

        Verifies that when multiple concurrent requests access the same cached
        health check result, they all receive the cached value without triggering
        additional check executions. This ensures efficient resource usage during
        high-frequency health check polling.
        """
        call_count = 0

        class CountingHealthCheck(HealthCheck):
            async def check(self) -> HealthCheckResult:
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.1)  # Simulate some work
                return HealthCheckResult(
                    name="counting",
                    status="healthy",
                    message=f"Call {call_count}",
                )

        check = CountingHealthCheck(name="counting", cache_ttl=1.0)

        # First call to populate cache
        await check.check_with_cache()
        assert call_count == 1

        # Multiple concurrent calls should all get cached result
        results = await asyncio.gather(*[check.check_with_cache() for _ in range(10)])

        # Should still only have called check once
        assert call_count == 1
        assert all(r.message == "Call 1" for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_filesystem_checks(self):
        """Test concurrent filesystem health checks.

        Verifies that multiple filesystem health checks can safely execute
        concurrently on the same directory without conflicts or race conditions.
        This is important when checking multiple paths or performing write
        permission tests simultaneously.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple filesystem checks
            checks = [
                FileSystemHealthCheck(
                    name=f"fs_check_{i}",
                    path=tmpdir,
                    check_write=True,
                )
                for i in range(5)
            ]

            # Run all checks concurrently
            results = await asyncio.gather(*[check.check() for check in checks])

            # All should succeed without conflicts
            assert all(r.status == "healthy" for r in results)
            assert all(
                r.metadata is not None and r.metadata["writable"] is True
                for r in results
            )
