"""Unit tests for CircuitBreaker resilience pattern.

Tests circuit breaker state transitions, failure handling,
and recovery behavior.
"""

import asyncio

import pytest

from idea_shared.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerState,
)


@pytest.mark.unit
class TestCircuitBreaker:
    """Test suite for CircuitBreaker class."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker with short timeouts for testing."""
        return CircuitBreaker(
            name="test",
            failure_threshold=3,
            recovery_timeout=1.0,  # Short timeout for fast tests
            half_open_max_calls=2,
        )

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, circuit_breaker):
        """Circuit breaker should start in CLOSED state."""
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.is_closed
        assert not circuit_breaker.is_open
        assert not circuit_breaker.is_half_open

    @pytest.mark.asyncio
    async def test_successful_call_keeps_circuit_closed(self, circuit_breaker):
        """Successful calls should keep circuit breaker closed."""

        async def successful_operation():
            return "success"

        result = await circuit_breaker.call(successful_operation)
        assert result == "success"
        assert circuit_breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_failures_open_circuit(self, circuit_breaker):
        """Circuit should open after failure threshold."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        # Fail threshold number of times
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        # Circuit should now be open
        assert circuit_breaker.state == CircuitBreakerState.OPEN
        assert circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self, circuit_breaker):
        """Open circuit should reject calls with CircuitBreakerError."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        assert circuit_breaker.is_open

        # Calls should now be rejected
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker.call(failing_operation)

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit_breaker):
        """Circuit should transition to HALF_OPEN after recovery timeout."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        assert circuit_breaker.is_open

        # Wait for recovery timeout
        await asyncio.sleep(circuit_breaker.recovery_timeout + 0.1)

        # Next call should transition to HALF_OPEN
        async def successful_operation():
            return "success"

        result = await circuit_breaker.call(successful_operation)
        assert result == "success"
        assert circuit_breaker.state == CircuitBreakerState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_closes_after_successful_calls(self, circuit_breaker):
        """HALF_OPEN circuit should close after enough successful calls."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        async def successful_operation():
            return "success"

        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        assert circuit_breaker.is_open

        # Wait for recovery
        await asyncio.sleep(circuit_breaker.recovery_timeout + 0.1)

        # Make successful calls to close circuit
        for _ in range(circuit_breaker.half_open_max_calls):
            result = await circuit_breaker.call(successful_operation)
            assert result == "success"

        # Circuit should now be closed
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.is_closed

    @pytest.mark.asyncio
    async def test_half_open_reopens_on_failure(self, circuit_breaker):
        """HALF_OPEN circuit should reopen on failure."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        async def successful_operation():
            return "success"

        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        # Wait for recovery
        await asyncio.sleep(circuit_breaker.recovery_timeout + 0.1)

        # First successful call transitions to HALF_OPEN
        await circuit_breaker.call(successful_operation)
        assert circuit_breaker.is_half_open

        # Failure should reopen circuit
        with pytest.raises(RuntimeError):
            await circuit_breaker.call(failing_operation)

        assert circuit_breaker.state == CircuitBreakerState.OPEN
        assert circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_context_manager_success(self, circuit_breaker):
        """Circuit breaker context manager should work with successful operations."""
        async with circuit_breaker:
            result = "success"

        assert circuit_breaker.is_closed
        assert result == "success"

    @pytest.mark.asyncio
    async def test_context_manager_failure(self, circuit_breaker):
        """Circuit breaker context manager should handle failures."""
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                async with circuit_breaker:
                    raise RuntimeError("Test failure")

        assert circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_cancelled_error_not_counted(self, circuit_breaker):
        """CancelledError should not count toward failure threshold."""

        async def cancelled_operation():
            raise asyncio.CancelledError()

        # CancelledError should not open circuit
        for _ in range(circuit_breaker.failure_threshold + 5):
            with pytest.raises(asyncio.CancelledError):
                await circuit_breaker.call(cancelled_operation)

        # Circuit should still be closed
        assert circuit_breaker.is_closed

    @pytest.mark.asyncio
    async def test_get_stats(self, circuit_breaker):
        """get_stats should return circuit breaker status."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        # Initially closed
        stats = circuit_breaker.get_stats()
        assert stats["name"] == "test"
        assert stats["state"] == CircuitBreakerState.CLOSED.value
        assert stats["failure_count"] == 0

        # Open after failures
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        stats = circuit_breaker.get_stats()
        assert stats["state"] == CircuitBreakerState.OPEN.value
        assert stats["failure_count"] == circuit_breaker.failure_threshold
        assert stats["last_failure_time"] is not None

    @pytest.mark.asyncio
    async def test_manual_reset(self, circuit_breaker):
        """Manual reset should close circuit immediately."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        assert circuit_breaker.is_open

        # Manual reset
        await circuit_breaker.reset()

        assert circuit_breaker.is_closed
        stats = circuit_breaker.get_stats()
        assert stats["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_success_resets_failure_count_in_closed_state(self, circuit_breaker):
        """Successful call should reset failure count in CLOSED state."""

        async def failing_operation():
            raise RuntimeError("Test failure")

        async def successful_operation():
            return "success"

        # Fail a few times (but not enough to open)
        for _ in range(circuit_breaker.failure_threshold - 1):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        # Success should reset count
        await circuit_breaker.call(successful_operation)

        # Should be able to fail threshold times again without opening
        for _ in range(circuit_breaker.failure_threshold - 1):
            with pytest.raises(RuntimeError):
                await circuit_breaker.call(failing_operation)

        assert circuit_breaker.is_closed
