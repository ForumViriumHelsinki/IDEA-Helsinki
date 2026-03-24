"""Tests for SQLite backend repository implementations."""

import pytest

from idea_shared.data.sqlite_backend import create_sqlite_repositories


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
