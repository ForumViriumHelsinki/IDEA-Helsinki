# Debugging IDEA-Helsinki

For Kubernetes-specific patterns (probes, GCS FUSE, CrashLoopBackOff, event-loop starvation), see `kubernetes-debugging.md`. This file covers the cross-cutting "where do I look first" decision tree and the Sentry integration that captures runtime errors across all three services.

## Where to look first

| Symptom | Start with |
|---------|-----------|
| Pod stuck `0/1`, restarting, or `CrashLoopBackOff` | `kubectl describe pod` + `/health/detail` (see `kubernetes-debugging.md`) |
| Recurring exceptions or regressions across releases | **Sentry** — every service ships errors here |
| Missing/stale data in TFDS_Dashboard | GCS bucket (`gs://idea-helsinki-data/data/*.json` and `*.db`); see `kubernetes-debugging.md` for the JSON-vs-SQLite split |
| Worker not validating segments | InfluxDB UI (`http://localhost:8086` locally) — verify FCD bucket has data for the queried period |
| Local dev failure during `skaffold dev` | Pod logs first; secrets-generation script second (`scripts/generate-secrets.sh`) |

When investigating a production incident, **always check Sentry alongside pod logs** — pod logs show the live cycle, Sentry shows the cumulative event distribution that pinpoints which error is dominant vs noise.

## Sentry — error tracking and release correlation

All three services initialize Sentry at startup via `idea_shared.observability.sentry.configure_sentry(service_name)`:

- **Orchestrator**: `services/orchestrator/src/main.py`
- **FCD Manager**: `services/fcd-manager/src/main.py`
- **Traffic Monitor**: `services/traffic-monitor/src/main.py`

Initialization is gated on `SENTRY_DSN` — when unset (typical for local dev), Sentry is silently skipped and a single info log is emitted (`SENTRY_DSN not set, running without Sentry error tracking`).

### Project location

| Field | Value |
|-------|-------|
| Org slug | `forum-virium-helsinki` |
| Project slug | `idea-helsinki` |
| Dashboard | https://forum-virium-helsinki.sentry.io/issues/?project=idea-helsinki |
| Release format | `idea-helsinki@<version>` (auto-detected from `/app/VERSION` written at Docker build time) |
| Service tag | `service:orchestrator` / `service:fcd-manager` / `service:traffic-monitor` |

### Querying Sentry from Claude Code

The Sentry MCP server is available — prefer it over the dashboard for triage flows:

```
mcp__sentry__search_issues(
  organizationSlug="forum-virium-helsinki",
  projectSlugOrId="idea-helsinki",
  query="is:unresolved lastSeen:-24h",
  sort="freq",        # by event frequency — fastest way to find dominant issues
  limit=20,
)
```

Useful filters:

- `service:orchestrator` (or `fcd-manager` / `traffic-monitor`) — narrow to one service
- `release:idea-helsinki@0.30.1` — confirm an issue is fixed in a new release
- `level:error firstSeen:-7d` — new issues only, not pre-existing noise
- `is:unresolved is:unassigned` — triage queue

For a single issue's stack trace and breadcrumbs:

```
mcp__sentry__get_sentry_resource(<issue-url-or-id>)
```

### Sample rate / cost knobs

Defaults (from `configure_sentry`):

| Env var | Default | Override range |
|---------|---------|---------------|
| `SENTRY_SAMPLE_RATE` | `1.0` (capture every error) | 0.0–1.0 |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` (10 % of transactions) | 0.0–1.0 |
| `SENTRY_PROFILES_SAMPLE_RATE` | `0.1` (10 % of profiles) | 0.0–1.0 |
| `SENTRY_RELEASE` | derived from `/app/VERSION` | any string |

If a noisy bug is burning quota, **fix the log severity at the source** rather than dropping the sample rate — see "Signal-to-noise hygiene" below.

### Breadcrumb redaction

`configure_sentry` installs a `before_breadcrumb` filter that strips InfluxDB query bodies and credentials from breadcrumbs. Don't disable this — flux queries leak segment IDs and timeframes into the breadcrumb log otherwise.

## Sentry triage workflow

When opening Sentry to investigate, work in this order:

1. **Sort by frequency** (`sort=freq`) — the top issue is almost always either a real high-impact bug *or* signal pollution. Distinguish before triaging anything else.
2. **For every issue >100 events/day, ask: should this be ERROR?** A `WARNING` log doesn't raise a Sentry issue; an `ERROR` does. "No FCD data available for this segment" is a normal outcome and should not be ERROR-level — fix the log call site, not the Sentry filter.
3. **Group by root cause, not by stack trace.** Multiple distinct Sentry issues (`InterfaceError in get_profile` / `TypeError NoneType bytes` / `Real-time update cycle error`) may all stem from one bug (shared SQLite connection across threads). Fix the root and the issues collapse together.
4. **Cross-reference with pod restarts.** A spike in error count at exactly the time of a pod restart usually means startup-time error, not a runtime regression. Use `kubectl get pod -o wide` to compare ages.
5. **Resolve in next release.** When fixing an issue, mark it resolved with the release version (`mcp__sentry__update_issue` → `status="resolvedInNextRelease"`). Sentry will reopen if it recurs in a later release — that's the regression alarm.

## Signal-to-noise hygiene

Sentry quota and triage capacity are scarce. Practices that protect them:

- **`logger.warning()` for expected-but-noteworthy outcomes** (no data for a segment, retry succeeded, cache miss). These appear in pod logs but do not become Sentry issues.
- **`logger.error()` only for things a human should investigate** (DB write failed after retries, schema invariant violated, external API returned 500).
- **Catch-and-log with context** — bare `logger.error("failed")` produces useless Sentry issues. Always include the operation name, the input that triggered the failure, and the underlying exception (`logger.error("save_profile failed for segment_id=%s", sid, exc_info=True)`).
- **Don't log inside tight loops** — one ERROR per validation cycle becomes 1000+ events/hour. Aggregate at the cycle boundary instead.

## Cross-references

- `kubernetes-debugging.md` — probes, GCS FUSE, EmptyDir reality, HealthServer threading
- `testing.md` — how to reproduce locally before debugging in prod
- `shared/src/idea_shared/observability/sentry.py` — Sentry SDK initialization
- `shared/src/idea_shared/resilience/README.md` — circuit breaker and retry semantics that gate when an exception reaches Sentry
