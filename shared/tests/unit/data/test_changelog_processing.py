"""Tests for extracted changelog processing logic and repository-based changelog updates."""

import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from idea_shared.data.json_backend import JsonSegmentRepository
from idea_shared.lib.FcdUtils import (
    ChangelogResult,
    extract_fresh_segments,
    process_segment_changelog,
    update_segment_changelog_from_repo,
)


def _geometry_hash(geometry: dict) -> str:
    """Compute SHA-256 hash of geometry (matching FcdUtils logic)."""
    return hashlib.sha256(
        json.dumps(geometry, sort_keys=True).encode("utf-8")
    ).hexdigest()


GEOM_A = {"type": "LineString", "coordinates": [[24.93, 60.17], [24.94, 60.18]]}
GEOM_B = {"type": "LineString", "coordinates": [[24.94, 60.18], [24.95, 60.19]]}
GEOM_A_MODIFIED = {
    "type": "LineString",
    "coordinates": [[24.93, 60.17], [24.94, 60.185]],
}

PROCESSING_DATE = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


class TestExtractFreshSegments:
    """Tests for extract_fresh_segments."""

    @pytest.mark.unit
    def test_extracts_geometries(self):
        """Extracts segment_id -> geometry mapping from segments data."""
        data = {
            "segmentId": {
                "seg_1": {"geometry": GEOM_A},
                "seg_2": {"geometry": GEOM_B},
            }
        }
        result = extract_fresh_segments(data)
        assert result == {"seg_1": GEOM_A, "seg_2": GEOM_B}

    @pytest.mark.unit
    def test_skips_entries_without_geometry(self):
        """Skips entries that don't have a geometry key."""
        data = {
            "segmentId": {
                "seg_1": {"geometry": GEOM_A},
                "seg_2": {"no_geometry": True},
                "seg_3": "not_a_dict",
            }
        }
        result = extract_fresh_segments(data)
        assert result == {"seg_1": GEOM_A}

    @pytest.mark.unit
    def test_returns_empty_for_missing_segment_id(self):
        """Returns empty dict when segmentId key is missing."""
        assert extract_fresh_segments({}) == {}
        assert extract_fresh_segments({"other": "data"}) == {}


class TestProcessSegmentChangelog:
    """Tests for process_segment_changelog (pure logic, no I/O)."""

    @pytest.mark.unit
    def test_detects_new_segments(self):
        """New segments are added to changelog."""
        fresh = {"seg_1": GEOM_A, "seg_2": GEOM_B}
        result = process_segment_changelog(fresh, {}, {}, PROCESSING_DATE)

        assert isinstance(result, ChangelogResult)
        assert "seg_1" in result.changelog
        assert "seg_2" in result.changelog
        assert result.newly_added_ids == ["seg_1", "seg_2"]
        assert result.modified_ids == []
        assert result.removed_ids == set()

        # Verify changelog entry structure
        entry = result.changelog["seg_1"]
        assert entry["current_geometry"] == GEOM_A
        assert entry["current_hash"] == _geometry_hash(GEOM_A)
        assert entry["date_added"] == PROCESSING_DATE.isoformat()
        assert entry["history"] == []

    @pytest.mark.unit
    def test_detects_removed_segments(self):
        """Removed segments are moved to archive."""
        existing_changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            }
        }
        fresh = {}  # seg_1 no longer present

        result = process_segment_changelog(
            fresh, existing_changelog, {}, PROCESSING_DATE
        )

        assert result.removed_ids == {"seg_1"}
        assert "seg_1" not in result.changelog
        assert "seg_1" in result.archive
        assert result.archive["seg_1"]["date_archived"] == PROCESSING_DATE.isoformat()

    @pytest.mark.unit
    def test_detects_modified_geometry(self):
        """Modified geometry is detected and old state archived in history."""
        existing_changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            }
        }
        fresh = {"seg_1": GEOM_A_MODIFIED}

        result = process_segment_changelog(
            fresh, existing_changelog, {}, PROCESSING_DATE
        )

        assert result.modified_ids == ["seg_1"]
        assert result.changelog["seg_1"]["current_geometry"] == GEOM_A_MODIFIED
        assert result.changelog["seg_1"]["current_hash"] == _geometry_hash(
            GEOM_A_MODIFIED
        )
        # Old geometry should be in history
        assert len(result.changelog["seg_1"]["history"]) == 1
        assert result.changelog["seg_1"]["history"][0]["geometry"] == GEOM_A

    @pytest.mark.unit
    def test_no_changes_detected(self):
        """No changes when segments are identical."""
        existing_changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            }
        }
        fresh = {"seg_1": GEOM_A}

        result = process_segment_changelog(
            fresh, existing_changelog, {}, PROCESSING_DATE
        )

        assert result.newly_added_ids == []
        assert result.modified_ids == []
        assert result.removed_ids == set()

    @pytest.mark.unit
    def test_does_not_mutate_input(self):
        """Input dicts are not mutated."""
        changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            }
        }
        archive = {"seg_old": {"date_archived": "2024-01-01"}}

        changelog_copy = json.loads(json.dumps(changelog))
        archive_copy = json.loads(json.dumps(archive))

        process_segment_changelog(
            {"seg_1": GEOM_A_MODIFIED}, changelog, archive, PROCESSING_DATE
        )

        assert changelog == changelog_copy
        assert archive == archive_copy

    @pytest.mark.unit
    def test_combined_add_remove_modify(self):
        """Handles new, removed, and modified segments simultaneously."""
        existing_changelog = {
            "seg_keep": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            },
            "seg_remove": {
                "current_geometry": GEOM_B,
                "current_hash": _geometry_hash(GEOM_B),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            },
        }
        fresh = {
            "seg_keep": GEOM_A_MODIFIED,  # modified
            "seg_new": GEOM_B,  # new
            # seg_remove is absent -> removed
        }

        result = process_segment_changelog(
            fresh, existing_changelog, {}, PROCESSING_DATE
        )

        assert "seg_new" in result.newly_added_ids
        assert "seg_keep" in result.modified_ids
        assert "seg_remove" in result.removed_ids
        assert "seg_remove" not in result.changelog
        assert "seg_remove" in result.archive


class TestUpdateSegmentChangelogFromRepo:
    """Tests for update_segment_changelog_from_repo."""

    @pytest.mark.unit
    def test_full_cycle_with_json_repo(self, tmp_path):
        """Full changelog update cycle using JsonSegmentRepository."""
        repo = JsonSegmentRepository(
            mapping_path=tmp_path / "segments.json",
            changelog_path=tmp_path / "changelog.json",
            archive_path=tmp_path / "archive.json",
        )

        # Save initial segments
        segments = {
            "segmentId": {
                "seg_1": {"geometry": GEOM_A},
                "seg_2": {"geometry": GEOM_B},
            }
        }
        repo.save_segments(segments)

        # Run changelog update - should detect two new segments
        update_segment_changelog_from_repo(repo, PROCESSING_DATE)

        changelog = repo.get_changelog()
        assert "seg_1" in changelog
        assert "seg_2" in changelog

    @pytest.mark.unit
    def test_handles_empty_repo(self, tmp_path):
        """Handles case where repository has no segments (no crash)."""
        repo = JsonSegmentRepository(
            mapping_path=tmp_path / "segments.json",
            changelog_path=tmp_path / "changelog.json",
            archive_path=tmp_path / "archive.json",
        )
        # No segments saved - should log error and return gracefully
        update_segment_changelog_from_repo(repo, PROCESSING_DATE)
        assert repo.get_changelog() == {}

    @pytest.mark.unit
    def test_detects_changes_across_updates(self, tmp_path):
        """Detects removals when segments change between updates."""
        repo = JsonSegmentRepository(
            mapping_path=tmp_path / "segments.json",
            changelog_path=tmp_path / "changelog.json",
            archive_path=tmp_path / "archive.json",
        )

        # First update: two segments
        repo.save_segments(
            {
                "segmentId": {
                    "seg_1": {"geometry": GEOM_A},
                    "seg_2": {"geometry": GEOM_B},
                }
            }
        )
        update_segment_changelog_from_repo(repo, PROCESSING_DATE)

        # Second update: remove seg_2
        repo.save_segments({"segmentId": {"seg_1": {"geometry": GEOM_A}}})
        later_date = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)
        update_segment_changelog_from_repo(repo, later_date)

        changelog = repo.get_changelog()
        archive = repo.get_archive()
        assert "seg_1" in changelog
        assert "seg_2" not in changelog
        assert "seg_2" in archive

    @pytest.mark.unit
    def test_uses_mock_repository(self):
        """Works with any SegmentRepository implementation (mock)."""
        mock_repo = MagicMock()
        mock_repo.get_segments.return_value = {
            "segmentId": {"seg_1": {"geometry": GEOM_A}}
        }
        mock_repo.get_changelog.return_value = {}
        mock_repo.get_archive.return_value = {}

        update_segment_changelog_from_repo(mock_repo, PROCESSING_DATE)

        mock_repo.save_changelog.assert_called_once()
        saved_changelog = mock_repo.save_changelog.call_args[0][0]
        assert "seg_1" in saved_changelog


class TestSegmentHistoryDepthCap:
    """Tests for MAX_SEGMENT_HISTORY_DEPTH trimming (#240)."""

    @pytest.mark.unit
    @patch("idea_shared.lib.FcdUtils.MAX_SEGMENT_HISTORY_DEPTH", 3)
    def test_history_trimmed_at_max_depth(self):
        """History exceeding max depth is trimmed to keep most recent entries."""
        existing_changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [
                    {"date_archived": f"2024-0{i}-01", "geometry": GEOM_A}
                    for i in range(1, 4)  # 3 existing entries (at max)
                ],
            }
        }
        fresh = {"seg_1": GEOM_A_MODIFIED}

        result = process_segment_changelog(
            fresh, existing_changelog, {}, PROCESSING_DATE
        )

        # With max=3, after appending a 4th entry, oldest should be trimmed
        assert len(result.changelog["seg_1"]["history"]) == 3
        # Most recent entry should be the newly archived geometry
        assert result.changelog["seg_1"]["history"][-1]["geometry"] == GEOM_A
        assert (
            result.changelog["seg_1"]["history"][-1]["date_archived"]
            == PROCESSING_DATE.isoformat()
        )
        # Oldest entry (2024-01-01) should have been trimmed
        assert result.changelog["seg_1"]["history"][0]["date_archived"] == "2024-02-01"

    @pytest.mark.unit
    @patch("idea_shared.lib.FcdUtils.MAX_SEGMENT_HISTORY_DEPTH", 5)
    def test_history_below_max_not_trimmed(self):
        """History below max depth is left untouched."""
        existing_changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [
                    {"date_archived": "2024-01-01", "geometry": GEOM_B},
                ],
            }
        }
        fresh = {"seg_1": GEOM_A_MODIFIED}

        result = process_segment_changelog(
            fresh, existing_changelog, {}, PROCESSING_DATE
        )

        # 1 existing + 1 new = 2, well below max of 5
        assert len(result.changelog["seg_1"]["history"]) == 2

    @pytest.mark.unit
    @patch("idea_shared.lib.FcdUtils.MAX_SEGMENT_HISTORY_DEPTH", 2)
    def test_repeated_modifications_stay_capped(self):
        """Multiple sequential modifications keep history at max depth."""
        changelog = {
            "seg_1": {
                "current_geometry": GEOM_A,
                "current_hash": _geometry_hash(GEOM_A),
                "date_added": "2024-01-01T00:00:00",
                "history": [],
            }
        }

        geometries = [GEOM_A_MODIFIED, GEOM_B, GEOM_A]
        for geom in geometries:
            fresh = {"seg_1": geom}
            result = process_segment_changelog(
                fresh, changelog, {}, PROCESSING_DATE
            )
            changelog = result.changelog

        # After 3 modifications with max=2, only last 2 should remain
        assert len(changelog["seg_1"]["history"]) == 2
