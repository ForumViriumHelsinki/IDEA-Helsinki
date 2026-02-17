# Kubernetes Debugging Patterns

## Feature Flag Provider Selection

Production uses `EnvironmentVariableProvider` (not JSON files). When a feature flag isn't taking effect:

1. Check which provider is active: `ENVIRONMENT` env var → selects provider in `initialization.py`
2. If `ENVIRONMENT=production`, flags must be set as `FEATURE_FLAG_<NAME>` env vars in Helm values
3. JSON file (`data/feature_flags.json`) is only read in development mode
4. If `FEATURE_FLAG_ENDPOINT` is set, GoFeatureFlag relay-proxy takes precedence over both

## Startup Probe vs Deployment Progress Deadline

Three separate timeout mechanisms interact during pod startup:

| Mechanism | Default | Controls |
|-----------|---------|----------|
| `startupProbe.failureThreshold * periodSeconds` | Service-specific | How long K8s waits before killing the container |
| `readinessProbe` | 30s to unready | When pod is removed from service endpoints |
| `.spec.progressDeadlineSeconds` | 600s (10 min) | When Deployment marks rollout as failed |

The Deployment progress deadline is independent of probe configuration. A pod can pass startup probes but still trigger `ProgressDeadlineExceeded` if it hasn't become ready within the deadline. Both must accommodate the longest expected initialization time.

## Health Check Grace Periods

For services with long initialization (backfill, data sync):

- Critical health checks that depend on files created during initialization should have a `startup_grace_minutes` parameter
- During grace period, return healthy to avoid blocking readiness
- Startup-only checks (`startup_only=True` in HealthServer) verify external connectivity without requiring data files
- The `SegmentMappingIntegrityHealthCheck` uses a 15-minute grace period for initial backfill

## GCS FUSE File I/O

GCS FUSE-mounted volumes have distinct failure modes from local filesystems.

### ESTALE (Stale File Handle)

GCS FUSE uses a metadata cache (default 60s TTL). When one pod writes a file and another reads it, the reader may get ESTALE (errno 116) if its cached metadata is stale.

**Application-level fix:** Use `read_json_with_retry()` and `atomic_write_json()` from `idea_shared.threading.file_locks` — both implement exponential backoff + jitter for ESTALE.

**Infrastructure-level fix:** Reduce metadata cache TTL in PV `mountOptions`:
```yaml
mountOptions:
  - metadata-cache:ttl-secs=10  # NOT stat-cache-ttl or type-cache-ttl (deprecated)
```

### Correct Mount Option Names

| Deprecated (pre-v2) | Current (v2+) |
|---------------------|---------------|
| `stat-cache-ttl` | `metadata-cache:ttl-secs` |
| `type-cache-ttl` | `metadata-cache:ttl-secs` (same param) |
| `max-retries` | Not a gcsfuse option; handle at application level |

### File Locking

GCS FUSE does **not** support file locking. Single-writer discipline is enforced at the application level (one service owns writes to each file).

### TOCTOU Avoidance

Never use `path.exists()` followed by `open()` on GCS FUSE — the file can disappear between calls. Instead, catch `FileNotFoundError` inside the operation.

## CrashLoopBackOff Debugging Checklist

1. Check pod events: `kubectl describe pod <name>` — look for OOMKilled, probe failures, progress deadline
2. Check container count: `Containers: 1/2` suggests sidecar failure (e.g., GCS FUSE)
3. Check logs from previous instance: `kubectl logs <pod> --previous`
4. Verify feature flags are reaching the service (check provider, env vars, not just config files)
5. Check if service exits after completing work (missing continuous loop)
6. Verify Deployment progress deadline isn't shorter than startup time
