"""Unit tests for FcdUtils module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from idea_shared.lib import FcdUtils


class TestGetFcdGeometries:
    """Tests for get_fcd_geometries function."""

    @pytest.mark.unit
    def test_empty_dict_returns_empty(self):
        """Empty dictionary returns empty result."""
        result = FcdUtils.get_fcd_geometries({})
        assert result == {}

    @pytest.mark.unit
    def test_none_input_returns_empty(self):
        """None input returns empty result."""
        result = FcdUtils.get_fcd_geometries(None)  # type: ignore[arg-type]
        assert result == {}

    @pytest.mark.unit
    def test_missing_segment_id_key(self):
        """Test handling of missing segmentId key."""
        fcd_data = {"other_key": "some_value"}
        result = FcdUtils.get_fcd_geometries(fcd_data)
        assert result == {}

    @pytest.mark.unit
    def test_valid_single_segment(self):
        """Test extracting geometry from a single valid segment."""
        fcd_data = {
            "segmentId": {
                "123": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[24.9384, 60.1699], [24.9404, 60.1719]],
                    }
                }
            }
        }
        result = FcdUtils.get_fcd_geometries(fcd_data)
        assert "segmentId" in result
        assert "123" in result["segmentId"]
        assert result["segmentId"]["123"]["geometry"]["type"] == "LineString"

    @pytest.mark.unit
    def test_multiple_segments(self):
        """Test extracting geometries from multiple segments."""
        fcd_data = {
            "segmentId": {
                "123": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[24.9384, 60.1699]],
                    }
                },
                "456": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[24.9404, 60.1719]],
                    }
                },
            }
        }
        result = FcdUtils.get_fcd_geometries(fcd_data)
        assert len(result["segmentId"]) == 2
        assert "123" in result["segmentId"]
        assert "456" in result["segmentId"]

    @pytest.mark.unit
    def test_segment_without_geometry_skipped(self):
        """Segments without geometry are skipped."""
        fcd_data = {
            "segmentId": {
                "123": {"geometry": {"type": "LineString"}},
                "456": {"observations": []},  # No geometry key
            }
        }
        result = FcdUtils.get_fcd_geometries(fcd_data)
        assert len(result["segmentId"]) == 1
        assert "123" in result["segmentId"]
        assert "456" not in result["segmentId"]


class TestExtractTimestampFromFileName:
    """Tests for extract_timestamp_str_from_file_name function."""

    @pytest.mark.unit
    def test_valid_timestamp_without_microseconds(self):
        """Test extracting timestamp without microseconds."""
        filename = "data_2024-01-15T10:30:45.json"
        result = FcdUtils.extract_timestamp_str_from_file_name(filename)
        assert result == "2024-01-15T10:30:45"

    @pytest.mark.unit
    def test_valid_timestamp_with_microseconds(self):
        """Test extracting timestamp with microseconds."""
        filename = "data_2024-01-15T10:30:45.123456.json"
        result = FcdUtils.extract_timestamp_str_from_file_name(
            filename, include_microseconds=True
        )
        assert result == "2024-01-15T10:30:45.123456"

    @pytest.mark.unit
    def test_timestamp_with_microseconds_truncated(self):
        """Microseconds are truncated when not requested."""
        filename = "data_2024-01-15T10:30:45.999999.json"
        result = FcdUtils.extract_timestamp_str_from_file_name(
            filename, include_microseconds=False
        )
        assert result == "2024-01-15T10:30:45"

    @pytest.mark.unit
    def test_no_timestamp_returns_none(self):
        """Files without timestamp return None."""
        filename = "data_file_without_timestamp.json"
        result = FcdUtils.extract_timestamp_str_from_file_name(filename)
        assert result is None

    @pytest.mark.unit
    def test_invalid_timestamp_format(self):
        """Invalid timestamp formats return None."""
        filename = "data_INVALID_TIMESTAMP.json"  # Invalid date/time
        result = FcdUtils.extract_timestamp_str_from_file_name(filename)
        assert result is None

    @pytest.mark.unit
    def test_timestamp_in_middle_of_path(self):
        """Test extracting timestamp from path."""
        filename = "path/to/2024-01-15T10:30:45.json"
        result = FcdUtils.extract_timestamp_str_from_file_name(filename)
        assert result == "2024-01-15T10:30:45"


class TestParseJsonFromBytes:
    """Tests for parse_json_from_bytes function."""

    @pytest.mark.unit
    def test_valid_json_bytes(self):
        """Test parsing valid JSON from bytes."""
        data = {"key": "value", "number": 42}
        json_bytes = json.dumps(data).encode("utf-8")
        result = FcdUtils.parse_json_from_bytes(json_bytes)
        assert result == data

    @pytest.mark.unit
    def test_empty_json_object(self):
        """Test parsing empty JSON object."""
        json_bytes = b"{}"
        result = FcdUtils.parse_json_from_bytes(json_bytes)
        assert result == {}

    @pytest.mark.unit
    def test_invalid_utf8_returns_none(self):
        """Invalid UTF-8 encoding returns None."""
        invalid_bytes = b"\x80\x81\x82"
        result = FcdUtils.parse_json_from_bytes(invalid_bytes)
        assert result is None

    @pytest.mark.unit
    def test_invalid_json_returns_none(self):
        """Invalid JSON returns None."""
        invalid_json = b'{"invalid": json}'
        result = FcdUtils.parse_json_from_bytes(invalid_json)
        assert result is None

    @pytest.mark.unit
    def test_complex_nested_json(self):
        """Test parsing complex nested JSON."""
        data = {
            "segmentId": {
                "123": {
                    "observations": [{"timestamp": "2024-01-15", "speed": 45.5}],
                    "geometry": {"type": "LineString"},
                }
            }
        }
        json_bytes = json.dumps(data).encode("utf-8")
        result = FcdUtils.parse_json_from_bytes(json_bytes)
        assert result == data


class TestWriteJsonRecords:
    """Tests for write_json_records function."""

    @pytest.mark.unit
    def test_write_valid_records(self):
        """Test writing valid JSON records to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            records = {"segmentId": {"123": {"geometry": "data"}}}

            result = FcdUtils.write_json_records(records, str(filepath))

            assert result is True
            assert filepath.exists()

            with open(filepath) as f:
                written_data = json.load(f)
            assert written_data == records

    @pytest.mark.unit
    def test_write_creates_parent_directories(self):
        """Parent directories are created if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "test.json"
            records = {"segmentId": {"123": {}}}

            result = FcdUtils.write_json_records(records, str(filepath))

            assert result is True
            assert filepath.exists()
            assert filepath.parent.exists()

    @pytest.mark.unit
    def test_write_invalid_records_returns_false(self):
        """Invalid records return False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            records = {"not_segmentId": {}}  # Missing segmentId key

            result = FcdUtils.write_json_records(records, str(filepath))

            assert result is False

    @pytest.mark.unit
    def test_write_empty_segments(self):
        """Test writing empty segments dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            records = {"segmentId": {}}

            result = FcdUtils.write_json_records(records, str(filepath))

            assert result is True


class TestReadExistingJsonRecords:
    """Tests for read_existing_json_records function."""

    @pytest.mark.unit
    def test_read_nonexistent_file_returns_empty(self):
        """Reading non-existent file returns empty dict."""
        result = FcdUtils.read_existing_json_records("/nonexistent/file.json")
        assert result == {}

    @pytest.mark.unit
    def test_read_valid_file(self):
        """Test reading valid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"segmentId": {"123": {"geometry": "data"}}}
            json.dump(data, f)
            filepath = f.name

        try:
            result = FcdUtils.read_existing_json_records(filepath)
            assert result == data
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_read_empty_file_returns_empty(self):
        """Reading empty file returns empty dict."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            result = FcdUtils.read_existing_json_records(filepath)
            assert result == {}
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_read_invalid_json_returns_empty(self):
        """Invalid JSON returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            filepath = f.name

        try:
            result = FcdUtils.read_existing_json_records(filepath)
            assert result == {}
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_read_json_without_segment_id(self):
        """Test reading JSON without segmentId key returns empty."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"other_key": "value"}, f)
            filepath = f.name

        try:
            result = FcdUtils.read_existing_json_records(filepath)
            assert result == {}
        finally:
            Path(filepath).unlink()


# ---------------------------------------------------------------------------
# Helpers shared by geo-matching tests
# ---------------------------------------------------------------------------

# Helsinki-area coordinates used across tests.
# Segment A: east–west road at lat 60.17.
SEG_A_COORDS = [[24.94, 60.17], [24.95, 60.17]]
# Segment B: same road shifted ~3 m north (0.000027° lat ≈ 3 m) – within 5 m buffer.
SEG_B_COORDS = [[24.94, 60.170027], [24.95, 60.170027]]
# Segment C: same orientation but ~110 m away – should NOT match A.
SEG_C_COORDS = [[24.94, 60.171], [24.95, 60.171]]


def _make_linestring(coords: list) -> dict:
    return {"type": "LineString", "coordinates": coords}


def _make_removed_record(coords: list, history: list | None = None) -> dict:
    return {
        "current_geometry": _make_linestring(coords),
        "current_hash": "dummy_hash",
        "date_added": "2025-01-01T00:00:00",
        "history": history or [],
        "date_archived": "2025-06-01T00:00:00",
    }


class TestFindMatchingHistoricalSegments:
    """Tests for find_matching_historical_segments."""

    @pytest.mark.unit
    def test_empty_new_segments_returns_empty(self):
        """No new segments → empty result."""
        removed = {"old1": _make_removed_record(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments({}, removed)
        assert result == {}

    @pytest.mark.unit
    def test_empty_removed_segments_returns_empty(self):
        """No removed segments → empty result."""
        new = {"new1": _make_linestring(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments(new, {})
        assert result == {}

    @pytest.mark.unit
    def test_identical_geometry_matches(self):
        """Identical geometry with a different ID is recognised as a match."""
        new = {"new1": _make_linestring(SEG_A_COORDS)}
        removed = {"old1": _make_removed_record(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments(new, removed)
        assert result == {"new1": "old1"}

    @pytest.mark.unit
    def test_nearby_geometry_matches(self):
        """Geometry shifted ~3 m (within 5 m buffer) is matched."""
        new = {"new1": _make_linestring(SEG_B_COORDS)}
        removed = {"old1": _make_removed_record(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments(new, removed)
        assert result == {"new1": "old1"}

    @pytest.mark.unit
    def test_far_geometry_does_not_match(self):
        """Geometry ~110 m away (outside 5 m buffer) is not matched."""
        new = {"new1": _make_linestring(SEG_C_COORDS)}
        removed = {"old1": _make_removed_record(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments(new, removed)
        assert result == {}

    @pytest.mark.unit
    def test_best_match_selected(self):
        """When multiple removed segments exist, the closest one wins."""
        new = {"new1": _make_linestring(SEG_A_COORDS)}
        removed = {
            "close": _make_removed_record(SEG_B_COORDS),  # ~3 m away
            "far": _make_removed_record(SEG_C_COORDS),  # ~110 m away
        }
        result = FcdUtils.find_matching_historical_segments(new, removed)
        assert result == {"new1": "close"}

    @pytest.mark.unit
    def test_multiple_new_segments_each_matched(self):
        """Multiple new segments can each independently match a removed segment."""
        new = {
            "new1": _make_linestring(SEG_A_COORDS),
            "new2": _make_linestring(SEG_B_COORDS),
        }
        removed = {"old1": _make_removed_record(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments(new, removed)
        # Both new segments are close enough to old1
        assert "new1" in result and result["new1"] == "old1"
        assert "new2" in result and result["new2"] == "old1"

    @pytest.mark.unit
    def test_high_threshold_prevents_nearby_match(self):
        """A threshold of 1.0 prevents a near-but-not-identical match."""
        new = {"new1": _make_linestring(SEG_B_COORDS)}
        removed = {"old1": _make_removed_record(SEG_A_COORDS)}
        result = FcdUtils.find_matching_historical_segments(
            new, removed, match_threshold=1.0
        )
        assert result == {}

    @pytest.mark.unit
    def test_removed_record_missing_geometry_skipped(self):
        """Removed records without current_geometry are skipped gracefully."""
        new = {"new1": _make_linestring(SEG_A_COORDS)}
        removed = {"old1": {"current_hash": "x", "history": []}}  # no geometry
        result = FcdUtils.find_matching_historical_segments(new, removed)
        assert result == {}


class TestUpdateSegmentChangelogGeoInheritance:
    """Tests for the geo-inheritance behaviour in update_segment_changelog."""

    def _write_mapping(self, tmp_path: Path, segments: dict) -> str:
        data = {"segmentId": {}}
        for seg_id, coords in segments.items():
            data["segmentId"][seg_id] = {"geometry": _make_linestring(coords)}
        path = tmp_path / "mapping.json"
        path.write_text(json.dumps(data))
        return str(path)

    def _write_changelog(self, tmp_path: Path, changelog: dict) -> str:
        path = tmp_path / "changelog.json"
        path.write_text(json.dumps(changelog))
        return str(path)

    def _write_archive(self, tmp_path: Path, archive: dict) -> str:
        path = tmp_path / "archive.json"
        path.write_text(json.dumps(archive))
        return str(path)

    @pytest.mark.unit
    def test_history_inherited_when_segment_replaced_at_same_location(self, tmp_path):
        """A new segment at the same location as a removed segment inherits its history."""
        old_history = [
            {
                "date_archived": "2024-06-01T00:00:00",
                "geometry": _make_linestring(SEG_A_COORDS),
            }
        ]
        changelog = {
            "old1": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "old_hash",
                "date_added": "2025-01-01T00:00:00",
                "history": old_history,
            }
        }
        # Fresh mapping has a new segment replacing the old one (slightly shifted)
        mapping_path = self._write_mapping(tmp_path, {"new1": SEG_B_COORDS})
        changelog_path = self._write_changelog(tmp_path, changelog)
        archive_path = self._write_archive(tmp_path, {})

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path, changelog_path, str(archive_path), processing_date
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert "new1" in updated
        # History should contain the inherited entries + old segment's current geometry
        new1_history = updated["new1"]["history"]
        assert len(new1_history) == len(old_history) + 1  # old history + final geometry
        assert updated["new1"].get("geo_inherited_from") == "old1"

    @pytest.mark.unit
    def test_no_inheritance_when_new_segment_far_away(self, tmp_path):
        """A new segment far from the removed one does not inherit history."""
        changelog = {
            "old1": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "old_hash",
                "date_added": "2025-01-01T00:00:00",
                "history": [],
            }
        }
        # Fresh mapping has a new segment 110 m away – outside the 5 m buffer
        mapping_path = self._write_mapping(tmp_path, {"new1": SEG_C_COORDS})
        changelog_path = self._write_changelog(tmp_path, changelog)
        archive_path = self._write_archive(tmp_path, {})

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path, changelog_path, str(archive_path), processing_date
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert "new1" in updated
        assert updated["new1"].get("geo_inherited_from") is None
        assert updated["new1"]["history"] == []

    @pytest.mark.unit
    def test_no_inheritance_without_removed_segments(self, tmp_path):
        """geo_inherited_from is absent when no segments were removed."""
        changelog = {
            "existing": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "h",
                "date_added": "2025-01-01T00:00:00",
                "history": [],
            }
        }
        mapping_path = self._write_mapping(
            tmp_path, {"existing": SEG_A_COORDS, "new1": SEG_C_COORDS}
        )
        changelog_path = self._write_changelog(tmp_path, changelog)
        archive_path = self._write_archive(tmp_path, {})

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path, changelog_path, str(archive_path), processing_date
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert "new1" in updated
        assert updated["new1"].get("geo_inherited_from") is None


    @pytest.mark.unit
    def test_lookback_inherits_from_previous_cycle_archive(self, tmp_path):
        """New segment inherits from an archived segment from a recent past cycle."""
        archive = {
            "old1": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "old_hash",
                "date_added": "2025-01-01T00:00:00",
                "history": [],
                "date_archived": "2025-05-31T22:00:00",  # 2 h before processing
            }
        }
        # No existing changelog entries; no same-cycle removals.
        mapping_path = self._write_mapping(tmp_path, {"new1": SEG_B_COORDS})
        changelog_path = self._write_changelog(tmp_path, {})
        archive_path = self._write_archive(tmp_path, archive)

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path,
            changelog_path,
            str(archive_path),
            processing_date,
            lookback_hours=24,
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert updated["new1"].get("geo_inherited_from") == "old1"
        # Inherited history contains the old segment's final geometry entry.
        assert len(updated["new1"]["history"]) == 1

    @pytest.mark.unit
    def test_lookback_respects_window(self, tmp_path):
        """Archived segment outside the lookback window is not used."""
        archive = {
            "old1": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "old_hash",
                "date_added": "2025-01-01T00:00:00",
                "history": [],
                "date_archived": "2025-05-30T00:00:00",  # 48 h before processing
            }
        }
        mapping_path = self._write_mapping(tmp_path, {"new1": SEG_B_COORDS})
        changelog_path = self._write_changelog(tmp_path, {})
        archive_path = self._write_archive(tmp_path, archive)

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path,
            changelog_path,
            str(archive_path),
            processing_date,
            lookback_hours=24,
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert "geo_inherited_from" not in updated["new1"]

    @pytest.mark.unit
    def test_lookback_skips_already_inherited_source(self, tmp_path):
        """An archived source already used as geo_inherited_from is not re-used."""
        archive = {
            "old1": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "old_hash",
                "date_added": "2025-01-01T00:00:00",
                "history": [],
                "date_archived": "2025-05-31T22:00:00",
            }
        }
        # Existing changelog entry already inherits from old1 (previous cycle).
        changelog = {
            "prev_new": {
                "current_geometry": _make_linestring(SEG_C_COORDS),
                "current_hash": "prev_hash",
                "date_added": "2025-05-31T22:05:00",
                "history": [],
                "geo_inherited_from": "old1",
            }
        }
        mapping_path = self._write_mapping(
            tmp_path, {"prev_new": SEG_C_COORDS, "new1": SEG_B_COORDS}
        )
        changelog_path = self._write_changelog(tmp_path, changelog)
        archive_path = self._write_archive(tmp_path, archive)

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path,
            changelog_path,
            str(archive_path),
            processing_date,
            lookback_hours=24,
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert "geo_inherited_from" not in updated["new1"]

    @pytest.mark.unit
    def test_lookback_disabled_by_default(self, tmp_path):
        """Omitting lookback_hours preserves the original same-cycle-only behaviour."""
        archive = {
            "old1": {
                "current_geometry": _make_linestring(SEG_A_COORDS),
                "current_hash": "old_hash",
                "date_added": "2025-01-01T00:00:00",
                "history": [],
                "date_archived": "2025-05-31T23:30:00",  # recent, but lookback off
            }
        }
        mapping_path = self._write_mapping(tmp_path, {"new1": SEG_B_COORDS})
        changelog_path = self._write_changelog(tmp_path, {})
        archive_path = self._write_archive(tmp_path, archive)

        processing_date = datetime.fromisoformat("2025-06-01T00:00:00")
        FcdUtils.update_segment_changelog(
            mapping_path, changelog_path, str(archive_path), processing_date
        )

        updated = json.loads(Path(changelog_path).read_text())
        assert "geo_inherited_from" not in updated["new1"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
