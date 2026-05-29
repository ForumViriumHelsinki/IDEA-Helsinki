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

## Diagnosing `/ready` 503 — start with `/health/detail`

When a pod is stuck unready (readiness probe 503) but logs show the application doing its work, the failing health check names itself in the JSON response body. Always exec and curl `/health/detail` before diving into code:

```bash
kubectl --context=<ctx> -n idea-helsinki exec <pod> -- wget -qO- http://localhost:8080/health/detail
```

Look for the first check with `"status": "unhealthy"` and `"critical": true` — that is what's forcing `/ready` to 503. Non-critical checks (`critical=False`) surface as `degraded` and do NOT fail readiness; don't chase those first.

Pattern in this codebase: readiness is the logical AND of all critical checks. A single stale/missing file dependency is enough to keep a Deployment at `0/1 Available` indefinitely.

## Probe timeouts — event-loop starvation vs CPU throttling

When `kubectl describe pod` shows `probe failed: context deadline exceeded` (not `503 Service Unavailable`), the handler never responded in time. Two distinct root causes, distinguishable from inside the pod:

1. **Check CPU throttling first:**
   ```bash
   kubectl --context=<ctx> exec <pod> -- cat /sys/fs/cgroup/cpu.stat
   ```
   Low `nr_throttled` and `throttled_usec` (≪1s total over lifetime) rules out CFS throttling.

2. **Measure trivial `/healthz` latency** (the handler should return 200 in <10ms):
   ```bash
   for i in 1 2 3 4 5 6 7 8 9 10; do
     kubectl exec <pod> -- sh -c 'time wget -qO- http://localhost:8080/healthz'
   done
   ```
   Bimodal latency with >1000× jitter on a zero-work endpoint (e.g. 66ms → 2210ms → timeout) is asyncio event-loop starvation, not CPU. The loop is spending seconds between yields and can't schedule the uvicorn task.

Individual check latencies from `/health/detail` (`latency_ms`) help locate the starvation source: fast checks but slow `/healthz` = pure loop saturation; slow checks = worker thread pool saturation (checks queue in `run_in_executor` behind worker I/O).

## HealthServer threading — `start_async()` vs `start_background()`

`shared/src/idea_shared/health/server.py` provides both. Choose correctly:

| Method | Runs on | Use when |
|--------|---------|----------|
| `start_async()` | Application's asyncio loop | Small workloads, health handler guaranteed to get scheduled within probe timeout |
| `start_background()` | Dedicated daemon thread + its own event loop | Many concurrent workers, loop may be saturated by validation/I/O bursts |

The orchestrator's probe timeouts were caused by `start_async()` sharing the loop with 2,778 workers (#396). When in doubt, default to `start_background()` — the health endpoint's job is to stay responsive regardless of application load.

## Feature-flag-gated file producers — audit consumers' health checks

When a feature flag changes which service produces a file (or stops producing it), every consumer's `critical=True` health check that asserts that file must be gated on the same flag. Otherwise the consumer's `/ready` fails forever in the new mode.

This bit us in #398: `USE_SQLITE_STORAGE` stopped `segments_mapping.json` production, but `FCDMappingHealthCheck(critical=True)` in traffic-monitor was registered unconditionally — 4+ days stuck at `0/1 Available`.

**When flipping a storage/data-source feature flag default, grep all services:**

```bash
# Find critical health checks that assert data files
rg 'add_check\(.*critical\s*=\s*True' services/ shared/src/idea_shared/health/
```

Verify each is either (a) not dependent on the flag-gated file, or (b) wrapped in the matching `if use_<flag>:` gate — mirror the pattern already used for SqliteHealthCheck registrations.

## Volume reality: `/app/data` is EmptyDir, not hostPath

Despite what older CLAUDE.md sections suggest, the production Helm values mount `/app/data` and `/app/sqlite` as **EmptyDir** volumes (verified via `kubectl get deploy -o jsonpath=...volumes`). Implications:

- Each pod has its own isolated `/app/data` — services cannot see each other's files via this path.
- Data is ephemeral; a pod restart loses anything not persisted to GCS/InfluxDB/SQLite-on-GCS.
- Cross-service data exchange goes through GCS, InfluxDB, or SQLite DBs synced via GCS — never via shared filesystem.

The hostPath pattern mentioned in older docs applied to Skaffold/local development (OrbStack) only.

## CrashLoopBackOff Debugging Checklist

1. `kubectl describe pod <name>` — events: OOMKilled, probe failures, progress deadline, container count
2. `Containers: 1/2` suggests sidecar failure (e.g., GCS FUSE)
3. `kubectl logs <pod> --previous` — last instance's dying breath
4. `kubectl exec <pod> -- wget -qO- http://localhost:8080/health/detail` — which check is failing?
5. `cat /sys/fs/cgroup/cpu.stat` — is it CPU throttling, or event-loop starvation?
6. Verify feature flags are reaching the service (check provider, env vars, not just config files)
7. Check if service exits after completing work (missing continuous loop)
8. Verify Deployment progress deadline isn't shorter than startup time
