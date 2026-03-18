"""Abstract base classes for health checks."""

import asyncio
import collections
import logging
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any

import aiohttp

from .models import HealthCheckResult

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """State of the circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, requests are blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


class HealthCheck(ABC):
    """Abstract base class for all health checks."""

    def __init__(
        self,
        name: str,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 0,
    ):
        """Initialize a health check.

        Args:
            name: Name of the health check
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds (0 = no cache)
        """
        self.name = name
        self.timeout = timeout
        self.critical = critical
        self.cache_ttl = cache_ttl
        self._cached_result: HealthCheckResult | None = None
        self._cache_timestamp: float = 0
        self._last_execution_time_ms: float | None = None
        self._execution_times: collections.deque[float] = collections.deque(maxlen=10)

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """Perform the health check asynchronously.

        Returns:
            HealthCheckResult indicating the status of the check
        """
        pass

    async def check_with_cache(self) -> HealthCheckResult:
        """Perform the health check with caching if enabled.

        Returns:
            HealthCheckResult, possibly from cache
        """
        now = time.time()
        if (
            self.cache_ttl > 0
            and self._cached_result
            and (now - self._cache_timestamp) < self.cache_ttl
        ):
            return self._cached_result

        start = time.time()
        try:
            result = await asyncio.wait_for(self.check(), timeout=self.timeout)
            execution_time_ms = (time.time() - start) * 1000
            self._record_execution_time(execution_time_ms)
            result = result.model_copy(update={"execution_time_ms": execution_time_ms})
            if self.cache_ttl > 0:
                self._cached_result = result
                self._cache_timestamp = now
            return result
        except TimeoutError:
            execution_time_ms = (time.time() - start) * 1000
            self._record_execution_time(execution_time_ms)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Health check timed out after {self.timeout} seconds",
                execution_time_ms=execution_time_ms,
            )
        except Exception as e:
            execution_time_ms = (time.time() - start) * 1000
            self._record_execution_time(execution_time_ms)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Health check failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

    def _record_execution_time(self, execution_time_ms: float) -> None:
        """Record an execution time and warn if approaching timeout.

        Args:
            execution_time_ms: Execution time in milliseconds
        """
        self._last_execution_time_ms = execution_time_ms
        self._execution_times.append(execution_time_ms)
        slow_threshold_ms = self.timeout * 0.8 * 1000
        if execution_time_ms >= slow_threshold_ms:
            logger.warning(
                "Health check '%s' took %.1fms, approaching timeout of %.0fms",
                self.name,
                execution_time_ms,
                self.timeout * 1000,
            )

    def get_performance_stats(self) -> dict[str, Any]:
        """Return execution time statistics for this health check.

        Returns:
            Dict with check_count, last/min/max/avg execution times in ms
        """
        times = list(self._execution_times)
        if not times:
            return {
                "check_count": 0,
                "last_execution_time_ms": None,
                "min_execution_time_ms": None,
                "max_execution_time_ms": None,
                "avg_execution_time_ms": None,
            }
        return {
            "check_count": len(times),
            "last_execution_time_ms": self._last_execution_time_ms,
            "min_execution_time_ms": min(times),
            "max_execution_time_ms": max(times),
            "avg_execution_time_ms": sum(times) / len(times),
        }

    def check_sync(self) -> HealthCheckResult:
        """Synchronous version of the health check.

        Note: This creates a new event loop for each check which may have
        performance implications for frequent checks. Consider using async
        checks with an existing event loop where possible.

        Returns:
            HealthCheckResult indicating the status of the check
        """
        try:
            return asyncio.run(self.check_with_cache())
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Health check failed: {str(e)}",
            )


class DatabaseHealthCheck(HealthCheck):
    """Base class for database connectivity checks."""

    def __init__(
        self,
        name: str,
        connection_string: str,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 5.0,
    ):
        """Initialize database health check.

        Args:
            name: Name of the health check
            connection_string: Database connection string
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.connection_string = connection_string

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """Subclasses must implement specific database connectivity check."""
        pass


class FileSystemHealthCheck(HealthCheck):
    """Base class for file system checks."""

    def __init__(
        self,
        name: str,
        path: str,
        check_write: bool = False,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 5.0,
    ):
        """Initialize file system health check.

        Args:
            name: Name of the health check
            path: Path to check
            check_write: Whether to check write permissions
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.path = Path(path)
        self.check_write = check_write

    async def check(self) -> HealthCheckResult:
        """Check file system accessibility.

        Returns:
            HealthCheckResult indicating file system status
        """
        try:
            # Check if path exists
            if not self.path.exists():
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message=f"Path does not exist: {self.path}",
                )

            # Check read permission
            if self.path.is_dir():
                # Try to list directory
                list(self.path.iterdir())
            else:
                # Try to read file stats
                self.path.stat()

            # Check write permission if requested
            if self.check_write:
                # Use UUID to prevent predictable test file names
                test_uuid = uuid.uuid4().hex[:8]
                test_file = (
                    self.path / f".health_check_test_{test_uuid}"
                    if self.path.is_dir()
                    else self.path.parent
                    / f".health_check_{self.path.name}_{test_uuid}"
                )
                try:
                    # Use async file operations
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: test_file.write_text("test"),
                    )
                    try:
                        await asyncio.get_running_loop().run_in_executor(
                            None,
                            test_file.unlink,
                        )
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to cleanup test file {test_file}: {cleanup_error}"
                        )
                except Exception as e:
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=f"Write permission check failed: {str(e)}",
                    )

            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message=f"File system check passed for {self.path}",
                metadata={"path": str(self.path), "writable": self.check_write},
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"File system check failed: {str(e)}",
            )


class ExternalAPIHealthCheck(HealthCheck):
    """Base class for external API checks with circuit breaker pattern."""

    def __init__(
        self,
        name: str,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 5.0,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_timeout: float = 60.0,
    ):
        """Initialize external API health check.

        Args:
            name: Name of the health check
            url: API endpoint URL
            method: HTTP method
            headers: Optional request headers
            expected_status: Expected HTTP status code
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
            circuit_breaker_threshold: Number of failures before opening circuit
            circuit_breaker_timeout: Time to wait before attempting to close circuit
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.expected_status = expected_status
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_timeout = circuit_breaker_timeout
        self._failure_count = 0
        self._circuit_state = CircuitBreakerState.CLOSED
        self._circuit_open_time = 0

    async def check(self) -> HealthCheckResult:
        """Check external API availability with circuit breaker.

        Returns:
            HealthCheckResult indicating API status
        """
        # Handle circuit breaker states
        if self._circuit_state == CircuitBreakerState.OPEN:
            if (time.time() - self._circuit_open_time) < self.circuit_breaker_timeout:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message="Circuit breaker is open",
                    metadata={
                        "circuit_state": self._circuit_state.value,
                        "failures": self._failure_count,
                        "time_remaining": self.circuit_breaker_timeout
                        - (time.time() - self._circuit_open_time),
                    },
                )
            else:
                # Transition to half-open state to test recovery
                self._circuit_state = CircuitBreakerState.HALF_OPEN
                logger.info(
                    f"Circuit breaker for {self.name} transitioning to half-open state"
                )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    self.method,
                    self.url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status == self.expected_status:
                        # Success - handle state transitions
                        if self._circuit_state == CircuitBreakerState.HALF_OPEN:
                            logger.info(
                                f"Circuit breaker for {self.name} closing - service recovered"
                            )
                            self._circuit_state = CircuitBreakerState.CLOSED
                        self._failure_count = 0
                        return HealthCheckResult(
                            name=self.name,
                            status="healthy",
                            message=f"API responded with status {response.status}",
                            metadata={
                                "url": self.url,
                                "status_code": response.status,
                                "circuit_state": self._circuit_state.value,
                            },
                        )
                    else:
                        # Failure - handle state transitions
                        if self._circuit_state == CircuitBreakerState.HALF_OPEN:
                            # Failed during half-open, re-open circuit
                            self._circuit_state = CircuitBreakerState.OPEN
                            self._circuit_open_time = time.time()
                            logger.warning(
                                f"Circuit breaker for {self.name} re-opening - service still failing"
                            )
                        else:
                            self._failure_count += 1
                            if self._failure_count >= self.circuit_breaker_threshold:
                                self._circuit_state = CircuitBreakerState.OPEN
                                self._circuit_open_time = time.time()
                                logger.warning(
                                    f"Circuit breaker for {self.name} opening after {self._failure_count} failures"
                                )

                        return HealthCheckResult(
                            name=self.name,
                            status="unhealthy",
                            message=f"API returned unexpected status {response.status}",
                            metadata={
                                "url": self.url,
                                "status_code": response.status,
                                "expected": self.expected_status,
                                "circuit_state": self._circuit_state.value,
                                "failures": self._failure_count,
                            },
                        )

        except aiohttp.ClientError as e:
            # Network errors - handle state transitions
            if self._circuit_state == CircuitBreakerState.HALF_OPEN:
                # Failed during half-open, re-open circuit
                self._circuit_state = CircuitBreakerState.OPEN
                self._circuit_open_time = time.time()
                logger.warning(
                    f"Circuit breaker for {self.name} re-opening - network error during recovery test"
                )
            else:
                self._failure_count += 1
                if self._failure_count >= self.circuit_breaker_threshold:
                    self._circuit_state = CircuitBreakerState.OPEN
                    self._circuit_open_time = time.time()
                    logger.warning(
                        f"Circuit breaker for {self.name} opening after {self._failure_count} network errors"
                    )

            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"API check failed: {str(e)}",
                metadata={
                    "url": self.url,
                    "error_type": "network",
                    "error": str(e),
                    "circuit_state": self._circuit_state.value,
                    "failures": self._failure_count,
                },
            )
        except Exception as e:
            # Unexpected errors - log but don't affect circuit breaker
            logger.error(f"Unexpected error in {self.name} health check: {e}")
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Unexpected error during API check: {str(e)}",
                metadata={
                    "url": self.url,
                    "error_type": "unexpected",
                    "error": str(e),
                    "circuit_state": self._circuit_state.value,
                },
            )
