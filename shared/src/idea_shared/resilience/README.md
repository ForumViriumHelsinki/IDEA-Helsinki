# Resilience Infrastructure

Production-grade resilience patterns for IDEA-Helsinki services to handle transient failures gracefully.

## Overview

This module provides resilience infrastructure that prevents cascade failures, implements intelligent retry logic, and ensures services can recover from temporary outages without requiring pod restarts.

### Key Components

1. **Circuit Breaker** (`circuit_breaker.py`): Prevents thundering herd during service outages
2. **Async Retry** (`retry.py`): Exponential backoff retry with jitter
3. **Error Tracker** (`retry.py`): Tracks consecutive failures for adaptive error handling

## Circuit Breaker

The circuit breaker prevents repeated attempts to execute operations that are likely to fail, allowing the system to recover gracefully.

### States

- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Failure threshold exceeded, requests fail fast
- **HALF_OPEN**: Testing recovery, limited requests allowed

### State Transitions

```
CLOSED → OPEN (after failure_threshold failures)
OPEN → HALF_OPEN (after recovery_timeout seconds)
HALF_OPEN → CLOSED (after successful calls)
HALF_OPEN → OPEN (if failures continue)
```

### Usage

```python
from idea_shared.resilience import CircuitBreaker

# Create circuit breaker
circuit_breaker = CircuitBreaker(
    name="influxdb",
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=60.0,    # Wait 60s before testing recovery
    half_open_max_calls=3     # Need 3 successes to close
)

# Use as context manager
async def query_database():
    async with circuit_breaker:
        return await db.query()

# Or use call method
result = await circuit_breaker.call(db.query)
```

### Integration Example (IdeaHelsinkiRoadSegment)

```python
class IdeaHelsinkiRoadSegment:
    def __init__(self, ...):
        self.db_circuit_breaker = CircuitBreaker(
            name=f"influxdb-{segment_id}",
            failure_threshold=5,
            recovery_timeout=60.0
        )

    async def __get_segment_data(self):
        # Protect database operations with circuit breaker
        async with self.db_circuit_breaker:
            with FCDInfluxDBManager(...) as manager:
                return await manager.get_data()
```

### Benefits

- **Prevents Cascade Failures**: One failing dependency doesn't bring down entire service
- **Fail Fast**: Open circuit rejects requests immediately (no wasted resources)
- **Automatic Recovery**: Tests recovery periodically without manual intervention
- **Resource Protection**: Prevents thundering herd when service recovers

## Async Retry

Retry infrastructure with exponential backoff and jitter for async operations.

### Features

- Exponential backoff (delays grow exponentially)
- Jitter (randomness prevents thundering herd)
- Configurable max attempts and delays
- Excluded exceptions (e.g., CancelledError not retried)

### Usage

#### Decorator

```python
from idea_shared.resilience.retry import async_retry

@async_retry(max_attempts=5, base_delay=2.0, max_delay=60.0)
async def fetch_data():
    return await api.get()

result = await fetch_data()
```

#### Function Wrapper

```python
from idea_shared.resilience.retry import with_retry

result = await with_retry(
    api.fetch_data,
    max_attempts=5,
    base_delay=2.0,
    max_delay=60.0
)
```

### Integration Example (IdeaHelsinkiManager)

```python
async def _run_worker_with_error_isolation(self, segment_instance):
    """Run worker with exponential backoff retry."""
    consecutive_errors = 0
    max_consecutive_errors = 10

    while consecutive_errors < max_consecutive_errors:
        try:
            await segment_instance.run_lifecycle()
            consecutive_errors = 0  # Reset on success
        except asyncio.CancelledError:
            raise  # Always propagate cancellation
        except Exception as e:
            consecutive_errors += 1
            backoff = calculate_backoff(attempt=consecutive_errors, base_delay=5.0, max_delay=60.0)
            await asyncio.sleep(backoff)
```

## Error Tracker

Tracks consecutive errors for adaptive error handling and backoff.

### Usage

```python
from idea_shared.resilience.retry import ErrorTracker

tracker = ErrorTracker(max_consecutive=10)

try:
    await operation()
    tracker.record_success()
except Exception:
    tracker.record_failure()

    if tracker.should_escalate():
        # Too many consecutive errors - escalate
        raise

    # Adaptive backoff based on error frequency
    backoff = tracker.get_backoff_multiplier() * base_delay
    await asyncio.sleep(backoff)
```

### Integration Example (IdeaHelsinkiManager)

```python
class IdeaHelsinkiManager:
    def __init__(self, ...):
        self.error_tracker = ErrorTracker(max_consecutive=10)

    async def run_main_loop(self):
        while True:
            try:
                await self._run_management_cycle()
                self.error_tracker.record_success()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.error_tracker.record_failure()

                if self.error_tracker.should_escalate():
                    # Systemic failure - exit to trigger pod restart
                    raise

                # Adaptive backoff
                backoff = min(self.error_tracker.consecutive_errors * 5, 60)
                await asyncio.sleep(backoff)
```

## Architecture Patterns

### Exception Boundaries

Every level of the orchestrator has exception handling:

1. **Main Loop** (`IdeaHelsinkiManager.run_main_loop`): Catches errors, implements adaptive backoff, escalates on systemic failure
2. **Worker Wrapper** (`_run_worker_with_error_isolation`): Isolates worker failures, prevents cascade to main loop
3. **Worker Lifecycle** (`IdeaHelsinkiRoadSegment.run_lifecycle`): Catches errors, implements per-worker retry
4. **Database Operations**: Protected by circuit breaker, retried by tenacity (low-level)

### Key Design Principles

1. **Never Crash Main Loop**: Orchestration must survive transient errors
2. **Fail Fast with Circuit Breakers**: Don't waste resources on known failures
3. **Retry with Backoff**: Give systems time to recover
4. **Graceful Degradation**: Service survives partial failures
5. **Always Re-raise CancelledError**: Never swallow cancellation signals
6. **Cleanup Resources**: Always cleanup in finally blocks

### Before vs After

**Before (Vulnerable):**
```
InfluxDB Error
    ↓
Worker fails → logs error
    ↓
Main loop discovers issue → unhandled exception
    ↓
Service exits (sys.exit(1))
    ↓
Pod restart → CrashLoopBackOff
```

**After (Resilient):**
```
InfluxDB Error (multiple workers)
    ↓
Circuit Breaker: CLOSED → OPEN (after 5 failures)
    ↓
All subsequent requests fail fast (no wasted retries)
    ↓
Worker catches error → exponential backoff → retry
    ↓
Main loop catches error → adaptive backoff → continues
    ↓
After 60s: Circuit Breaker → HALF_OPEN (test recovery)
    ↓
Success → Circuit Breaker → CLOSED (normal operation)
    ↓
Service survives → workers auto-retry → recovers when InfluxDB returns
```

## Health Check Integration

Circuit breaker and error tracker stats are exposed via health checks:

```python
async def get_worker_health_stats(self):
    return {
        "total_workers": len(self.active_segments),
        "circuit_breaker": self.circuit_breaker.get_stats(),
        "error_tracker": self.error_tracker.get_stats(),
        ...
    }
```

Example health check response:
```json
{
  "total_workers": 5,
  "circuit_breaker": {
    "name": "manager",
    "state": "closed",
    "failure_count": 0,
    "last_failure_time": null
  },
  "error_tracker": {
    "consecutive_errors": 0,
    "total_errors": 3,
    "total_successes": 127,
    "should_escalate": false
  }
}
```

## Testing

Comprehensive unit tests ensure reliability:

- **Circuit Breaker Tests** (`shared/tests/test_circuit_breaker.py`): State transitions, failure handling, recovery
- **Retry Tests** (`shared/tests/test_retry.py`): Exponential backoff, max attempts, exception handling

Run tests:
```bash
# All resilience tests
uv run --package idea-shared --directory shared python -m pytest tests/test_circuit_breaker.py tests/test_retry.py -v

# Just circuit breaker tests
uv run --package idea-shared --directory shared python -m pytest tests/test_circuit_breaker.py -v -m unit

# Just retry tests
uv run --package idea-shared --directory shared python -m pytest tests/test_retry.py -v -m unit
```

## Performance Considerations

### Circuit Breaker

- **Memory**: Minimal (~100 bytes per instance)
- **CPU**: Negligible (simple state checks)
- **Latency**: <1ms overhead per call

### Retry Logic

- **Backoff Delays**: Exponential (1s → 2s → 4s → 8s → ...)
- **Jitter**: Prevents thundering herd (+/- 50% randomness)
- **Max Delay**: Capped at 60s to prevent excessive waits

### Error Tracker

- **Memory**: Minimal (~50 bytes per instance)
- **CPU**: Negligible (simple counter operations)

## Related PRs

- **PR #185**: Added tenacity-based retry to `FCDInfluxDBManager` (low-level database retries)
- **PR #195**: Fixed FCD Manager CrashLoopBackOff (similar issue, different service)
- **Issue #196**: Orchestrator cascade shutdown from InfluxDB connectivity loss (this implementation)

## Future Enhancements

1. **Rate Limiting**: Limit request rate during recovery
2. **Bulkhead Pattern**: Isolate different resource pools
3. **Timeout Decorators**: Automatic timeout for long-running operations
4. **Metrics Integration**: Prometheus metrics for circuit breaker states
5. **Distributed Circuit Breaker**: Shared circuit breaker state across pods (via Redis)

## References

- [Circuit Breaker Pattern (Martin Fowler)](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Resilience4j Circuit Breaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [tenacity Python library](https://github.com/jd/tenacity) (used for low-level retries)
- [Exponential Backoff And Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
