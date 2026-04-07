"""Tests for JSON and GeoJSON export functions."""

from __future__ import annotations

import json

import pytest

from idea_shared.data.json_export import (
    export_disturbances_geojson,
    export_disturbances_json,
    export_segments_geojson,
    export_segments_json,
)
from idea_shared.data.repositories import DisturbanceRepository, SegmentRepository

# ---------------------------------------------------------------------------
# Concrete test implementations of the abstract repositories
# ---------------------------------------------------------------------------


class StubSegmentRepository(SegmentRepository):
    """In-memory segment repository for testing."""

    def __init__(self, segments: dict | None = None):
        self._segments = segments if segments is not None else {}

    def get_segments(self) -> dict:
        return self._segments

    def save_segments(self, segments: dict) -> bool:
        self._segments = segments
        return True

    def get_changelog(self) -> dict:
        return {}

    def save_changelog(self, changelog: dict) -> None:
        pass

    def get_archive(self) -> dict:
        return {}

    def save_archive(self, archive: dict) -> None:
        pass


class StubDisturbanceRepository(DisturbanceRepository):
    """In-memory disturbance repository for testing."""

    def __init__(self, disturbances: dict | None = None):
        self._disturbances = disturbances if disturbances is not None else {}

    def get_disturbances(self) -> dict:
        return self._disturbances

    def save_disturbances(self, data: dict) -> bool:
        self._disturbances = data
        return True


# ---------------------------------------------------------------------------
# Tests: export_segments_json
# ---------------------------------------------------------------------------


class TestExportSegmentsJson:
    """Tests for export_segments_json."""

    @pytest.mark.unit
    def test_exports_segments_matching_input(self, tmp_path, sample_segments):
        """Exported JSON matches the repository data exactly."""
        repo = StubSegmentRepository(sample_segments)
        out = tmp_path / "segments.json"

        result = export_segments_json(repo, out)

        assert result is True
        with open(out) as f:
            written = json.load(f)
        assert written == sample_segments

    @pytest.mark.unit
    def test_exports_empty_segments(self, tmp_path):
        """Empty dict is written successfully."""
        repo = StubSegmentRepository({})
        out = tmp_path / "segments.json"

        result = export_segments_json(repo, out)

        assert result is True
        with open(out) as f:
            written = json.load(f)
        assert written == {}

    @pytest.mark.unit
    def test_returns_false_on_write_error(self):
        """Returns False when writing to a non-existent directory fails."""
        repo = StubSegmentRepository({"segmentId": {}})
        # atomic_write_json creates parent dirs, so use a path blocked by a file
        # occupying the parent name to trigger an error
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile() as f:
            # Try to write inside a file (not a directory)
            bad_path = Path(f.name) / "subdir" / "segments.json"
            result = export_segments_json(repo, bad_path)
            assert result is False


# ---------------------------------------------------------------------------
# Tests: export_disturbances_json
# ---------------------------------------------------------------------------


class TestExportDisturbancesJson:
    """Tests for export_disturbances_json."""

    @pytest.mark.unit
    def test_exports_disturbances_matching_input(self, tmp_path, sample_disturbances):
        """Exported JSON matches the repository data exactly."""
        repo = StubDisturbanceRepository(sample_disturbances)
        out = tmp_path / "disturbances.json"

        result = export_disturbances_json(repo, out)

        assert result is True
        with open(out) as f:
            written = json.load(f)
        assert written == sample_disturbances

    @pytest.mark.unit
    def test_exports_empty_disturbances(self, tmp_path):
        """Empty dict is written successfully."""
        repo = StubDisturbanceRepository({})
        out = tmp_path / "disturbances.json"

        result = export_disturbances_json(repo, out)

        assert result is True
        with open(out) as f:
            written = json.load(f)
        assert written == {}


# ---------------------------------------------------------------------------
# Tests: export_segments_geojson
# ---------------------------------------------------------------------------


class TestExportSegmentsGeoJson:
    """Tests for export_segments_geojson."""

    @pytest.mark.unit
    def test_produces_valid_feature_collection(self, tmp_path, sample_segments):
        """Output is a valid GeoJSON FeatureCollection."""
        repo = StubSegmentRepository(sample_segments)
        out = tmp_path / "segments.geojson"

        result = export_segments_geojson(repo, out)

        assert result is True
        with open(out) as f:
            geojson = json.load(f)
        assert geojson["type"] == "FeatureCollection"
        assert isinstance(geojson["features"], list)
        assert len(geojson["features"]) == 2

    @pytest.mark.unit
    def test_no_crs_member(self, tmp_path, sample_segments):
        """RFC 7946 Section 4: no crs member in output."""
        repo = StubSegmentRepository(sample_segments)
        out = tmp_path / "segments.geojson"

        export_segments_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        assert "crs" not in geojson

    @pytest.mark.unit
    def test_feature_structure(self, tmp_path, sample_segments):
        """Each feature has correct type, geometry, and properties."""
        repo = StubSegmentRepository(sample_segments)
        out = tmp_path / "segments.geojson"

        export_segments_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        for feature in geojson["features"]:
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
            assert "segment_id" in feature["properties"]

    @pytest.mark.unit
    def test_geometry_preserved(self, tmp_path, sample_segments):
        """Segment geometry is preserved in GeoJSON output."""
        repo = StubSegmentRepository(sample_segments)
        out = tmp_path / "segments.geojson"

        export_segments_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        seg_ids = {f["properties"]["segment_id"] for f in geojson["features"]}
        assert seg_ids == {"seg_001", "seg_002"}

        for feature in geojson["features"]:
            seg_id = feature["properties"]["segment_id"]
            expected_geom = sample_segments["segmentId"][seg_id]["geometry"]
            assert feature["geometry"] == expected_geom

    @pytest.mark.unit
    def test_empty_segments_produce_empty_features(self, tmp_path):
        """Empty segment data produces FeatureCollection with no features."""
        repo = StubSegmentRepository({})
        out = tmp_path / "segments.geojson"

        export_segments_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"] == []

    @pytest.mark.unit
    def test_extra_properties_included(self, tmp_path):
        """Non-geometry fields are included in properties."""
        segments = {
            "segmentId": {
                "seg_100": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[24.0, 60.0], [24.1, 60.1]],
                    },
                    "speed": 45.2,
                    "confidence": 0.95,
                }
            }
        }
        repo = StubSegmentRepository(segments)
        out = tmp_path / "segments.geojson"

        export_segments_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        props = geojson["features"][0]["properties"]
        assert props["segment_id"] == "seg_100"
        assert props["speed"] == 45.2
        assert props["confidence"] == 0.95


# ---------------------------------------------------------------------------
# Tests: export_disturbances_geojson
# ---------------------------------------------------------------------------


class TestExportDisturbancesGeoJson:
    """Tests for export_disturbances_geojson."""

    @pytest.mark.unit
    def test_produces_valid_feature_collection(self, tmp_path, sample_disturbances):
        """Output is a valid GeoJSON FeatureCollection."""
        repo = StubDisturbanceRepository(sample_disturbances)
        out = tmp_path / "disturbances.geojson"

        result = export_disturbances_geojson(repo, out)

        assert result is True
        with open(out) as f:
            geojson = json.load(f)
        assert geojson["type"] == "FeatureCollection"
        assert isinstance(geojson["features"], list)
        assert len(geojson["features"]) == 1

    @pytest.mark.unit
    def test_no_crs_member(self, tmp_path, sample_disturbances):
        """RFC 7946 Section 4: no crs member in output."""
        repo = StubDisturbanceRepository(sample_disturbances)
        out = tmp_path / "disturbances.geojson"

        export_disturbances_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        assert "crs" not in geojson

    @pytest.mark.unit
    def test_feature_includes_detailed_collisions(self, tmp_path, sample_disturbances):
        """detailedCollisions are included in feature properties."""
        repo = StubDisturbanceRepository(sample_disturbances)
        out = tmp_path / "disturbances.geojson"

        export_disturbances_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        feature = geojson["features"][0]
        assert feature["type"] == "Feature"
        assert feature["properties"]["segment_id"] == "seg_001"
        assert "detailedCollisions" in feature["properties"]
        assert len(feature["properties"]["detailedCollisions"]) == 1

    @pytest.mark.unit
    def test_geometry_preserved(self, tmp_path, sample_disturbances):
        """Disturbance geometry is preserved in GeoJSON output."""
        repo = StubDisturbanceRepository(sample_disturbances)
        out = tmp_path / "disturbances.geojson"

        export_disturbances_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        feature = geojson["features"][0]
        expected_geom = sample_disturbances["segmentId"]["seg_001"]["geometry"]
        assert feature["geometry"] == expected_geom

    @pytest.mark.unit
    def test_empty_disturbances_produce_empty_features(self, tmp_path):
        """Empty disturbance data produces FeatureCollection with no features."""
        repo = StubDisturbanceRepository({})
        out = tmp_path / "disturbances.geojson"

        export_disturbances_geojson(repo, out)

        with open(out) as f:
            geojson = json.load(f)
        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"] == []

    @pytest.mark.unit
    def test_returns_false_on_write_error(self):
        """Returns False when writing to an invalid path."""
        repo = StubDisturbanceRepository({"segmentId": {}})
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile() as f:
            bad_path = Path(f.name) / "subdir" / "disturbances.geojson"
            result = export_disturbances_geojson(repo, bad_path)
            assert result is False
