"""Tests for SQLite backend repository implementations."""

import random
import sqlite3
import threading
from pathlib import Path

import pytest

from idea_shared.data.sqlite_backend import (
    SqliteIntegrityError,
    _SqliteConnectionManager,
    create_sqlite_repositories,
)


def _corrupt_sqlite_file(db_path: Path) -> None:
    """Overwrite a data page of *db_path* so SQLite reports it malformed.

    Writes deterministic random bytes starting at page offset 4096 (the second
    page — the first page holds the database header which SQLite still parses
    even on otherwise-broken files). The damage is enough that
    ``PRAGMA quick_check`` raises ``sqlite3.DatabaseError: database disk image
    is malformed``, the exact symptom in Sentry IDEA-HELSINKI-2K / issue #459.
    """
    rng = random.Random(42)
    with db_path.open("r+b") as fh:
        fh.seek(4096)
        fh.write(bytes(rng.randint(0, 255) for _ in range(2048)))


@pytest.fixture
def repos():
    """Create SQLite repositories with in-memory database."""
    return create_sqlite_repositories(":memory:")


@pytest.fixture
def segment_repo(repos):
    return repos[0]


@pytest.fixture
def disturbance_repo(repos):
    return repos[1]


@pytest.fixture
def profile_repo(repos):
    return repos[2]


class TestSqliteSegmentRepository:
    """Tests for SqliteSegmentRepository."""

    @pytest.mark.unit
    def test_get_segments_returns_empty_when_no_data(self, segment_repo):
        result = segment_repo.get_segments()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_segments(self, segment_repo, sample_segments):
        assert segment_repo.save_segments(sample_segments) is True
        result = segment_repo.get_segments()
        assert result == sample_segments
        assert len(result["segmentId"]) == 2

    @pytest.mark.unit
    def test_save_segments_rejects_invalid_data(self, segment_repo):
        assert segment_repo.save_segments({}) is False
        assert segment_repo.save_segments({"segmentId": "not_a_dict"}) is False

    @pytest.mark.unit
    def test_get_changelog_returns_empty_when_no_data(self, segment_repo):
        result = segment_repo.get_changelog()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_changelog(self, segment_repo, sample_changelog):
        segment_repo.save_changelog(sample_changelog)
        result = segment_repo.get_changelog()
        assert "seg_001" in result
        assert result["seg_001"]["current_hash"] == "abc123"

    @pytest.mark.unit
    def test_changelog_retention_enforced(self, segment_repo):
        """Save a changelog with 60 history entries; verify only 50 rows remain.

        save_changelog uses full-replace semantics (delete + reinsert per segment),
        so the retention limit is applied to the entries within a single call.
        60 history entries + 1 current entry = 61 rows inserted; 11 are pruned,
        leaving 50.
        """
        history = [
            {
                "geometry": {"type": "Point", "coordinates": [i, i]},
                "geometry_hash": f"hash_{i}",
                "change_type": "updated",
                "recorded_at": f"2024-01-01T{i:02d}:00:00+00:00",
            }
            for i in range(60)
        ]
        changelog = {
            "seg_retention": {
                "current_geometry": {"type": "Point", "coordinates": [60, 60]},
                "current_hash": "hash_60",
                "date_added": "2024-01-01T00:00:00+00:00",
                "history": history,
            }
        }
        segment_repo.save_changelog(changelog)

        # Check total entries for this segment (61 inserted, 11 pruned → 50 remain)
        conn = segment_repo._conn
        cursor = conn.execute(
            "SELECT COUNT(*) FROM segment_changelog WHERE segment_id = ?",
            ("seg_retention",),
        )
        count = cursor.fetchone()[0]
        assert count == 50

    @pytest.mark.unit
    def test_save_changelog_no_duplicates_on_repeat_call(self, segment_repo):
        """Repeated save_changelog calls must not duplicate history rows.

        The get_changelog → process → save_changelog round-trip means the
        history entries returned by get_changelog() are passed back in the
        next save_changelog() call. Without full-replace semantics this would
        create duplicate rows in segment_changelog.
        """
        changelog = {
            "seg_dup": {
                "current_geometry": {"type": "Point", "coordinates": [1, 1]},
                "current_hash": "h1",
                "date_added": "2024-01-01T00:00:00+00:00",
                "history": [],
            }
        }
        # First save: 1 row
        segment_repo.save_changelog(changelog)

        # Simulate a round-trip: read back, add a history entry, save again
        retrieved = segment_repo.get_changelog()
        # Geometry "changed" — old entry moves to history
        retrieved["seg_dup"]["history"].append(
            {
                "geometry": {"type": "Point", "coordinates": [1, 1]},
                "geometry_hash": "h1",
                "change_type": "updated",
                "recorded_at": "2024-01-01T00:00:00+00:00",
            }
        )
        retrieved["seg_dup"]["current_geometry"] = {
            "type": "Point",
            "coordinates": [2, 2],
        }
        retrieved["seg_dup"]["current_hash"] = "h2"
        segment_repo.save_changelog(retrieved)

        conn = segment_repo._conn
        cursor = conn.execute(
            "SELECT COUNT(*) FROM segment_changelog WHERE segment_id = ?",
            ("seg_dup",),
        )
        # Expect exactly 2 rows: current + 1 history entry (no duplicates)
        assert cursor.fetchone()[0] == 2

    @pytest.mark.unit
    def test_get_archive_returns_empty_when_no_data(self, segment_repo):
        result = segment_repo.get_archive()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_archive(self, segment_repo):
        archive = {
            "seg_old": {
                "last_geometry": {"type": "Point", "coordinates": [24.9, 60.1]},
                "last_hash": "oldhash",
                "date_added": "2024-01-01T00:00:00",
                "date_archived": "2024-06-01T00:00:00",
            }
        }
        segment_repo.save_archive(archive)
        result = segment_repo.get_archive()
        assert result == archive

    @pytest.mark.unit
    def test_rtree_populated_on_save(self, segment_repo, sample_segments):
        segment_repo.save_segments(sample_segments)
        conn = segment_repo._conn
        cursor = conn.execute("SELECT COUNT(*) FROM segments_rtree")
        count = cursor.fetchone()[0]
        assert count == 2

    @pytest.mark.unit
    def test_rtree_bounding_box_values(self, segment_repo):
        """Verify R-tree contains correct bounding box for known coordinates."""
        segments = {
            "segmentId": {
                "seg_bbox": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[10.0, 20.0], [30.0, 40.0]],
                    }
                }
            }
        }
        segment_repo.save_segments(segments)
        conn = segment_repo._conn
        cursor = conn.execute("SELECT min_x, max_x, min_y, max_y FROM segments_rtree")
        row = cursor.fetchone()
        assert row["min_x"] == 10.0
        assert row["max_x"] == 30.0
        assert row["min_y"] == 20.0
        assert row["max_y"] == 40.0


class TestSqliteDisturbanceRepository:
    """Tests for SqliteDisturbanceRepository."""

    @pytest.mark.unit
    def test_get_disturbances_returns_empty_when_no_data(self, disturbance_repo):
        result = disturbance_repo.get_disturbances()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_disturbances(self, disturbance_repo, sample_disturbances):
        assert disturbance_repo.save_disturbances(sample_disturbances) is True
        result = disturbance_repo.get_disturbances()
        assert result == sample_disturbances

    @pytest.mark.unit
    def test_save_disturbances_rejects_invalid_data(self, disturbance_repo):
        assert disturbance_repo.save_disturbances({}) is False
        assert disturbance_repo.save_disturbances({"segmentId": "not_dict"}) is False

    @pytest.mark.unit
    def test_detailed_collisions_json_fidelity(self, disturbance_repo):
        """Verify complex nested JSON in detailedCollisions round-trips correctly."""
        data = {
            "segmentId": {
                "seg_complex": {
                    "geometry": {"type": "Point", "coordinates": [24.9, 60.1]},
                    "detailedCollisions": [
                        {
                            "properties": {
                                "nested": {"deep": [1, 2, 3]},
                                "unicode": "Hämeentie \u2192 Sörnäinen",
                                "special_chars": "quotes \"and\" 'more'",
                            }
                        }
                    ],
                }
            }
        }
        disturbance_repo.save_disturbances(data)
        result = disturbance_repo.get_disturbances()
        assert result == data

    @pytest.mark.unit
    def test_save_replaces_all_disturbances(self, disturbance_repo):
        """Verify full-replace semantics — old data is removed."""
        data1 = {
            "segmentId": {
                "seg_a": {
                    "geometry": {"type": "Point", "coordinates": [1, 2]},
                    "detailedCollisions": [],
                }
            }
        }
        data2 = {
            "segmentId": {
                "seg_b": {
                    "geometry": {"type": "Point", "coordinates": [3, 4]},
                    "detailedCollisions": [],
                }
            }
        }
        disturbance_repo.save_disturbances(data1)
        disturbance_repo.save_disturbances(data2)
        result = disturbance_repo.get_disturbances()
        assert "seg_a" not in result.get("segmentId", {})
        assert "seg_b" in result["segmentId"]


class TestSqliteProfileRepository:
    """Tests for SqliteProfileRepository."""

    @pytest.mark.unit
    def test_get_profile_returns_none_when_missing(self, profile_repo):
        result = profile_repo.get_profile("nonexistent")
        assert result is None

    @pytest.mark.unit
    def test_save_and_get_profile(self, profile_repo):
        data = b"parquet-bytes-here"
        profile_repo.save_profile(
            "seg_001", data, "2024-01-01T00:00:00", "2025-01-01T00:00:00"
        )
        result = profile_repo.get_profile("seg_001")
        assert result == data

    @pytest.mark.unit
    def test_save_profile_upsert(self, profile_repo):
        """Second save replaces existing profile."""
        profile_repo.save_profile(
            "seg_001", b"old", "2024-01-01T00:00:00", "2025-01-01T00:00:00"
        )
        profile_repo.save_profile(
            "seg_001", b"new", "2024-06-01T00:00:00", "2025-06-01T00:00:00"
        )
        result = profile_repo.get_profile("seg_001")
        assert result == b"new"

    @pytest.mark.unit
    def test_delete_profile(self, profile_repo):
        profile_repo.save_profile(
            "seg_001", b"data", "2024-01-01T00:00:00", "2025-01-01T00:00:00"
        )
        profile_repo.delete_profile("seg_001")
        assert profile_repo.get_profile("seg_001") is None

    @pytest.mark.unit
    def test_get_all_profile_ids(self, profile_repo):
        profile_repo.save_profile(
            "seg_b", b"data", "2024-01-01T00:00:00", "2025-01-01T00:00:00"
        )
        profile_repo.save_profile(
            "seg_a", b"data", "2024-01-01T00:00:00", "2025-01-01T00:00:00"
        )
        ids = profile_repo.get_all_profile_ids()
        assert ids == ["seg_a", "seg_b"]

    @pytest.mark.unit
    def test_delete_expired_profiles(self, profile_repo):
        # One expired, one not
        profile_repo.save_profile(
            "seg_expired",
            b"old",
            "2020-01-01T00:00:00",
            "2020-06-01T00:00:00",
        )
        profile_repo.save_profile(
            "seg_valid",
            b"current",
            "2024-01-01T00:00:00",
            "2099-01-01T00:00:00",
        )
        deleted = profile_repo.delete_expired_profiles()
        assert deleted == 1
        assert profile_repo.get_profile("seg_expired") is None
        assert profile_repo.get_profile("seg_valid") is not None


class TestSqliteReconnect:
    """Tests for SQLite connection reconnection after file replacement."""

    @pytest.mark.unit
    def test_reconnect_picks_up_new_data(self, tmp_path):
        """After reconnect(), queries reflect the current database file."""
        db_path = tmp_path / "segments.db"

        # Create repo and save initial data
        seg_repo, _, _ = create_sqlite_repositories(db_path)
        seg_repo.save_segments(
            {
                "segmentId": {
                    "seg_old": {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0, 0], [1, 1]],
                        }
                    }
                }
            }
        )
        assert "seg_old" in seg_repo.get_segments()["segmentId"]

        # Simulate file replacement (like GCS download overwriting the file):
        # create a new database at a temp path, then replace the original
        replacement = tmp_path / "segments_new.db"
        new_repo, _, _ = create_sqlite_repositories(replacement)
        new_repo.save_segments(
            {
                "segmentId": {
                    "seg_new": {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[2, 2], [3, 3]],
                        }
                    }
                }
            }
        )
        new_repo._cm.close()

        # Replace the file on disk
        replacement.replace(db_path)

        # Before reconnect: stale connection may still return old data
        # After reconnect: should see new data
        seg_repo.reconnect()
        result = seg_repo.get_segments()
        assert "seg_new" in result["segmentId"]
        assert "seg_old" not in result["segmentId"]

    @pytest.mark.unit
    def test_reconnect_on_in_memory_db(self):
        """reconnect() on in-memory DB resets to empty state."""
        seg_repo, _, _ = create_sqlite_repositories(":memory:")
        seg_repo.save_segments(
            {
                "segmentId": {
                    "seg_1": {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0, 0], [1, 1]],
                        }
                    }
                }
            }
        )
        seg_repo.reconnect()
        # In-memory DB is gone after close; reconnect creates a fresh one
        # but schema needs to be re-applied
        seg_repo._cm.ensure_schema()
        assert seg_repo.get_segments() == {}

    @pytest.mark.unit
    def test_disturbance_reconnect_picks_up_new_data(self, tmp_path):
        """Regression for orchestrator's stale-connection bug on disturbances.db.

        The orchestrator opens a SqliteDisturbanceRepository against the
        disturbances.db it just downloaded, then re-downloads the file each
        management cycle. Without reconnect(), the connection's WAL/SHM
        journals cause SQLite to replay the original empty transactions on
        top of the freshly downloaded file, so get_disturbances() returns
        nothing and the manager creates 0 workers.
        """
        db_path = tmp_path / "disturbances.db"

        _, dist_repo, _ = create_sqlite_repositories(db_path)
        dist_repo.save_disturbances(
            {
                "segmentId": {
                    "seg_old": {
                        "geometry": {"type": "LineString", "coordinates": []},
                        "detailedCollisions": [],
                    }
                }
            }
        )
        assert "seg_old" in dist_repo.get_disturbances()["segmentId"]

        replacement = tmp_path / "disturbances_new.db"
        _, new_repo, _ = create_sqlite_repositories(replacement)
        new_repo.save_disturbances(
            {
                "segmentId": {
                    "seg_new": {
                        "geometry": {"type": "LineString", "coordinates": []},
                        "detailedCollisions": [{"id": 1}],
                    }
                }
            }
        )
        new_repo._cm.close()

        replacement.replace(db_path)

        dist_repo.reconnect()
        result = dist_repo.get_disturbances()
        assert "seg_new" in result["segmentId"]
        assert "seg_old" not in result["segmentId"]


class TestConnectionManagerThreading:
    """Cross-thread invariants for ``_SqliteConnectionManager``.

    These regression tests cover the failure mode where ``reconnect()`` only
    refreshed the calling thread's cached connection, leaving worker threads
    operating on connections bound to a database file that had since been
    replaced — a known cause of "database disk image is malformed" in
    production (Sentry IDEA-HELSINKI-2K).
    """

    @pytest.mark.unit
    def test_each_thread_gets_its_own_connection(self, tmp_path: Path) -> None:
        """``connection`` returns a thread-local handle, not a shared one."""
        cm = _SqliteConnectionManager(tmp_path / "db.sqlite")
        cm.ensure_schema()
        main_conn = cm.connection
        worker_conn: list[sqlite3.Connection] = []

        def worker() -> None:
            worker_conn.append(cm.connection)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert worker_conn[0] is not main_conn

    @pytest.mark.unit
    def test_reconnect_bumps_generation_and_refreshes_caller(
        self, tmp_path: Path
    ) -> None:
        """reconnect() bumps the generation and gives the caller a new handle.

        The generation bump is what forces *other* threads to drop their
        cached connection on next access — the regression check for Sentry
        IDEA-HELSINKI-2K.
        """
        cm = _SqliteConnectionManager(tmp_path / "db.sqlite")
        cm.ensure_schema()
        before = cm.connection
        gen_before = cm._generation

        cm.reconnect()

        assert cm._generation == gen_before + 1
        # Calling thread's _local.conn was cleared by reconnect; next access
        # opens a fresh handle.
        after = cm.connection
        assert after is not before

    @pytest.mark.unit
    def test_other_thread_drops_stale_connection_on_next_access(
        self, tmp_path: Path
    ) -> None:
        """A worker that opened a connection BEFORE close() must reopen after.

        Probes Gemini's high-priority concern: prior to the fix a worker's
        ``_local.conn`` cached from a previous generation was reused
        verbatim, leaving the worker bound to a database file inode that
        had since been replaced. The generation bump on close()/reconnect()
        is what makes the worker drop the stale handle on its next access.

        Uses ``close()`` rather than ``reconnect()`` to isolate the
        per-thread refresh invariant from the WAL/SHM file-replacement
        dance, which has its own coverage in
        ``test_reconnect_after_replacement_picks_up_new_data``.
        """
        cm = _SqliteConnectionManager(tmp_path / "db.sqlite")
        cm.ensure_schema()

        captured_first: list[sqlite3.Connection] = []
        captured_second: list[sqlite3.Connection] = []
        gate_after_first = threading.Event()
        proceed_with_second = threading.Event()

        def worker() -> None:
            captured_first.append(cm.connection)
            gate_after_first.set()
            proceed_with_second.wait(timeout=5.0)
            captured_second.append(cm.connection)

        t = threading.Thread(target=worker)
        t.start()

        assert gate_after_first.wait(timeout=5.0)
        cm.close()
        proceed_with_second.set()
        t.join(timeout=5.0)

        assert captured_first and captured_second
        assert captured_second[0] is not captured_first[0]

    @pytest.mark.unit
    def test_close_bumps_generation(self, tmp_path: Path) -> None:
        cm = _SqliteConnectionManager(tmp_path / "db.sqlite")
        cm.ensure_schema()
        gen_before = cm._generation
        cm.close()
        assert cm._generation == gen_before + 1


class TestSchemaIdempotency:
    """Test that schema migration is idempotent."""

    @pytest.mark.unit
    def test_ensure_schema_called_twice(self):
        """Running ensure_schema twice should not raise."""
        seg_repo, _, _ = create_sqlite_repositories(":memory:")
        # Schema already applied by factory; calling again should be safe
        seg_repo._cm.ensure_schema()
        # Verify tables still work
        result = seg_repo.get_segments()
        assert result == {}


class TestSchemaSelfHealing:
    """Regression tests for issue #461 — missing tables despite schema_version=1.

    A snapshot downloaded from GCS (or otherwise replaced on disk) may report
    ``schema_version`` v1 yet be missing application tables — e.g. a partial
    upload, a stale snapshot, or a manual `DROP TABLE`. Before #461 the
    ``ensure_schema`` check trusted ``schema_version`` alone, so the orchestrator
    crashed every cycle with ``OperationalError: no such table: disturbances``.
    """

    @pytest.mark.unit
    def test_ensure_schema_restores_missing_table_when_version_already_v1(
        self, tmp_path: Path
    ) -> None:
        """If schema_version=1 but disturbances is missing, re-apply migration."""
        db_path = tmp_path / "broken.db"

        # Create a fully-initialised DB then forcibly drop disturbances so we
        # simulate a snapshot that claims to be at v1 but lacks a table.
        _, dist_repo, _ = create_sqlite_repositories(db_path)
        dist_repo._cm.connection.execute("DROP TABLE disturbances")
        dist_repo._cm.connection.commit()
        dist_repo._cm.close()

        # Reopen the broken DB. ensure_schema must notice the missing table
        # and re-apply the migration despite schema_version reading v1.
        _, healed_repo, _ = create_sqlite_repositories(db_path)
        assert healed_repo.get_disturbances() == {}

        # And the repo is now usable end-to-end.
        assert (
            healed_repo.save_disturbances(
                {
                    "segmentId": {
                        "seg_x": {
                            "geometry": {"type": "Point", "coordinates": [0, 0]},
                            "detailedCollisions": [],
                        }
                    }
                }
            )
            is True
        )
        assert "seg_x" in healed_repo.get_disturbances()["segmentId"]

    @pytest.mark.unit
    def test_reconnect_reapplies_schema_when_replacement_file_missing_table(
        self, tmp_path: Path
    ) -> None:
        """reconnect() must verify the freshly-mounted file's schema.

        When the orchestrator's hourly disturbance refresh downloads a broken
        snapshot, the connection is reopened against a file that may be
        missing tables. ``reconnect`` must heal the schema before the next
        ``get_disturbances`` call, otherwise the manager's main loop crashes
        on every cycle (issue #461).
        """
        db_path = tmp_path / "disturbances.db"

        _, dist_repo, _ = create_sqlite_repositories(db_path)
        dist_repo.save_disturbances(
            {
                "segmentId": {
                    "seg_old": {
                        "geometry": {"type": "LineString", "coordinates": []},
                        "detailedCollisions": [],
                    }
                }
            }
        )

        # Simulate a replacement snapshot that has schema_version=1 but is
        # missing the disturbances table — i.e. the failure mode from #461.
        replacement = tmp_path / "disturbances_broken.db"
        _, replacement_repo, _ = create_sqlite_repositories(replacement)
        replacement_repo._cm.connection.execute("DROP TABLE disturbances")
        replacement_repo._cm.connection.commit()
        replacement_repo._cm.close()

        replacement.replace(db_path)

        # Without the #461 fix, this raises OperationalError on get_disturbances.
        dist_repo.reconnect()
        assert dist_repo.get_disturbances() == {}

    @pytest.mark.unit
    def test_fresh_connection_validates_schema_on_open(self, tmp_path: Path) -> None:
        """A worker thread opening its connection on a broken file must self-heal.

        Reproduces the post-#461 review concern: when one thread calls
        ``reconnect()`` (which bumps the generation), a *different* thread
        running a query in parallel may open its fresh handle before the
        reconnecting thread has finished ``ensure_schema``. Without per-
        connection validation that thread would crash with ``no such table``.
        Here we simulate that by skipping the manager-driven reconnect path
        entirely and confirming that a thread which opens its first handle
        on a broken file still gets a healed schema.
        """
        db_path = tmp_path / "broken.db"

        # Seed the file with schema_version=1 but missing the disturbances table.
        seed = _SqliteConnectionManager(db_path)
        seed.ensure_schema()
        seed.connection.execute("DROP TABLE disturbances")
        seed.connection.commit()
        seed.close()

        # A *new* manager — emulating a worker thread that has never opened
        # this DB before — reads through the connection property without an
        # explicit ensure_schema() call. The property's refresh path is the
        # only thing that can save it from "no such table".
        worker_cm = _SqliteConnectionManager(db_path)
        cursor = worker_cm.connection.execute("SELECT COUNT(*) FROM disturbances")
        assert cursor.fetchone()[0] == 0


class TestCorruptionDetection:
    """Regression tests for issue #459 — malformed SQLite snapshots crash orchestrator.

    The orchestrator downloads ``disturbances.db`` from GCS. If the downloaded
    file is malformed (mid-stream truncation, faulty upstream writer, FUSE
    metadata cache returning a stale page) every ``get_disturbances()`` call
    raises ``sqlite3.DatabaseError: database disk image is malformed`` until
    the main loop's consecutive-error guard kills the pod, only for the
    restarted pod to pick up the same broken file from upstream.

    These tests exercise the detection-and-recovery primitives that let
    callers self-heal instead of CrashLoopBackOff'ing.
    """

    @pytest.mark.unit
    def test_check_integrity_passes_on_healthy_db(self, tmp_path: Path) -> None:
        """``check_integrity`` is a no-op when the DB is well-formed."""
        _, dist_repo, _ = create_sqlite_repositories(tmp_path / "ok.db")
        # Should not raise.
        dist_repo.verify_integrity()

    @pytest.mark.unit
    def test_check_integrity_raises_on_corrupt_db(self, tmp_path: Path) -> None:
        """A malformed file surfaces as ``SqliteIntegrityError`` (not bare DatabaseError)."""
        db_path = tmp_path / "corrupt.db"

        # Populate a real DB then scramble its data pages.
        _, dist_repo, _ = create_sqlite_repositories(db_path)
        dist_repo.save_disturbances(
            {
                "segmentId": {
                    "seg_a": {
                        "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "detailedCollisions": [],
                    }
                }
            }
        )
        dist_repo._cm.close()

        _corrupt_sqlite_file(db_path)

        # New manager opens the broken file; PRAGMA quick_check must fail.
        _, broken_repo, _ = create_sqlite_repositories(db_path)
        with pytest.raises(SqliteIntegrityError) as exc_info:
            broken_repo.verify_integrity()
        # The typed exception preserves the path for callers/logs.
        assert str(db_path) in str(exc_info.value)

    @pytest.mark.unit
    def test_discard_local_file_removes_db_and_journals(self, tmp_path: Path) -> None:
        """After ``discard_local_file`` the SQLite file is gone for re-download."""
        db_path = tmp_path / "to_discard.db"
        _, dist_repo, _ = create_sqlite_repositories(db_path)
        dist_repo.save_disturbances({"segmentId": {}})
        # WAL mode plus an active write leaves -wal/-shm sidecars behind.
        assert db_path.exists()

        dist_repo.discard_local_file()

        assert not db_path.exists()
        assert not (tmp_path / "to_discard.db-wal").exists()
        assert not (tmp_path / "to_discard.db-shm").exists()
        assert not (tmp_path / "to_discard.db-journal").exists()

    @pytest.mark.unit
    def test_discard_local_file_is_idempotent(self, tmp_path: Path) -> None:
        """Calling ``discard_local_file`` twice is safe (no FileNotFoundError)."""
        _, dist_repo, _ = create_sqlite_repositories(tmp_path / "x.db")
        dist_repo.discard_local_file()
        dist_repo.discard_local_file()  # no raise

    @pytest.mark.unit
    def test_discard_local_file_noop_for_memory_db(self) -> None:
        """In-memory databases are not unlinkable; discard is a no-op."""
        _, dist_repo, _ = create_sqlite_repositories(":memory:")
        dist_repo.discard_local_file()  # no raise

    @pytest.mark.unit
    def test_recover_flow_redownload_after_corruption(self, tmp_path: Path) -> None:
        """End-to-end recovery: corrupt file → discard → replace → verify.

        Models the orchestrator's per-cycle refresh hook after the fix:
        on detection it discards the local file and the next ``download``
        re-pulls the upstream blob. Once a healthy file is in place,
        ``verify_integrity`` returns cleanly.
        """
        db_path = tmp_path / "disturbances.db"
        upstream = tmp_path / "upstream_disturbances.db"

        _, healthy_repo, _ = create_sqlite_repositories(upstream)
        healthy_repo.save_disturbances(
            {
                "segmentId": {
                    "seg_healthy": {
                        "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "detailedCollisions": [{"id": 1}],
                    }
                }
            }
        )
        healthy_repo._cm.close()

        # Simulate the corrupt download already on disk.
        import shutil

        shutil.copy2(upstream, db_path)
        _corrupt_sqlite_file(db_path)

        _, dist_repo, _ = create_sqlite_repositories(db_path)
        with pytest.raises(SqliteIntegrityError):
            dist_repo.verify_integrity()

        # The "refresh hook" deletes the local file and re-downloads.
        dist_repo.discard_local_file()
        shutil.copy2(upstream, db_path)

        # reconnect picks up the new file; integrity is now ok.
        dist_repo.reconnect()
        dist_repo.verify_integrity()
        assert "seg_healthy" in dist_repo.get_disturbances()["segmentId"]
