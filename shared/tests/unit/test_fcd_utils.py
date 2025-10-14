"""Unit tests for FcdUtils module."""

import json
import tempfile
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
        result = FcdUtils.get_fcd_geometries(None)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
