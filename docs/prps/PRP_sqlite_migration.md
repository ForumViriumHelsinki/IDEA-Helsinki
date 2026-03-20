# Product Requirement Prompt: SQLite Migration

**Related Documents:**
- PRD: [`docs/prds/PRD_sqlite_migration.md`](../prds/PRD_sqlite_migration.md)
- ADR: [`docs/adrs/ADR_001_sqlite_over_alternatives.md`](../adrs/ADR_001_sqlite_over_alternatives.md)

## Overview

Implementation checklist for migrating IDEA Helsinki from GCS FUSE JSON files to SQLite per service + GCS Object API. Five phases, each independently testable with `just test`.

---

## Phase 1: Data Access Layer — COMPLETE

Decoupled business logic from storage backends via abstract repository interfaces.

### Files Created
- [x] `shared/src/idea_shared/data/__init__.py` — Package init, exports `SegmentRepository`, `DisturbanceRepository`
- [x] `shared/src/idea_shared/data/repositories.py` — Abstract `SegmentRepository` (segments, changelog, archive) and `DisturbanceRepository` ABCs
- [x] `shared/src/idea_shared/data/json_backend.py` — `JsonSegmentRepository`, `JsonDisturbanceRepository` wrapping existing file I/O
- [x] `shared/tests/unit/data/__init__.py`
- [x] `shared/tests/unit/data/test_json_backend.py` — Repository contract tests
- [x] `shared/tests/unit/data/test_changelog_processing.py` — Pure changelog logic tests

### Files Modified
- [x] `shared/src/idea_shared/lib/FcdUtils.py`
  - Added `ChangelogResult` dataclass
  - Extracted `extract_fresh_segments()` — segment_id → geometry mapping
  - Extracted `process_segment_changelog()` — pure function, no file I/O
  - Added `update_segment_changelog_from_repo()` — repository-based wrapper
- [x] `shared/src/idea_shared/classes/IntersectionDetector.py`
  - Extracted `_parse_segment_data()` from `load_fcd_segment_data()`
  - Added `load_segments_from_repo()` — loads segments via `SegmentRepository`
  - Added `save_disturbances_to_repo()` — saves via `DisturbanceRepository`
  - Used `TYPE_CHECKING` imports to avoid circular dependencies
- [x] `shared/src/idea_shared/classes/IdeaHelsinkiManager.py`
  - Added `disturbance_repository: DisturbanceRepository | None` parameter
  - `_load_latest_disturbance_data()` uses repository when available, falls back to file
  - Used `TYPE_CHECKING` imports
- [x] `services/fcd-manager/src/main.py` — Wired `JsonSegmentRepository`, passes to `run()`
- [x] `services/traffic-monitor/src/main.py` — Wired `JsonSegmentRepository` + `JsonDisturbanceRepository`
- [x] `services/orchestrator/src/main.py` — Wired `DisturbanceRepository` via `IdeaHelsinkiManager`

### Key Design Decisions
- **Deep copy in `process_segment_changelog()`**: Prevents mutation of caller's data when nested dicts contain shared references
- **`_parse_segment_data()` extraction**: Shared parsing logic reused by both file-based and repository-based loading paths
- **`TYPE_CHECKING` imports**: Avoids circular imports between `data/` and `classes/` packages at runtime
- **Optional repository parameters**: Services fall back to direct file I/O when repository is `None`, enabling gradual adoption

---

## Phase 2: SQLite Implementations — COMPLETE

Implemented SQLite backends for all repository interfaces plus a new `ProfileRepository` ABC.

### Feature Flag
- [x] Add `USE_SQLITE_STORAGE` to `shared/src/idea_shared/feature_flags/flags.py` (`FeatureFlag` enum and `FlagDefaults`)

### Schema Migration
- [x] Create `shared/src/idea_shared/data/migrations/001_initial.sql`
  - `segments` table (segment_id PK, geometry, geometry_hash, srid, updated_at)
  - `segment_changelog` table (autoincrement PK, segment_id, geometry, geometry_hash, change_type, recorded_at)
  - `segment_archive` table (segment_id PK, last_geometry, last_hash, date_added, date_archived)
  - `disturbances` table (segment_id PK, geometry, detailed_collisions JSON, updated_at)
  - `profiles` table (segment_id PK, profile_data BLOB, computed_at, expires_at)
  - `schema_version` table for migration tracking
  - `segments_rtree` R-tree virtual table for bounding box spatial pre-filtering
  - SpatiaLite upgrade path documented in SQL comments

### Repository Implementations
- [x] Create `shared/src/idea_shared/data/sqlite_backend.py`
- [x] Implement `SqliteSegmentRepository(SegmentRepository)`
  - Schema creation from migration file via `importlib.resources`
  - CRUD for segments, changelog, archive
  - R-tree bounding box maintenance on segment save
  - Retention: max 50 changelog entries per segment
  - `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;`
- [x] Implement `SqliteDisturbanceRepository(DisturbanceRepository)`
  - Full-replace semantics (DELETE all + INSERT)
  - JSON serialization for `detailed_collisions`
- [x] Add `ProfileRepository` ABC to `shared/src/idea_shared/data/repositories.py`
- [x] Implement `SqliteProfileRepository(ProfileRepository)`
  - BLOB storage with UPSERT semantics
  - Expiration-based cleanup (`delete_expired_profiles()`)
- [x] Create `shared/src/idea_shared/data/profile_serialization.py`
  - `serialize_profile()` / `deserialize_profile()` for DataFrame ↔ Parquet bytes
- [x] `create_sqlite_repositories(db_path)` factory for shared connection

### Profile Integration
- [ ] Modify `shared/src/idea_shared/classes/IdeaHelsinkiRoadSegment.py` (deferred to Phase 4 — service wiring)
  - `segment_profile` property: lazy-load from `ProfileRepository` when configured
  - Fall back to in-memory dict when repository is `None`

### Tests
- [x] Unit tests using `:memory:` SQLite for all three repositories
- [x] Test retention logic (verify max 50 changelog entries per segment)
- [x] Test schema migration idempotency
- [x] Test Parquet round-trip serialization
- [x] `just test` passes

---

## Phase 3: GCS Sync Layer — PENDING

Replace GCS FUSE with Object API for cross-service communication.

### Dependencies
- [ ] Add `google-cloud-storage` to `shared/pyproject.toml`

### Implementation
- [ ] Create `shared/src/idea_shared/data/gcs_sync.py`
- [ ] Implement `GCSSync` class:
  - `__init__(bucket_name, prefix, credentials)` — initialize GCS client
  - `upload(local_path, remote_key)` — upload file to GCS bucket
  - `download_if_changed(remote_key, local_path)` — download only if ETag differs from cached value
  - ETag caching: store last-seen ETag per remote_key to skip redundant downloads
  - Error handling: retry with exponential backoff on transient GCS errors

### Tests
- [ ] Unit tests with mocked GCS client
- [ ] Integration tests against `fake-gcs-server` Docker container
- [ ] Test ETag caching (verify no download when unchanged)
- [ ] Test error handling (transient failures, missing objects)
- [ ] `just test` passes

---

## Phase 4: Service Wiring — PENDING

Wire SQLite + GCS sync into all services and validate.

### JSON Export
- [ ] Create `shared/src/idea_shared/data/json_export.py`
  - `export_segments_json(repo: SegmentRepository, path: Path)` — for TFDS_Dashboard
  - `export_disturbances_json(repo: DisturbanceRepository, path: Path)` — for TFDS_Dashboard

### Service Changes
- [ ] Wire `SqliteSegmentRepository` + `GCSSync.upload()` in fcd-manager
- [ ] Wire `SqliteDisturbanceRepository` + `GCSSync.upload()` in traffic-monitor
- [ ] Wire `SqliteProfileRepository` + `GCSSync.download_if_changed()` in orchestrator
- [ ] Traffic-monitor: `GCSSync.download_if_changed()` for segments data
- [ ] Orchestrator: `GCSSync.download_if_changed()` for segments + disturbances

### Health Checks
- [ ] Update health checks to query SQLite (table existence, row count) instead of JSON file existence

### Infrastructure
- [ ] Remove GCS FUSE volume mounts from IDEA service k8s deployments
- [ ] Add emptyDir volumes for SQLite files in k8s deployments

### Validation
- [ ] Dual-write mode: both JSON and SQLite backends active simultaneously
- [ ] Compare JSON export output vs direct JSON backend output
- [ ] Verify all services function with `USE_SQLITE_STORAGE=true`
- [ ] `just test` passes

---

## Phase 5: Cleanup — PENDING

Remove JSON-only code paths and GCS FUSE remnants.

### Files to Remove
- [ ] `shared/src/idea_shared/data/json_backend.py` (keep `json_export.py`)
- [ ] `shared/src/idea_shared/threading/file_locks.py` (GCS FUSE retry/lock utilities)
- [ ] `shared/src/idea_shared/threading/SegmentMappingFileManager` (if exists)

### Files to Modify
- [ ] `shared/src/idea_shared/feature_flags/flags.py` — Remove `USE_SQLITE_STORAGE` (SQLite is sole backend)
- [ ] All three service `main.py` files — Remove JSON fallback code paths
- [ ] `shared/src/idea_shared/data/__init__.py` — Remove JSON backend exports
- [ ] Remove GCS FUSE PVC from IDEA service k8s manifests (if not done in Phase 4)

### Documentation
- [ ] Update `CLAUDE.md` — Remove GCS FUSE references, add SQLite architecture
- [ ] Update `docs/data_models.md` — Reflect SQLite schema
- [ ] Update `.claude/rules/kubernetes-debugging.md` — Remove GCS FUSE debugging section

### Verification
- [ ] All JSON backend references removed from codebase
- [ ] No GCS FUSE mounts in IDEA k8s manifests
- [ ] `just test` passes
- [ ] `ruff check` passes
