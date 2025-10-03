# Health Check System Documentation

## Overview

The IDEA-Helsinki health check system provides a comprehensive framework for monitoring service health and readiness in Kubernetes environments. It implements standardized health endpoints compatible with Kubernetes liveness, readiness, and startup probes.

## Health Endpoints

The health server exposes the following endpoints:

### `/healthz` - Liveness Probe

**Purpose**: Indicates whether the service process is alive and running.

**When to use**: Kubernetes uses this to determine if a pod should be restarted.

**Response Codes**:
- `200 OK` - Service is alive

**Response Example**:
```json
{
  "status": "ok",
  "timestamp": "2025-10-03T18:00:00Z"
}
```

**Expected Behavior**:
- Always returns 200 if the server is running
- No dependency checks performed
- Fast response (<100ms)
- Should only fail if the process is dead or hung

### `/ready` - Readiness Probe

**Purpose**: Indicates whether the service is ready to accept traffic.

**When to use**: Kubernetes uses this to determine if a pod should receive traffic from services/load balancers.

**Response Codes**:
- `200 OK` - Service is ready (all critical checks passed)
- `503 Service Unavailable` - Service is not ready (one or more critical checks failed)

**Response Example (Healthy)**:
```json
{
  "ready": true,
  "checks": {
    "influxdb": "healthy",
    "azure_storage": "healthy",
    "segment_mapping": "healthy"
  },
  "timestamp": "2025-10-03T18:00:00Z"
}
```

**Response Example (Unhealthy)**:
```json
{
  "ready": false,
  "checks": {
    "influxdb": "unhealthy",
    "azure_storage": "healthy",
    "segment_mapping": "degraded"
  },
  "timestamp": "2025-10-03T18:00:00Z"
}
```

**Expected Behavior**:
- Runs all registered health checks
- Returns 503 if ANY critical check is unhealthy
- Non-critical checks don't affect readiness status
- Should check critical dependencies (databases, required files, etc.)

### `/startup` - Startup Probe

**Purpose**: Indicates whether the service has completed initialization.

**When to use**: Kubernetes uses this for slow-starting containers. Once this succeeds, liveness and readiness probes take over.

**Response Codes**:
- `200 OK` - Startup completed successfully
- `503 Service Unavailable` - Still initializing or startup failed

**Response Example**:
```json
{
  "ready": true,
  "checks": {
    "data_directory": "healthy",
    "influxdb": "healthy"
  },
  "timestamp": "2025-10-03T18:00:00Z"
}
```

**Expected Behavior**:
- Uses startup-specific checks if configured, otherwise uses readiness checks
- Returns 503 until all startup checks pass
- Once successful, subsequent calls continue to return 200 (idempotent)
- Allows longer initialization times without triggering liveness failures

### `/metrics` - Metrics Endpoint

**Purpose**: Exposes service metrics for monitoring systems like Prometheus.

**When to use**: Optional endpoint for observability and monitoring.

**Availability**: Only available when `enable_metrics=True`

**Response Example**:
```json
{
  "metrics": {
    "health_checks_total": 5,
    "service_name": "IDEA Helsinki Service"
  },
  "timestamp": "2025-10-03T18:00:00Z"
}
```

**Expected Behavior**:
- Returns 404 if metrics are disabled
- Placeholder for future Prometheus integration
- Does not affect pod lifecycle decisions

### `/health/detail` - Detailed Health Endpoint

**Purpose**: Provides detailed health check information for debugging and troubleshooting.

**When to use**: Manual debugging, dashboards, or detailed monitoring.

**Response Example**:
```json
{
  "service": "IDEA Helsinki Service",
  "timestamp": "2025-10-03T18:00:00Z",
  "checks": {
    "influxdb": {
      "status": "healthy",
      "message": "InfluxDB is accessible",
      "metadata": {
        "org": "idea_helsinki",
        "bucket": "fcd_data"
      },
      "critical": true
    },
    "azure_storage": {
      "status": "degraded",
      "message": "High latency detected",
      "metadata": {
        "latency_ms": 2500
      },
      "critical": false
    }
  }
}
```

**Expected Behavior**:
- Always returns 200 (never affects pod status)
- Includes detailed information about each check
- Shows check status, messages, metadata, and criticality
- Useful for troubleshooting

## Health States

### `healthy`
- Check passed successfully
- All expected conditions are met
- Service can operate normally

### `unhealthy`
- Check failed
- Critical dependency is unavailable
- Service cannot operate properly
- For critical checks: causes readiness probe to fail

### `degraded`
- Check partially failed or performing sub-optimally
- Service can still operate but with reduced capabilities
- Example: High latency, circuit breaker open, stale data
- For critical checks: causes readiness probe to fail
- For non-critical checks: doesn't affect readiness

## Available Health Checks

### Base Health Checks

#### `HealthCheck` (Abstract Base)
Base class for all health checks.

**Parameters**:
- `name`: Unique identifier for the check
- `timeout`: Maximum time (seconds) before timeout
- `critical`: Whether this check is critical for readiness
- `cache_ttl`: Cache duration (seconds) for results

#### `FileSystemHealthCheck`
Checks file system accessibility.

**Use cases**:
- Verify data directories exist
- Check read/write permissions
- Validate required files are present

**Example**:
```python
check = FileSystemHealthCheck(
    name="data_directory",
    path="/app/data",
    check_write=True,
    critical=True
)
```

#### `ExternalAPIHealthCheck`
Checks external API availability with circuit breaker pattern.

**Features**:
- Circuit breaker to prevent cascading failures
- Configurable failure threshold
- Automatic recovery testing

**Use cases**:
- Monitor external service availability
- Detect API outages
- Prevent request storms to failing services

**Example**:
```python
check = ExternalAPIHealthCheck(
    name="external_api",
    url="https://api.example.com/health",
    method="GET",
    expected_status=200,
    circuit_breaker_threshold=3,
    circuit_breaker_timeout=60.0,
    critical=False
)
```

#### `DatabaseHealthCheck` (Abstract Base)
Base class for database connectivity checks.

### IDEA-Helsinki Specific Checks

#### `InfluxDBHealthCheck`
Checks InfluxDB connectivity and availability.

**Example**:
```python
check = InfluxDBHealthCheck(
    name="influxdb_fcd",
    url="http://localhost:8086",
    token="your_token",
    org="idea_helsinki",
    bucket="fcd_data",
    critical=True
)
```

#### `AzureBlobStorageHealthCheck`
Checks Azure Blob Storage accessibility.

**Example**:
```python
check = AzureBlobStorageHealthCheck(
    name="azure_storage",
    account_name="your_account",
    container_name="fcd-data",
    sas_token="your_sas_token",
    critical=True
)
```

#### `WFSServiceHealthCheck`
Checks Helsinki WFS service availability.

**Example**:
```python
check = WFSServiceHealthCheck(
    name="helsinki_wfs",
    url="https://kartta.hel.fi/ws/geoserver/avoindata/wfs",
    critical=True
)
```

#### `FCDDataFreshnessHealthCheck`
Checks if FCD data is fresh (recent enough).

**Example**:
```python
check = FCDDataFreshnessHealthCheck(
    name="fcd_freshness",
    url="http://localhost:8086",
    token="your_token",
    org="idea_helsinki",
    bucket="fcd_data",
    max_age_minutes=30,
    critical=False
)
```

#### `SegmentMappingIntegrityHealthCheck`
Validates segment mapping files integrity.

**Example**:
```python
check = SegmentMappingIntegrityHealthCheck(
    name="segment_mapping",
    mapping_file_path="data/segments_mapping.json",
    history_file_path="data/master_segment_history.json",
    critical=True
)
```

## Troubleshooting Guide

### Liveness Probe Failures

**Symptom**: Pod is being restarted by Kubernetes

**Possible Causes**:
1. **Application deadlock** - The process is hung
2. **Health server not starting** - Port binding failure
3. **Timeout too short** - Health endpoint can't respond in time

**Solutions**:
1. Check application logs for deadlocks or infinite loops
2. Verify port is not already in use: `netstat -tulpn | grep 8080`
3. Increase `timeoutSeconds` in Kubernetes probe configuration
4. Check if application has enough resources (CPU/memory)

**Debugging**:
```bash
# Check if health endpoint responds
curl http://localhost:8080/healthz

# Check server logs
kubectl logs <pod-name>

# Check pod events
kubectl describe pod <pod-name>
```

### Readiness Probe Failures

**Symptom**: Pod shows as not ready, no traffic is routed to it

**Possible Causes**:
1. **Critical dependency unavailable** - Database, storage, or API is down
2. **Configuration error** - Invalid credentials or connection strings
3. **Resource exhaustion** - Service can't access required files/directories
4. **Network issues** - Can't reach external services

**Solutions**:
1. Check `/health/detail` endpoint for specific check failures
2. Verify all critical services are running and accessible
3. Validate configuration and credentials
4. Check network connectivity to dependencies

**Debugging**:
```bash
# Get detailed health status
curl http://localhost:8080/health/detail

# Check specific service connectivity
# For InfluxDB:
curl http://localhost:8086/health

# For Azure Storage (if accessible):
az storage account show --name <account-name>

# Check Kubernetes service endpoints
kubectl get endpoints
```

### Startup Probe Failures

**Symptom**: Pod stuck in initializing state, eventually restarts

**Possible Causes**:
1. **Slow initialization** - Service takes longer than expected to start
2. **Missing dependencies** - Required files or services not available at startup
3. **Configuration issues** - Invalid startup configuration

**Solutions**:
1. Increase `failureThreshold` or `periodSeconds` in startup probe
2. Ensure all required directories and files exist before pod starts (init containers)
3. Check startup logs for configuration errors
4. Consider using startup-specific health checks with lower requirements

**Debugging**:
```bash
# Check startup probe status
curl http://localhost:8080/startup

# View startup logs
kubectl logs <pod-name> --previous  # If pod restarted
kubectl logs <pod-name>  # Current attempt

# Check init container logs
kubectl logs <pod-name> -c <init-container-name>
```

### Circuit Breaker Open

**Symptom**: External API health check shows "degraded" status with "Circuit breaker is open" message

**Explanation**: Circuit breaker has detected multiple failures and is preventing requests to protect the system.

**Expected Behavior**:
1. After threshold failures (default 3), circuit opens
2. Requests are blocked for timeout period (default 60s)
3. Circuit transitions to half-open to test recovery
4. If test succeeds, circuit closes; if fails, reopens

**Solutions**:
1. **If expected** - Wait for circuit breaker timeout to allow recovery test
2. **If persistent** - Investigate why external service is failing:
   - Check external service health
   - Verify network connectivity
   - Validate credentials/tokens
   - Check rate limits

**Debugging**:
```bash
# Check circuit breaker state
curl http://localhost:8080/health/detail | jq '.checks.external_api'

# Look for circuit state and time remaining
{
  "status": "degraded",
  "message": "Circuit breaker is open",
  "metadata": {
    "circuit_state": "open",
    "failures": 3,
    "time_remaining": 45.2
  }
}
```

### High Memory Usage

**Symptom**: Health server consuming excessive memory

**Possible Causes**:
1. **Cache accumulation** - Many health checks with long TTLs
2. **Memory leak** - Unclosed connections or resources

**Solutions**:
1. Reduce `cache_ttl` for health checks
2. Ensure health checks properly close connections
3. Monitor memory usage over time
4. Consider restarting pods periodically

### Port Already in Use

**Symptom**: Health server fails to start with "Address already in use" error

**Solutions**:
1. Change health server port in configuration
2. Check if another process is using the port: `lsof -i :8080`
3. Ensure only one health server instance per pod
4. Verify no port conflicts in Kubernetes service definition

## Monitoring Best Practices

### Kubernetes Probe Configuration

#### Liveness Probe
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10      # Wait for initial startup
  periodSeconds: 10             # Check every 10 seconds
  timeoutSeconds: 5             # Wait up to 5 seconds for response
  failureThreshold: 3           # Restart after 3 consecutive failures
  successThreshold: 1           # One success = healthy
```

**Recommendations**:
- Set `initialDelaySeconds` to cover typical startup time
- Use `periodSeconds` of 10-30 seconds (balance between responsiveness and overhead)
- Set `timeoutSeconds` < `periodSeconds`
- Use `failureThreshold` of 3-5 to avoid restarts on transient issues

#### Readiness Probe
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5        # Shorter than liveness
  periodSeconds: 5              # Check more frequently
  timeoutSeconds: 3             # Shorter timeout acceptable
  failureThreshold: 2           # Remove from service faster
  successThreshold: 1           # One success = ready
```

**Recommendations**:
- Shorter `periodSeconds` than liveness (5-10 seconds) for faster traffic routing
- Lower `failureThreshold` to quickly remove unhealthy pods from service
- Start checking sooner with shorter `initialDelaySeconds`

#### Startup Probe
```yaml
startupProbe:
  httpGet:
    path: /startup
    port: 8080
  initialDelaySeconds: 0        # Start checking immediately
  periodSeconds: 5              # Check frequently
  timeoutSeconds: 3             # Reasonable timeout
  failureThreshold: 60          # Allow up to 5 minutes (60 * 5s)
  successThreshold: 1           # One success = started
```

**Recommendations**:
- Use for slow-starting services (data loading, cache warming)
- Set `failureThreshold * periodSeconds` > maximum startup time
- Once successful, liveness and readiness probes take over
- Prevents premature liveness failures during startup

### Health Check Design

#### Critical vs Non-Critical

**Mark as Critical** (`critical=True`):
- Database connections required for core functionality
- Required configuration files
- Essential external services
- Data directories that must be writable

**Mark as Non-Critical** (`critical=False`):
- Optional caches
- Metrics collection services
- Non-essential external services
- Degraded mode services

#### Cache Configuration

**Use Caching** (`cache_ttl > 0`):
- Expensive checks (database queries, external APIs)
- Checks that don't change frequently
- Reduces load on dependencies

**Recommended TTL Values**:
- Database connectivity: 5-10 seconds
- External APIs: 30-60 seconds
- File system checks: 30-300 seconds
- Data freshness checks: 30-120 seconds

**Don't Cache**:
- Very fast checks (<10ms)
- Checks that must always be current
- During development/debugging

#### Timeout Configuration

**Timeout Guidelines**:
- Local database: 2-5 seconds
- Remote database: 5-10 seconds
- External APIs: 5-15 seconds
- File system: 1-2 seconds

**Important**:
- Set timeout < Kubernetes probe timeout
- Consider network latency
- Add buffer for busy systems

### Alerting

#### Metrics to Monitor

1. **Health Check Failure Rate**
   - Alert on sustained failures (>5 minutes)
   - Track failure patterns

2. **Readiness Transitions**
   - Alert on frequent ready/not-ready transitions (flapping)
   - Indicates unstable dependencies

3. **Startup Time**
   - Alert on increasing startup times
   - May indicate data growth or performance degradation

4. **Circuit Breaker Events**
   - Track when circuit breakers open
   - Monitor external service health

#### Recommended Alerts

```yaml
# Example Prometheus alert rules
groups:
  - name: health_checks
    rules:
      # Pod not ready for 5 minutes
      - alert: PodNotReady
        expr: kube_pod_status_ready{condition="false"} > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Pod {{ $labels.pod }} not ready"

      # Pod restart loop
      - alert: PodRestartLoop
        expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Pod {{ $labels.pod }} restarting frequently"
```

### Logging

**Log Health Events**:
- Health check failures (ERROR level)
- Circuit breaker state changes (WARNING level)
- Health server startup/shutdown (INFO level)
- Check addition/removal (INFO level)

**Example Log Messages**:
```
INFO: Health server started on 0.0.0.0:8080
INFO: Added health check: influxdb
WARNING: Health check influxdb failed: Connection timeout
WARNING: Circuit breaker for external_api opening after 3 failures
ERROR: Health check azure_storage failed with error: Authentication failed
```

### Service-Specific Guidance

#### FCD Manager Service
- **Critical**: InfluxDB, Azure Storage, data directory
- **Non-Critical**: External APIs (can work with cached data)
- **Startup**: Verify segment mapping files exist

#### Traffic Monitor Service
- **Critical**: WFS service, InfluxDB, segment mapping integrity
- **Non-Critical**: Metrics endpoints
- **Startup**: Validate configuration files

#### IDEA Helsinki Service
- **Critical**: InfluxDB (both buckets), segment mapping
- **Non-Critical**: FCD data freshness, external metrics
- **Startup**: Check data files, validate InfluxDB buckets exist

### Performance Considerations

1. **Minimize Check Overhead**
   - Use caching for expensive checks
   - Run checks concurrently (handled automatically)
   - Keep timeout values reasonable

2. **Resource Limits**
   - Health checks run in same process as service
   - Include health check overhead in resource requests
   - Typical overhead: <50MB memory, <0.1 CPU

3. **Network Impact**
   - External API checks generate network traffic
   - Use caching to reduce request frequency
   - Consider circuit breakers to prevent request storms

### Testing Health Checks

#### Manual Testing
```bash
# Test liveness
curl http://localhost:8080/healthz

# Test readiness
curl http://localhost:8080/ready

# Get detailed status
curl http://localhost:8080/health/detail | jq

# Test with timeouts
curl --max-time 2 http://localhost:8080/ready

# Simulate dependency failure
# (e.g., stop InfluxDB and verify readiness fails)
docker stop influxdb
curl http://localhost:8080/ready  # Should return 503
```

#### Integration Testing
- Include health check tests in CI/CD pipeline
- Test all health states (healthy, unhealthy, degraded)
- Verify circuit breaker behavior
- Test startup sequence
- Validate Kubernetes probe configuration

#### Load Testing
- Verify health checks don't degrade under load
- Test concurrent health check execution
- Validate timeout behavior under stress
- Monitor resource usage during health checks

## Additional Resources

- [Kubernetes Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- Example usage: `shared/src/idea_shared/health/example_usage.py`
- API reference: Source code documentation in `shared/src/idea_shared/health/`
