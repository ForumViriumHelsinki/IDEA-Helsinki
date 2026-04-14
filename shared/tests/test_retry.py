"""Unit tests for retry resilience patterns.

Tests async_retry decorator, with_retry function, and ErrorTracker.
"""

import asyncio

import pytest

from idea_shared.resilience.retry import (
    ErrorTracker,
    async_retry,
    calculate_backoff,
    with_retry,
)


@pytest.mark.unit
class TestCalculateBackoff:
    """Test suite for calculate_backoff function."""

    def test_exponential_growth(self):
        """Backoff should grow exponentially."""
        assert calculate_backoff(1, base_delay=1.0, jitter=False) == 1.0
        assert calculate_backoff(2, base_delay=1.0, jitter=False) == 2.0
        assert calculate_backoff(3, base_delay=1.0, jitter=False) == 4.0
        assert calculate_backoff(4, base_delay=1.0, jitter=False) == 8.0

    def test_max_delay_cap(self):
        """Backoff should be capped at max_delay."""
        result = calculate_backoff(10, base_delay=1.0, max_delay=10.0, jitter=False)
        assert result == 10.0

    def test_jitter_adds_randomness(self):
        """Backoff with jitter should vary."""
        results = [calculate_backoff(3, base_delay=1.0, jitter=True) for _ in range(10)]
        # All results should be between 50% and 100% of 4.0
        assert all(2.0 <= r <= 4.0 for r in results)
        # Results should vary (not all the same)
        assert len(set(results)) > 1

    def test_custom_base_delay(self):
        """Backoff should scale with base_delay."""
        assert calculate_backoff(2, base_delay=2.0, jitter=False) == 4.0
        assert calculate_backoff(3, base_delay=2.0, jitter=False) == 8.0


@pytest.mark.unit
class TestAsyncRetry:
    """Test suite for async_retry decorator."""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """Successful call should not retry."""
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0.01)
        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_operation()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Should retry on failure."""
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0.01)
        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Test failure")
            return "success"

        result = await failing_then_success()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded(self):
        """Should raise exception after max attempts."""
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Test failure")

        with pytest.raises(RuntimeError, match="Test failure"):
            await always_fails()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_cancelled_error_not_retried(self):
        """CancelledError should not be retried."""
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0.01)
        async def cancelled_operation():
            nonlocal call_count
            call_count += 1
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await cancelled_operation()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_backoff_between_retries(self):
        """Should wait between retries."""
        call_times = []

        @async_retry(max_attempts=3, base_delay=0.1, jitter=False)
        async def failing_operation():
            call_times.append(asyncio.get_running_loop().time())
            raise RuntimeError("Test failure")

        with pytest.raises(RuntimeError):
            await failing_operation()

        assert len(call_times) == 3
        # Check delays are approximately correct
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert 0.08 < delay1 < 0.15  # ~0.1s
        assert 0.18 < delay2 < 0.25  # ~0.2s


@pytest.mark.unit
class TestWithRetry:
    """Test suite for with_retry function."""

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Successful call should not retry."""
        call_count = 0

        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await with_retry(successful_operation, max_attempts=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_with_args(self):
        """Should pass arguments to function."""
        call_count = 0

        async def operation_with_args(x, y):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Test failure")
            return x + y

        result = await with_retry(
            operation_with_args, 10, 20, max_attempts=3, base_delay=0.01
        )
        assert result == 30
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_with_kwargs(self):
        """Should pass keyword arguments to function."""

        async def operation_with_kwargs(x, y=5):
            return x * y

        result = await with_retry(
            operation_with_kwargs, 10, y=3, max_attempts=3, base_delay=0.01
        )
        assert result == 30

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded(self):
        """Should raise exception after max attempts."""
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Test failure")

        with pytest.raises(RuntimeError, match="Test failure"):
            await with_retry(always_fails, max_attempts=3, base_delay=0.01)

        assert call_count == 3


@pytest.mark.unit
class TestErrorTracker:
    """Test suite for ErrorTracker class."""

    def test_initial_state(self):
        """Error tracker should start with zero errors."""
        tracker = ErrorTracker(max_consecutive=5)
        assert tracker.consecutive_errors == 0
        assert not tracker.should_escalate()

    def test_record_failure(self):
        """record_failure should increment consecutive errors."""
        tracker = ErrorTracker(max_consecutive=5)
        tracker.record_failure()
        assert tracker.consecutive_errors == 1
        tracker.record_failure()
        assert tracker.consecutive_errors == 2

    def test_record_success_resets_consecutive(self):
        """record_success should reset consecutive errors."""
        tracker = ErrorTracker(max_consecutive=5)
        tracker.record_failure()
        tracker.record_failure()
        assert tracker.consecutive_errors == 2

        tracker.record_success()
        assert tracker.consecutive_errors == 0

    def test_should_escalate(self):
        """should_escalate should be true when threshold exceeded."""
        tracker = ErrorTracker(max_consecutive=3)
        tracker.record_failure()
        tracker.record_failure()
        assert not tracker.should_escalate()

        tracker.record_failure()
        assert tracker.should_escalate()

    def test_get_backoff_multiplier(self):
        """Backoff multiplier should increase with consecutive errors."""
        tracker = ErrorTracker(max_consecutive=10)

        assert tracker.get_backoff_multiplier() == 1.0

        tracker.record_failure()
        assert tracker.get_backoff_multiplier() == 1.5

        tracker.record_failure()
        assert tracker.get_backoff_multiplier() == 2.0

        # Should be capped at 10.0
        for _ in range(20):
            tracker.record_failure()
        assert tracker.get_backoff_multiplier() == 10.0

    def test_get_stats(self):
        """get_stats should return error tracking info."""
        tracker = ErrorTracker(max_consecutive=5)

        stats = tracker.get_stats()
        assert stats["consecutive_errors"] == 0
        assert stats["total_errors"] == 0
        assert stats["total_successes"] == 0
        assert not stats["should_escalate"]

        tracker.record_failure()
        tracker.record_failure()
        tracker.record_success()

        stats = tracker.get_stats()
        assert stats["consecutive_errors"] == 0  # Reset by success
        assert stats["total_errors"] == 2
        assert stats["total_successes"] == 1

    def test_reset(self):
        """Reset should clear all counters."""
        tracker = ErrorTracker(max_consecutive=5)
        tracker.record_failure()
        tracker.record_failure()
        tracker.record_success()

        tracker.reset()

        stats = tracker.get_stats()
        assert stats["consecutive_errors"] == 0
        assert stats["total_errors"] == 0
        assert stats["total_successes"] == 0
