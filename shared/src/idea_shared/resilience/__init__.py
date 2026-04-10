"""Resilience infrastructure for IDEA-Helsinki services.

This module provides production-grade resilience patterns for handling
transient failures, preventing cascade shutdowns, and improving service stability.

Key Components:
- CircuitBreaker: Prevents thundering herd during service outages
- async_retry: Exponential backoff retry with jitter for async operations
- ErrorTracker: Tracks consecutive failures for adaptive error handling
"""

from idea_shared.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerState,
)
from idea_shared.resilience.retry import ErrorTracker, async_retry, with_retry

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerState",
    "ErrorTracker",
    "async_retry",
    "with_retry",
]
