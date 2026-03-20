-- IDEA Helsinki SQLite Schema — Migration 001
--
-- This migration creates the initial schema for the SQLite storage backend.
-- Tables mirror the existing JSON file structure to enable gradual migration.
--
-- PRAGMAs (applied at connection time, not in migration):
--   journal_mode=WAL     — concurrent readers during writes
--   synchronous=NORMAL   — safe with WAL, better performance than FULL
--   foreign_keys=ON      — enforce referential integrity
--
-- SpatiaLite Upgrade Path
-- -----------------------
-- Current approach: geometries stored as GeoJSON TEXT with R-tree bounding box
-- index for spatial pre-filtering. This avoids requiring mod_spatialite in
-- containers.
--
-- When to upgrade to SpatiaLite:
--   - Segment count exceeds ~50K
--   - Spatial query performance becomes a bottleneck
--   - Need for accurate spatial operations (intersection, buffer, distance)
--
-- How to upgrade:
--   1. Add WKB geometry column:
--      ALTER TABLE segments ADD COLUMN geom BLOB;
--   2. Load extension:
--      SELECT load_extension('mod_spatialite');
--      SELECT InitSpatialMetadata(1);
--   3. Register geometry column:
--      SELECT AddGeometryColumn('segments', 'geom_spatial', 4326, 'LINESTRING', 'XY');
--   4. Populate from GeoJSON:
--      UPDATE segments SET geom_spatial = GeomFromGeoJSON(geometry);
--   5. Create spatial index:
--      SELECT CreateSpatialIndex('segments', 'geom_spatial');
--   6. The R-tree virtual table (segments_rtree) can then be dropped.

-- Current segment geometries (replaces segments_mapping.json)
CREATE TABLE IF NOT EXISTS segments (
    segment_id TEXT PRIMARY KEY,
    geometry TEXT NOT NULL,        -- GeoJSON geometry object
    geometry_hash TEXT NOT NULL,   -- SHA-256 hash for change detection
    srid INTEGER NOT NULL DEFAULT 4326,
    updated_at TEXT NOT NULL
);

-- Segment geometry change history (replaces master_segment_history.json)
CREATE TABLE IF NOT EXISTS segment_changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL,
    geometry TEXT NOT NULL,
    geometry_hash TEXT NOT NULL,
    change_type TEXT NOT NULL,     -- 'added', 'updated', 'removed'
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changelog_segment_recorded
    ON segment_changelog (segment_id, recorded_at DESC);

-- Removed segments archive (replaces archived_segment_history.json)
CREATE TABLE IF NOT EXISTS segment_archive (
    segment_id TEXT PRIMARY KEY,
    last_geometry TEXT NOT NULL,
    last_hash TEXT NOT NULL,
    date_added TEXT NOT NULL,
    date_archived TEXT NOT NULL
);

-- Traffic disturbance intersections (replaces traffic_disturbance_data.json)
CREATE TABLE IF NOT EXISTS disturbances (
    segment_id TEXT PRIMARY KEY,
    geometry TEXT NOT NULL,
    detailed_collisions TEXT NOT NULL DEFAULT '[]',  -- JSON array
    updated_at TEXT NOT NULL
);

-- Disk-backed segment profiles (new — replaces in-memory dict)
CREATE TABLE IF NOT EXISTS profiles (
    segment_id TEXT PRIMARY KEY,
    profile_data BLOB NOT NULL,
    computed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_expires
    ON profiles (expires_at);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- R-tree spatial index for bounding box pre-filtering
CREATE VIRTUAL TABLE IF NOT EXISTS segments_rtree USING rtree(
    id,       -- rowid alias (integer)
    min_x,    -- minimum longitude
    max_x,    -- maximum longitude
    min_y,    -- minimum latitude
    max_y     -- maximum latitude
);

-- Triggers to maintain R-tree on segment changes
CREATE TRIGGER IF NOT EXISTS segments_rtree_insert AFTER INSERT ON segments
BEGIN
    -- R-tree population handled by application code (bounding box extraction)
    -- Trigger placeholder for documentation; actual insert done in repository
    SELECT 1;
END;

CREATE TRIGGER IF NOT EXISTS segments_rtree_delete AFTER DELETE ON segments
BEGIN
    DELETE FROM segments_rtree WHERE id = CAST(OLD.segment_id AS INTEGER);
END;

-- Record this migration
INSERT OR IGNORE INTO schema_version (version, applied_at)
VALUES (1, datetime('now'));
