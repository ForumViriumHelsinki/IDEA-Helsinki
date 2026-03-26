# ADR-001: Use SQLite per Service with GCS Object API for Cross-Service Data Sharing

**Date:** 2026-03-19
**Status:** Accepted

## Context

IDEA Helsinki's three microservices (fcd-manager, traffic-monitor, orchestrator) share persistent state via JSON files on a GCS FUSE-mounted volume. This architecture has caused multiple production issues:

- **ESTALE errors** ([#147](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/147)): GCS FUSE metadata cache causes stale file handles when one pod writes and another reads.
- **Data corruption** ([#168](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/168)): No file locking on GCS FUSE means pod termination during writes produces truncated JSON.
- **Unbounded growth** ([#240](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/240)): Segment history files grow monotonically with no retention policy.
- **Excessive memory** ([#242](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/242)): Orchestrator holds all profiles in memory (~4 GB).
- **No query capability** ([#248](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/248)): JSON files cannot be queried; spatial joins are recomputed every cycle.

Key constraints:
- Total data volume is ~150 MB across all JSON files
- Single-writer discipline is already enforced (one service owns writes to each file)
- TFDS_Dashboard consumes the JSON files and cannot be rewritten immediately
- Infrastructure cost sensitivity (Forum Virium Helsinki is a public-sector organization)
- GKE Autopilot environment with limited PV options

## Decision

**Use SQLite per service for local storage, GCS Object API for cross-service data sharing, and JSON export for TFDS_Dashboard backwards compatibility.**

Each service:
1. Maintains its own SQLite database on local (emptyDir) storage
2. Uploads changed data to a GCS bucket via the Object API (not FUSE)
3. Downloads data from GCS that other services produce
4. Optionally exports JSON for consumers that require it

## Alternatives Considered

### 1. PostgreSQL/PostGIS via Cloud SQL

**Verdict: Rejected — overkill**

- Adds managed database dependency (Cloud SQL) with monthly cost ($7-50/mo minimum)
- Requires connection pooling, migration tooling, and operational overhead
- Data volume (~150 MB) doesn't justify a server-based database
- Single-writer workload doesn't benefit from PostgreSQL's concurrency model
- Would solve all technical issues but violates the principle of minimal infrastructure

### 2. SQLite on NFS-backed ReadWriteMany PV (Filestore)

**Verdict: Rejected — cost and correctness**

- Google Filestore minimum instance is 1 TiB at ~$204/month — 6,700x the actual data volume
- NFS does not reliably support SQLite WAL mode (shared memory segment)
- Introduces shared filesystem semantics that SQLite was not designed for
- Single point of failure for all three services

### 3. Keep JSON + Replace FUSE with GCS Object API

**Verdict: Rejected — insufficient**

- Solves #147 (ESTALE) by eliminating FUSE
- Does NOT solve #240 (unbounded history — JSON has no retention mechanism)
- Does NOT solve #242 (memory — JSON must be fully loaded)
- Does NOT solve #248 (no query capability)
- Still requires full-file reads/writes with no transactional guarantees

### 4. SQLite on GCS FUSE Volume

**Verdict: Rejected — won't work**

- SQLite requires file locking (`fcntl` / `flock`) which GCS FUSE does not support
- WAL mode requires shared memory (`-shm` file) which cannot be shared across FUSE
- Would result in database corruption under concurrent access
- Google's own documentation warns against using databases on GCS FUSE

## Consequences

### Positive

- **ACID transactions**: All writes are atomic; no more truncated JSON on pod kill
- **Bounded history**: `DELETE FROM segment_changelog WHERE ...` with retention policy
- **Disk-backed profiles**: SQLite stores profiles on disk; orchestrator loads only what's needed
- **Spatial readiness**: Schema design accommodates future SpatiaLite extension
- **Zero infrastructure cost**: SQLite is a library; GCS Object API uses existing bucket
- **Standard library**: `sqlite3` ships with Python; no new runtime dependency for Phase 2
- **Testability**: `:memory:` SQLite databases enable fast, isolated unit tests

### Negative

- **Single-writer limitation**: SQLite allows only one writer at a time. Acceptable because single-writer discipline is already enforced.
- **GCS sync latency**: Object API adds latency vs. FUSE's (cached) filesystem semantics. Mitigated by ETag-based caching — only download when changed.
- **Migration complexity**: Five-phase migration requires careful sequencing and dual-write validation.
- **TFDS_Dashboard dependency**: JSON export must be maintained until Dashboard is updated.
- **Pod restart data loss**: emptyDir storage is ephemeral. Services must re-download from GCS on startup. This is acceptable because GCS is the durable store.

## SpatiaLite Evaluation (Issue #303)

### Current Approach

Geometries are stored as GeoJSON TEXT columns with a built-in SQLite R-tree virtual table (`segments_rtree`) for bounding box pre-filtering. This provides spatial query capability without requiring the `mod_spatialite` extension in containers.

The R-tree index stores bounding boxes (min_x, max_x, min_y, max_y) extracted from GeoJSON coordinates at write time. Queries can use the R-tree for fast rectangular area filtering before performing precise geometry operations in application code.

### When to Upgrade to SpatiaLite

Consider loading `mod_spatialite` when:
- Segment count exceeds ~50K and bounding box pre-filtering is insufficient
- Spatial query performance becomes a bottleneck (e.g., intersection detection taking >1s)
- Need for accurate spatial operations (ST_Intersects, ST_Buffer, ST_Distance) that cannot be approximated by bounding box checks

### How to Upgrade

The migration SQL (`001_initial.sql`) documents the upgrade path:
1. Add WKB geometry column to `segments` table
2. Load `mod_spatialite` extension and initialize spatial metadata
3. Register geometry column with `AddGeometryColumn()`
4. Populate from existing GeoJSON with `GeomFromGeoJSON()`
5. Create SpatiaLite spatial index with `CreateSpatialIndex()`
6. Drop the R-tree virtual table (`segments_rtree`) once SpatiaLite indexes are in place

### Container Impact

Adding SpatiaLite requires `libspatialite` in the container image (~15 MB). This would be added to the Dockerfile only when the upgrade is justified by segment volume or query complexity.
