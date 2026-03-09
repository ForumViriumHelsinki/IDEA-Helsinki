"""
Async retry infrastructure with exponential backoff.

Provides decorators and utilities for retrying async operations with
exponential backoff and jitter. Complements the low-level tenacity retries
in FCDInfluxDBManager with higher-level orchestration retry logic.

Example:
    @async_retry(max_attempts=3, base_delay=1.0)
    async def fetch_data():
        return await api.get()

    # Or use as function wrapper
    result = await with_retry(
        fetch_data,
        max_attempts=5,
        base_delay=2.0
    )
"""

import asyncio
import random
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

from idea_shared.classes.Logger import Logger

T = TypeVar("T")


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    Calculate exponential backoff delay with optional jitter.

    Args:
        attempt: Current attempt number (1-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Add random jitter to prevent thundering herd

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * 2^(attempt-1)
    delay = base_delay * (2 ** (attempt - 1))
    delay = min(delay, max_delay)

    if jitter:
        # Add jitter: random value between 50% and 100% of calculated delay
        delay = delay * (0.5 + random.random() * 0.5)

    return delay


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    excluded_exceptions: tuple[type[BaseException], ...] = (asyncio.CancelledError,),
    logger_name: str | None = None,
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        jitter: Add random jitter to delays
        excluded_exceptions: Exception types that should not be retried
        logger_name: Optional logger name (defaults to function name)

    Example:
        @async_retry(max_attempts=5, base_delay=2.0)
        async def fetch_data():
            return await api.get()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = Logger(logger_name or func.__name__)
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except excluded_exceptions:
                    # Don't retry excluded exceptions (like CancelledError)
                    raise
                except Exception as e:
                    last_exception = e

                    if attempt < max_attempts:
                        delay = calculate_backoff(
                            attempt, base_delay, max_delay, jitter
                        )
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed. Last error: {e}"
                        )

            # If we get here, all attempts failed
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry loop completed without success or exception")

        return wrapper

    return decorator


async def with_retry[T](
    func: Callable[..., Coroutine[Any, Any, T]],
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    excluded_exceptions: tuple[type[BaseException], ...] = (asyncio.CancelledError,),
    logger_name: str | None = None,
    **kwargs,
) -> T:
    """
    Execute async function with retry logic.

    This is a functional alternative to the @async_retry decorator,
    useful when you can't modify the function definition.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        max_attempts: Maximum number of attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        jitter: Add random jitter to delays
        excluded_exceptions: Exception types that should not be retried
        logger_name: Optional logger name
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        Exception: The last exception if all attempts fail

    Example:
        result = await with_retry(
            api.fetch_data,
            max_attempts=5,
            base_delay=2.0
        )
    """
    logger = Logger(logger_name or func.__name__)
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except excluded_exceptions:
            raise
        except Exception as e:
            last_exception = e

            if attempt < max_attempts:
                delay = calculate_backoff(attempt, base_delay, max_delay, jitter)
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_attempts} attempts failed. Last error: {e}")

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Retry loop completed without success or exception")


class ErrorTracker:
    """
    Tracks consecutive errors for adaptive error handling.

    Useful for implementing progressive backoff or circuit-breaking behavior
    at the application level.

    Example:
        tracker = ErrorTracker(max_consecutive=10)

        try:
            await operation()
            tracker.record_success()
        except Exception as e:
            tracker.record_failure()
            if tracker.should_escalate():
                raise  # Exit on systemic failure
    """

    def __init__(self, max_consecutive: int = 10):
        """
        Initialize error tracker.

        Args:
            max_consecutive: Maximum consecutive errors before escalation
        """
        self.max_consecutive = max_consecutive
        self._consecutive_errors = 0
        self._total_errors = 0
        self._total_successes = 0

    def record_success(self):
        """Record successful operation."""
        self._consecutive_errors = 0
        self._total_successes += 1

    def record_failure(self):
        """Record failed operation."""
        self._consecutive_errors += 1
        self._total_errors += 1

    @property
    def consecutive_errors(self) -> int:
        """Number of consecutive errors."""
        return self._consecutive_errors

    def should_escalate(self) -> bool:
        """True if consecutive errors exceed threshold."""
        return self._consecutive_errors >= self.max_consecutive

    def get_backoff_multiplier(self) -> float:
        """
        Get backoff multiplier based on consecutive errors.

        Returns value between 1.0 and 10.0 for adaptive backoff.
        """
        return min(1.0 + self._consecutive_errors * 0.5, 10.0)

    def get_stats(self) -> dict:
        """Get error tracking statistics."""
        return {
            "consecutive_errors": self._consecutive_errors,
            "total_errors": self._total_errors,
            "total_successes": self._total_successes,
            "should_escalate": self.should_escalate(),
        }

    def reset(self):
        """Reset all counters."""
        self._consecutive_errors = 0
        self._total_errors = 0
        self._total_successes = 0
