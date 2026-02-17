"""
Circuit Breaker pattern implementation for preventing cascade failures.

A circuit breaker prevents repeated attempts to execute operations that are
likely to fail, allowing the system to recover gracefully and preventing
resource exhaustion (thundering herd problem).

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests fail fast
- HALF_OPEN: Testing recovery, limited requests allowed

Example:
    circuit_breaker = CircuitBreaker(
        name="influxdb",
        failure_threshold=5,
        recovery_timeout=60.0,
        half_open_max_calls=3
    )

    async def query_database():
        async with circuit_breaker:
            return await db.query()
"""

import asyncio
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from idea_shared.classes.Logger import Logger


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, name: str, message: str = None):
        self.name = name
        self.message = message or f"Circuit breaker '{name}' is OPEN"
        super().__init__(self.message)


class CircuitBreaker:
    """
    Async circuit breaker for preventing cascade failures.

    Tracks consecutive failures and transitions between states:
    CLOSED → OPEN (after failure_threshold failures)
    OPEN → HALF_OPEN (after recovery_timeout seconds)
    HALF_OPEN → CLOSED (after successful calls)
    HALF_OPEN → OPEN (if failures continue)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        excluded_exceptions: tuple[type[Exception], ...] = (asyncio.CancelledError,),
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker (used in logs)
            failure_threshold: Number of consecutive failures before opening
            recovery_timeout: Seconds to wait before testing recovery
            half_open_max_calls: Max successful calls needed to close from half-open
            excluded_exceptions: Exception types that don't trigger the circuit breaker
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.excluded_exceptions = excluded_exceptions

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._lock = asyncio.Lock()

        self.logger = Logger(f"CircuitBreaker[{name}]")

    @property
    def state(self) -> CircuitBreakerState:
        """Current state of the circuit breaker."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """True if circuit breaker is closed (normal operation)."""
        return self._state == CircuitBreakerState.CLOSED

    @property
    def is_open(self) -> bool:
        """True if circuit breaker is open (failing)."""
        return self._state == CircuitBreakerState.OPEN

    @property
    def is_half_open(self) -> bool:
        """True if circuit breaker is half-open (testing recovery)."""
        return self._state == CircuitBreakerState.HALF_OPEN

    async def call(self, func, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by func
        """
        async with self._lock:
            await self._check_state_transition()

            if self._state == CircuitBreakerState.OPEN:
                raise CircuitBreakerError(self.name)

        # Execute outside lock to allow concurrent operations
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            # Don't count excluded exceptions (like CancelledError) as failures
            if not isinstance(e, self.excluded_exceptions):
                await self._on_failure()
            raise

    async def _check_state_transition(self):
        """Check if circuit breaker should transition states."""
        if self._state == CircuitBreakerState.OPEN:
            # Check if enough time has passed to try recovery
            if self._last_failure_time:
                time_since_failure = (
                    datetime.now(UTC) - self._last_failure_time
                ).total_seconds()
                if time_since_failure >= self.recovery_timeout:
                    self.logger.info(
                        f"Transitioning to HALF_OPEN after {time_since_failure:.1f}s"
                    )
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._success_count = 0

    async def _on_success(self):
        """Handle successful operation."""
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                self.logger.debug(
                    f"HALF_OPEN success {self._success_count}/{self.half_open_max_calls}"
                )

                if self._success_count >= self.half_open_max_calls:
                    self.logger.info(
                        f"Transitioning to CLOSED after {self._success_count} successful calls"
                    )
                    self._state = CircuitBreakerState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitBreakerState.CLOSED:
                # Reset failure count on success in closed state
                if self._failure_count > 0:
                    self.logger.debug(
                        f"Resetting failure count from {self._failure_count} to 0"
                    )
                    self._failure_count = 0

    async def _on_failure(self):
        """Handle failed operation."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(UTC)

            if self._state == CircuitBreakerState.HALF_OPEN:
                self.logger.warning("Failure in HALF_OPEN state, transitioning to OPEN")
                self._state = CircuitBreakerState.OPEN
                self._success_count = 0
            elif (
                self._state == CircuitBreakerState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self.logger.error(
                    f"Failure threshold ({self.failure_threshold}) reached, transitioning to OPEN"
                )
                self._state = CircuitBreakerState.OPEN

    async def __aenter__(self):
        """Context manager entry - check circuit breaker state."""
        async with self._lock:
            await self._check_state_transition()

            if self._state == CircuitBreakerState.OPEN:
                raise CircuitBreakerError(self.name)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - record success/failure."""
        if exc_type is None:
            await self._on_success()
        elif not issubclass(exc_type, self.excluded_exceptions):
            await self._on_failure()
        return False  # Don't suppress exceptions

    def get_stats(self) -> dict:
        """
        Get current circuit breaker statistics.

        Returns:
            Dictionary with state, failure count, and timing info
        """
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time.isoformat()
            if self._last_failure_time
            else None,
        }

    async def reset(self):
        """Manually reset circuit breaker to closed state."""
        async with self._lock:
            self.logger.info("Manually resetting circuit breaker to CLOSED")
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
