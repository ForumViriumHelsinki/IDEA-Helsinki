"""Abstract base classes for health checks."""

import asyncio
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
import requests

from .models import HealthCheckResult


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
        self._cached_result: Optional[HealthCheckResult] = None
        self._cache_timestamp: float = 0

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
        import time

        now = time.time()
        if (
            self.cache_ttl > 0
            and self._cached_result
            and (now - self._cache_timestamp) < self.cache_ttl
        ):
            return self._cached_result

        try:
            result = await asyncio.wait_for(self.check(), timeout=self.timeout)
            if self.cache_ttl > 0:
                self._cached_result = result
                self._cache_timestamp = now
            return result
        except asyncio.TimeoutError:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Health check timed out after {self.timeout} seconds",
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Health check failed: {str(e)}",
            )

    def check_sync(self) -> HealthCheckResult:
        """Synchronous version of the health check.

        Returns:
            HealthCheckResult indicating the status of the check
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.check_with_cache())
            loop.close()
            return result
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
                test_file = self.path / ".health_check_test" if self.path.is_dir() else self.path.parent / f".health_check_{self.path.name}"
                try:
                    # Use async file operations
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: test_file.write_text("test"),
                    )
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        test_file.unlink,
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
        headers: Optional[Dict[str, str]] = None,
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
        self._circuit_open = False
        self._circuit_open_time = 0

    async def check(self) -> HealthCheckResult:
        """Check external API availability with circuit breaker.

        Returns:
            HealthCheckResult indicating API status
        """
        import time

        # Check if circuit breaker is open
        if self._circuit_open:
            if (time.time() - self._circuit_open_time) < self.circuit_breaker_timeout:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message="Circuit breaker is open",
                    metadata={
                        "circuit_open": True,
                        "failures": self._failure_count,
                    },
                )
            else:
                # Try to close the circuit
                self._circuit_open = False
                self._failure_count = 0

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    self.method,
                    self.url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status == self.expected_status:
                        self._failure_count = 0
                        return HealthCheckResult(
                            name=self.name,
                            status="healthy",
                            message=f"API responded with status {response.status}",
                            metadata={
                                "url": self.url,
                                "status_code": response.status,
                            },
                        )
                    else:
                        self._failure_count += 1
                        if self._failure_count >= self.circuit_breaker_threshold:
                            self._circuit_open = True
                            self._circuit_open_time = time.time()

                        return HealthCheckResult(
                            name=self.name,
                            status="unhealthy",
                            message=f"API returned unexpected status {response.status}",
                            metadata={
                                "url": self.url,
                                "status_code": response.status,
                                "expected": self.expected_status,
                            },
                        )

        except aiohttp.ClientError as e:
            self._failure_count += 1
            if self._failure_count >= self.circuit_breaker_threshold:
                self._circuit_open = True
                self._circuit_open_time = time.time()

            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"API check failed: {str(e)}",
                metadata={
                    "url": self.url,
                    "error": str(e),
                    "failures": self._failure_count,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Unexpected error during API check: {str(e)}",
            )