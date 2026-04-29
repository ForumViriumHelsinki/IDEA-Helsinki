"""SQLite backend for IDEA Helsinki repositories.

Implements SegmentRepository, DisturbanceRepository, and ProfileRepository
using SQLite. Designed for single-writer usage with WAL mode for concurrent
reads. Connection is shared across repositories via create_sqlite_repositories().
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from idea_shared.data.repositories import (
    DisturbanceRepository,
    ProfileRepository,
    SegmentRepository,
)

logger = logging.getLogger(__name__)

_CHANGELOG_RETENTION_LIMIT = 50


class _SqliteConnectionManager:
    """Manages SQLite connection lifecycle and schema migration."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._local = threading.local()

    @property
    def connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=True)
            self._local.conn.row_factory = sqlite3.Row
            self._apply_pragmas(self._local.conn)
        return self._local.conn

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")

    def ensure_schema(self) -> None:
        """Apply schema migrations idempotently."""
        conn = self.connection
        # Check if schema_version table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        has_version_table = cursor.fetchone() is not None

        if has_version_table:
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row and row[0] is not None else 0
        else:
            current_version = 0

        if current_version < 1:
            migration_sql = (
                importlib.resources.files("idea_shared.data.migrations")
                .joinpath("001_initial.sql")
                .read_text(encoding="utf-8")
            )
            conn.executescript(migration_sql)
            logger.info("Applied schema migration 001_initial")

    def reconnect(self) -> None:
        """Close and reopen the connection to pick up a replaced database file.

        Also removes stale WAL/SHM journal files left by the previous
        connection, which would otherwise cause SQLite to replay old
        transactions on top of the newly downloaded database.
        """
        self.close()
        # Remove WAL/SHM files so the new connection reads the replaced file cleanly
        if self._db_path != ":memory:":
            for suffix in ("-wal", "-shm"):
                journal = Path(self._db_path + suffix)
                journal.unlink(missing_ok=True)
        logger.info("SQLite connection reset; will reconnect on next access.")

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            del self._local.conn


def _extract_bounding_box(
    geometry: dict,
) -> tuple[float, float, float, float] | None:
    """Extract bounding box (min_x, max_x, min_y, max_y) from GeoJSON geometry."""
    coords = geometry.get("coordinates")
    if not coords:
        return None
    # Flatten coordinates (handles LineString [[x,y], ...])
    flat = []
    if isinstance(coords[0], (list, tuple)) and isinstance(coords[0][0], (int, float)):
        # LineString: [[x, y], ...]
        flat = coords
    elif isinstance(coords[0], (int, float)):
        # Point: [x, y]
        flat = [coords]
    else:
        # MultiLineString or Polygon: [[[x, y], ...], ...]
        for ring in coords:
            if isinstance(ring[0], (list, tuple)):
                flat.extend(ring)
            else:
                flat.append(ring)

    if not flat:
        return None

    xs = [p[0] for p in flat]
    ys = [p[1] for p in flat]
    return (min(xs), max(xs), min(ys), max(ys))


class SqliteSegmentRepository(SegmentRepository):
    """SQLite-backed segment repository.

    Stores segments, changelog, and archive in SQLite tables with R-tree
    bounding box index for spatial pre-filtering.
    """

    def __init__(self, conn_manager: _SqliteConnectionManager):
        self._cm = conn_manager

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._cm.connection

    def reconnect(self) -> None:
        """Reset the database connection to pick up a replaced file on disk."""
        self._cm.reconnect()

    def get_segments(self) -> dict:
        """Read all segments, reconstructing the JSON dict format."""
        cursor = self._conn.execute("SELECT segment_id, geometry FROM segments")
        rows = cursor.fetchall()
        if not rows:
            return {}
        segments = {}
        for row in rows:
            segments[row["segment_id"]] = {"geometry": json.loads(row["geometry"])}
        return {"segmentId": segments}

    def save_segments(self, segments: dict) -> bool:
        """Save segments with R-tree bounding box maintenance."""
        segment_ids = segments.get("segmentId")
        if not isinstance(segment_ids, dict):
            logger.error("Segment data missing 'segmentId' dict, cannot save.")
            return False

        now = datetime.now(UTC).isoformat()
        try:
            with self._conn:
                self._conn.execute("DELETE FROM segments")
                self._conn.execute("DELETE FROM segments_rtree")
                for seg_id, seg_data in segment_ids.items():
                    geometry = seg_data.get("geometry", {})
                    geometry_json = json.dumps(geometry)
                    geometry_hash = hashlib.sha256(geometry_json.encode()).hexdigest()
                    self._conn.execute(
                        "INSERT INTO segments (segment_id, geometry, geometry_hash, updated_at) "
                        "VALUES (?, ?, ?, ?)",
                        (seg_id, geometry_json, geometry_hash, now),
                    )
                    bbox = _extract_bounding_box(geometry)
                    if bbox:
                        # Use SHA-256 hash of segment_id for a stable, collision-resistant
                        # integer key. Python's built-in hash() is PYTHONHASHSEED-randomized
                        # and can cause PRIMARY KEY collisions across runs.
                        rtree_id = (
                            int.from_bytes(
                                hashlib.sha256(seg_id.encode()).digest()[:8], "big"
                            )
                            & 0x7FFFFFFFFFFFFFFF
                        )
                        self._conn.execute(
                            "INSERT INTO segments_rtree (id, min_x, max_x, min_y, max_y) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (rtree_id, *bbox),
                        )
            logger.info(f"Saved {len(segment_ids)} segments to SQLite.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to save segments: {e}")
            return False

    def get_changelog(self) -> dict:
        """Read changelog, reconstructing the JSON dict format."""
        cursor = self._conn.execute(
            "SELECT segment_id, geometry, geometry_hash, change_type, recorded_at "
            "FROM segment_changelog ORDER BY recorded_at DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            return {}

        changelog: dict = {}
        for row in rows:
            seg_id = row["segment_id"]
            entry = {
                "geometry": json.loads(row["geometry"]),
                "geometry_hash": row["geometry_hash"],
                "change_type": row["change_type"],
                "recorded_at": row["recorded_at"],
            }
            if seg_id not in changelog:
                changelog[seg_id] = {
                    "current_geometry": entry["geometry"],
                    "current_hash": entry["geometry_hash"],
                    "date_added": entry["recorded_at"],
                    "history": [],
                }
            else:
                changelog[seg_id]["history"].append(entry)
        return changelog

    def save_changelog(self, changelog: dict) -> None:
        """Save changelog with full-replace semantics per segment.

        Matches the JSON backend's file-overwrite behaviour: all existing rows for
        each segment in the dict are deleted and the full history (current + past
        entries) is reinserted. This prevents duplicate rows when the caller
        round-trips through get_changelog() → process_segment_changelog() →
        save_changelog(), where history entries are already stored in the DB.
        """
        now = datetime.now(UTC).isoformat()
        with self._conn:
            for seg_id, entry in changelog.items():
                # Full-replace: remove all existing rows for this segment so that
                # history entries from a previous save are not duplicated.
                self._conn.execute(
                    "DELETE FROM segment_changelog WHERE segment_id = ?", (seg_id,)
                )
                # Insert the current geometry as the most-recent entry.
                geometry = entry.get("current_geometry", {})
                geometry_json = json.dumps(geometry)
                geometry_hash = entry.get("current_hash", "")
                self._conn.execute(
                    "INSERT INTO segment_changelog "
                    "(segment_id, geometry, geometry_hash, change_type, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (seg_id, geometry_json, geometry_hash, "updated", now),
                )
                # Reinsert historical entries (older timestamps preserved).
                for hist in entry.get("history", []):
                    self._conn.execute(
                        "INSERT INTO segment_changelog "
                        "(segment_id, geometry, geometry_hash, change_type, recorded_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            seg_id,
                            json.dumps(hist.get("geometry", {})),
                            hist.get("geometry_hash", ""),
                            hist.get("change_type", "updated"),
                            hist.get("recorded_at", now),
                        ),
                    )
                # Enforce retention limit per segment.
                self._conn.execute(
                    "DELETE FROM segment_changelog WHERE id NOT IN "
                    "(SELECT id FROM segment_changelog WHERE segment_id = ? "
                    "ORDER BY recorded_at DESC LIMIT ?)",
                    (seg_id, _CHANGELOG_RETENTION_LIMIT),
                )
        logger.info("Segment changelog saved to SQLite.")

    def get_archive(self) -> dict:
        """Read archived segments."""
        cursor = self._conn.execute(
            "SELECT segment_id, last_geometry, last_hash, date_added, date_archived "
            "FROM segment_archive"
        )
        rows = cursor.fetchall()
        if not rows:
            return {}
        archive = {}
        for row in rows:
            archive[row["segment_id"]] = {
                "last_geometry": json.loads(row["last_geometry"]),
                "last_hash": row["last_hash"],
                "date_added": row["date_added"],
                "date_archived": row["date_archived"],
            }
        return archive

    def save_archive(self, archive: dict) -> None:
        """Save archived segments with full-replace semantics."""
        with self._conn:
            self._conn.execute("DELETE FROM segment_archive")
            for seg_id, entry in archive.items():
                self._conn.execute(
                    "INSERT INTO segment_archive "
                    "(segment_id, last_geometry, last_hash, date_added, date_archived) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        seg_id,
                        json.dumps(entry.get("last_geometry", {})),
                        entry.get("last_hash", ""),
                        entry.get("date_added", ""),
                        entry.get("date_archived", ""),
                    ),
                )
        logger.info("Segment archive saved to SQLite.")


class SqliteDisturbanceRepository(DisturbanceRepository):
    """SQLite-backed disturbance repository.

    Uses full-replace semantics (DELETE all + INSERT) on save, matching
    the JSON backend's behavior of overwriting the entire file.
    """

    def __init__(self, conn_manager: _SqliteConnectionManager):
        self._cm = conn_manager

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._cm.connection

    def get_disturbances(self) -> dict:
        """Read disturbances, reconstructing the JSON dict format."""
        cursor = self._conn.execute(
            "SELECT segment_id, geometry, detailed_collisions FROM disturbances"
        )
        rows = cursor.fetchall()
        if not rows:
            return {}
        disturbances = {}
        for row in rows:
            disturbances[row["segment_id"]] = {
                "geometry": json.loads(row["geometry"]),
                "detailedCollisions": json.loads(row["detailed_collisions"]),
            }
        return {"segmentId": disturbances}

    def save_disturbances(self, data: dict) -> bool:
        """Save disturbances with full-replace semantics."""
        segment_ids = data.get("segmentId")
        if not isinstance(segment_ids, dict):
            logger.error("Disturbance data missing 'segmentId' dict, cannot save.")
            return False

        now = datetime.now(UTC).isoformat()
        try:
            with self._conn:
                self._conn.execute("DELETE FROM disturbances")
                for seg_id, entry in segment_ids.items():
                    self._conn.execute(
                        "INSERT INTO disturbances "
                        "(segment_id, geometry, detailed_collisions, updated_at) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            seg_id,
                            json.dumps(entry.get("geometry", {}), ensure_ascii=False),
                            json.dumps(
                                entry.get("detailedCollisions", []), ensure_ascii=False
                            ),
                            now,
                        ),
                    )
            logger.info(f"Saved {len(segment_ids)} disturbance records to SQLite.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to save disturbances: {e}")
            return False


class SqliteProfileRepository(ProfileRepository):
    """SQLite-backed profile repository.

    Stores serialized profile data as BLOBs with UPSERT semantics
    and expiration-based cleanup.
    """

    def __init__(self, conn_manager: _SqliteConnectionManager):
        self._cm = conn_manager

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._cm.connection

    def get_profile(self, segment_id: str) -> bytes | None:
        """Retrieve a serialized profile by segment ID."""
        cursor = self._conn.execute(
            "SELECT profile_data FROM profiles WHERE segment_id = ?",
            (str(segment_id),),
        )
        row = cursor.fetchone()
        if row and row["profile_data"] is not None:
            return bytes(row["profile_data"])
        return None

    def save_profile(
        self,
        segment_id: str,
        profile_data: bytes,
        computed_at: str,
        expires_at: str,
    ) -> None:
        """Insert or replace a serialized profile for a segment."""
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO profiles "
                "(segment_id, profile_data, computed_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (str(segment_id), profile_data, computed_at, expires_at),
            )

    def delete_profile(self, segment_id: str) -> None:
        """Delete a profile by segment ID."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM profiles WHERE segment_id = ?",
                (str(segment_id),),
            )

    def get_all_profile_ids(self) -> list[str]:
        """Return all stored segment IDs, sorted alphabetically."""
        cursor = self._conn.execute(
            "SELECT segment_id FROM profiles ORDER BY segment_id"
        )
        return [row["segment_id"] for row in cursor.fetchall()]

    def delete_expired_profiles(self) -> int:
        """Delete profiles past their expiration date and return the count removed."""
        now = datetime.now(UTC).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM profiles WHERE expires_at < ?", (now,)
            )
            deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Deleted {deleted} expired profiles.")
        return deleted


def create_sqlite_repositories(
    db_path: str | Path,
) -> tuple[
    SqliteSegmentRepository,
    SqliteDisturbanceRepository,
    SqliteProfileRepository,
]:
    """Factory creating all repositories sharing one SQLite connection.

    Args:
        db_path: Path to SQLite database file, or ":memory:" for testing.

    Returns:
        Tuple of (segment_repo, disturbance_repo, profile_repo).

    """
    conn_manager = _SqliteConnectionManager(db_path)
    conn_manager.ensure_schema()
    return (
        SqliteSegmentRepository(conn_manager),
        SqliteDisturbanceRepository(conn_manager),
        SqliteProfileRepository(conn_manager),
    )
