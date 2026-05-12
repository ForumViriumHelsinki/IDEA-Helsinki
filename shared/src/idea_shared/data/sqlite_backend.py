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


class SqliteIntegrityError(sqlite3.DatabaseError):
    """Raised when ``PRAGMA quick_check`` reports a corrupt database.

    Distinct from the bare ``sqlite3.DatabaseError`` that SQLite raises on
    queries against a malformed file so callers can recover (delete the
    local file, force a re-download from upstream) without catching every
    transient DB error. See issue #459.
    """

    def __init__(self, db_path: str, detail: str) -> None:
        super().__init__(f"SQLite integrity check failed for {db_path}: {detail}")
        self.db_path = db_path
        self.detail = detail


# Tables created by migration 001. ``ensure_schema`` cross-checks this set
# against ``sqlite_master`` so it can detect files whose ``schema_version``
# claims v1 but whose tables have gone missing — e.g. a partial GCS download
# or a stale snapshot uploaded by an upstream service in an incomplete state
# (see https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/461).
_MIGRATION_001_TABLES: frozenset[str] = frozenset(
    {
        "segments",
        "segment_changelog",
        "segment_archive",
        "disturbances",
        "profiles",
        "schema_version",
        "segments_rtree",
    }
)


class _SqliteConnectionManager:
    """Manages SQLite connection lifecycle and schema migration.

    Each thread owns its own SQLite connection (via ``threading.local``) so
    operations dispatched through ``asyncio.to_thread`` do not violate
    ``check_same_thread`` and do not contend on a shared handle. A monotonic
    *generation* counter coordinates ``reconnect()`` across threads: after the
    underlying database file is replaced (e.g. downloaded from GCS), the
    counter is bumped and every thread closes-and-reopens its cached
    connection on next access.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._local = threading.local()
        self._generation = 0

    @property
    def connection(self) -> sqlite3.Connection:
        local_gen = getattr(self._local, "gen", None)
        if local_gen != self._generation:
            # Generation advanced (or first access in this thread): close any
            # stale connection in this thread and reopen against the current
            # database file.
            self._close_local()
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=True)
            self._local.conn.row_factory = sqlite3.Row
            self._apply_pragmas(self._local.conn)
            # Validate schema on every fresh handle. Worker threads that
            # reconnect after the manager bumped the generation would
            # otherwise race the reconnecting thread's ``ensure_schema`` call
            # and crash with ``no such table`` (issue #461). Doing the check
            # here serialises through SQLite's own locking: ``CREATE TABLE IF
            # NOT EXISTS`` is a no-op once another thread has committed the
            # migration, so concurrent first-access from multiple threads is
            # safe.
            self._validate_and_repair_schema(self._local.conn)
            self._local.gen = self._generation
        return self._local.conn

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")

    def _validate_and_repair_schema(self, conn: sqlite3.Connection) -> None:
        """Verify migration 001 tables exist on *conn*; re-apply migration if not.

        Operates on an explicit connection rather than ``self.connection`` so
        it can be called from inside the connection property's refresh block
        without recursion. Idempotent: when the schema is already intact
        this is two cheap ``SELECT``s.
        """
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        if "schema_version" in existing_tables:
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row and row[0] is not None else 0
        else:
            current_version = 0

        missing_v1_tables = _MIGRATION_001_TABLES - existing_tables
        needs_v1 = current_version < 1 or bool(missing_v1_tables)

        if not needs_v1:
            return

        if missing_v1_tables and current_version >= 1:
            # File on disk reports an up-to-date schema_version but is
            # missing tables the migration was meant to create. Re-apply
            # the migration to self-heal rather than crashing on the
            # next query (issue #461).
            logger.warning(
                "schema_version reports v%d but tables are missing: %s; "
                "re-applying migration 001 to restore schema.",
                current_version,
                sorted(missing_v1_tables),
            )
        migration_sql = (
            importlib.resources.files("idea_shared.data.migrations")
            .joinpath("001_initial.sql")
            .read_text(encoding="utf-8")
        )
        conn.executescript(migration_sql)
        logger.info("Applied schema migration 001_initial")

    def ensure_schema(self) -> None:
        """Apply schema migrations idempotently.

        Per-connection validation already happens inside the ``connection``
        property's refresh block, so for already-open handles this is a
        cheap no-op. The method is retained for explicit-intent call sites
        (e.g. ``create_sqlite_repositories``) and for backward compatibility
        with tests that call it directly.
        """
        self._validate_and_repair_schema(self.connection)

    def check_integrity(self) -> None:
        """Run ``PRAGMA quick_check`` against the current connection.

        Detects the structural corruption pattern from issue #459
        (``database disk image is malformed``) cheaply enough to call on
        every fresh download. ``quick_check`` is the same logic as
        ``integrity_check`` minus the costly index/UNIQUE consistency
        verification — it still detects the page-level damage that the
        Sentry stack trace points at.

        Raises:
            SqliteIntegrityError: when the database is malformed.

        """
        try:
            cursor = self.connection.execute("PRAGMA quick_check")
            rows = cursor.fetchall()
        except sqlite3.DatabaseError as exc:
            # The quick_check itself failed to execute (e.g. the file is so
            # damaged we cannot even parse the header). Surface this as
            # integrity failure so callers can recover.
            raise SqliteIntegrityError(self._db_path, str(exc)) from exc

        # SQLite reports a single "ok" row on success; anything else is a
        # list of corruption details.
        if not rows or any(row[0] != "ok" for row in rows):
            detail = "; ".join(str(row[0]) for row in rows) or "no rows returned"
            raise SqliteIntegrityError(self._db_path, detail)

    def discard_file(self) -> None:
        """Delete the underlying database file and its journals.

        Used by callers that detected the local file is unrecoverable
        (e.g. ``check_integrity`` raised ``SqliteIntegrityError``) and want
        the next download attempt to pull a fresh copy from upstream.
        Calls ``close`` first so the unlinks don't race with an open
        write handle.
        """
        self._close_local()
        self._generation += 1
        if self._db_path == ":memory:":
            return
        for suffix in ("", "-wal", "-shm", "-journal"):
            stale = Path(self._db_path + suffix)
            stale.unlink(missing_ok=True)
        logger.warning(
            "Discarded local SQLite file %s (and journals); next refresh "
            "must re-download from upstream.",
            self._db_path,
        )

    def reconnect(self) -> None:
        """Force every thread to reopen its connection on next access.

        After the database file on disk has been replaced (e.g. a fresh
        download from GCS), this method closes the calling thread's
        connection, removes the stale WAL/SHM journal files left by the
        previous database, and advances the generation counter so other
        threads detect their cached connection is obsolete on next access
        and re-open against the replaced file.

        Threads that are mid-operation on the previous connection will lose
        any uncommitted writes when their connection is closed on next
        access — which is the intended behaviour: the database has been
        replaced wholesale.
        """
        # Close this thread's connection BEFORE unlinking journals so we are
        # not holding a write handle to the WAL file we are about to delete.
        self._close_local()
        if self._db_path != ":memory:":
            for suffix in ("-wal", "-shm"):
                journal = Path(self._db_path + suffix)
                journal.unlink(missing_ok=True)
        self._generation += 1
        logger.info(
            "SQLite connection reset (gen=%d); all threads will reconnect on next access.",
            self._generation,
        )
        # The file on disk has been replaced (e.g. fresh GCS download). Eagerly
        # heal the schema on the caller's connection so the post-condition
        # "after reconnect() returns, the schema is intact" holds locally —
        # worker threads on other generations get the same protection via the
        # per-connection check in the ``connection`` property (issue #461).
        self.ensure_schema()

    def close(self) -> None:
        """Close the calling thread's connection and invalidate other threads' caches.

        Bumping the generation ensures that other threads which still hold a
        connection from the previous generation will reopen on next access
        instead of operating on a connection whose database file has been
        replaced or removed.
        """
        self._close_local()
        self._generation += 1

    def _close_local(self) -> None:
        """Close the connection cached in this thread's storage, if any."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                logger.exception("Error closing SQLite connection")
            self._local.conn = None


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

    def reconnect(self) -> None:
        """Reset the database connection to pick up a replaced file on disk."""
        self._cm.reconnect()

    def verify_integrity(self) -> None:
        """Run ``PRAGMA quick_check`` against the underlying SQLite file.

        Raises:
            SqliteIntegrityError: when the database is malformed.

        """
        self._cm.check_integrity()

    def discard_local_file(self) -> None:
        """Delete the local SQLite file (and journals) so it can be re-downloaded."""
        self._cm.discard_file()

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
