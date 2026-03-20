"""Tests for JSON backend repository implementations."""

import json

import pytest

from idea_shared.data.json_backend import (
    JsonDisturbanceRepository,
    JsonSegmentRepository,
)


@pytest.fixture
def sample_segments():
    """Sample segment mapping data."""
    return {
        "segmentId": {
            "seg_001": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[24.9384, 60.1699], [24.9404, 60.1719]],
                }
            },
            "seg_002": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[24.9404, 60.1719], [24.9424, 60.1739]],
                }
            },
        }
    }


@pytest.fixture
def sample_changelog():
    """Sample changelog data."""
    return {
        "seg_001": {
            "current_geometry": {
                "type": "LineString",
                "coordinates": [[24.9384, 60.1699], [24.9404, 60.1719]],
            },
            "current_hash": "abc123",
            "date_added": "2024-01-01T00:00:00",
            "history": [],
        }
    }


@pytest.fixture
def sample_disturbances():
    """Sample disturbance data."""
    return {
        "segmentId": {
            "seg_001": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[24.9384, 60.1699], [24.9404, 60.1719]],
                },
                "detailedCollisions": [
                    {
                        "properties": {
                            "traffic_disturbance_type": "Kaivuilmoitus_alue",
                            "traffic_disturbance_id": "TEST-001",
                            "application_id": "APP-001",
                            "star_date": "2024-01-15",
                            "end_date": "2024-01-20",
                        }
                    }
                ],
            }
        }
    }


@pytest.fixture
def segment_repo(tmp_path):
    """Create a JsonSegmentRepository with temporary file paths."""
    return JsonSegmentRepository(
        mapping_path=tmp_path / "segments_mapping.json",
        changelog_path=tmp_path / "master_segment_history.json",
        archive_path=tmp_path / "archived_segment_history.json",
    )


@pytest.fixture
def disturbance_repo(tmp_path):
    """Create a JsonDisturbanceRepository with temporary file path."""
    return JsonDisturbanceRepository(
        data_path=tmp_path / "traffic_disturbance_data.json",
    )


class TestJsonSegmentRepository:
    """Tests for JsonSegmentRepository."""

    @pytest.mark.unit
    def test_get_segments_returns_empty_when_file_missing(self, segment_repo):
        """get_segments returns empty dict when file doesn't exist."""
        result = segment_repo.get_segments()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_segments(self, segment_repo, sample_segments):
        """save_segments writes data that get_segments can read back."""
        assert segment_repo.save_segments(sample_segments) is True
        result = segment_repo.get_segments()
        assert result == sample_segments
        assert len(result["segmentId"]) == 2

    @pytest.mark.unit
    def test_save_segments_rejects_invalid_data(self, segment_repo):
        """save_segments returns False for data without segmentId dict."""
        assert segment_repo.save_segments({}) is False
        assert segment_repo.save_segments({"segmentId": "not_a_dict"}) is False

    @pytest.mark.unit
    def test_get_segments_handles_malformed_json(self, segment_repo, tmp_path):
        """get_segments returns empty dict for malformed data."""
        mapping_path = tmp_path / "segments_mapping.json"
        mapping_path.write_text('{"not_segment_id": {}}')
        result = segment_repo.get_segments()
        assert result == {}

    @pytest.mark.unit
    def test_get_changelog_returns_empty_when_missing(self, segment_repo):
        """get_changelog returns empty dict when file doesn't exist."""
        result = segment_repo.get_changelog()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_changelog(self, segment_repo, sample_changelog):
        """save_changelog writes data that get_changelog can read back."""
        segment_repo.save_changelog(sample_changelog)
        result = segment_repo.get_changelog()
        assert result == sample_changelog

    @pytest.mark.unit
    def test_get_changelog_recovers_from_corruption(self, segment_repo, tmp_path):
        """get_changelog returns empty dict and backs up corrupted file."""
        changelog_path = tmp_path / "master_segment_history.json"
        changelog_path.write_text("{corrupted json data")
        result = segment_repo.get_changelog()
        assert result == {}
        # Verify backup was created
        backup_files = list(tmp_path.glob("*.corrupted"))
        assert len(backup_files) == 1

    @pytest.mark.unit
    def test_get_archive_returns_empty_when_missing(self, segment_repo):
        """get_archive returns empty dict when file doesn't exist."""
        result = segment_repo.get_archive()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_archive(self, segment_repo):
        """save_archive writes data that get_archive can read back."""
        archive = {"seg_old": {"date_archived": "2024-01-01T00:00:00"}}
        segment_repo.save_archive(archive)
        result = segment_repo.get_archive()
        assert result == archive

    @pytest.mark.unit
    def test_get_archive_handles_corrupted_file(self, segment_repo, tmp_path):
        """get_archive returns empty dict for corrupted file."""
        archive_path = tmp_path / "archived_segment_history.json"
        archive_path.write_text("not valid json")
        result = segment_repo.get_archive()
        assert result == {}

    @pytest.mark.unit
    def test_save_segments_creates_parent_directory(self, tmp_path, sample_segments):
        """save_segments creates parent directories if needed."""
        repo = JsonSegmentRepository(
            mapping_path=tmp_path / "subdir" / "segments.json",
            changelog_path=tmp_path / "changelog.json",
            archive_path=tmp_path / "archive.json",
        )
        assert repo.save_segments(sample_segments) is True
        assert (tmp_path / "subdir" / "segments.json").exists()


class TestJsonDisturbanceRepository:
    """Tests for JsonDisturbanceRepository."""

    @pytest.mark.unit
    def test_get_disturbances_returns_empty_when_missing(self, disturbance_repo):
        """get_disturbances returns empty dict when file doesn't exist."""
        result = disturbance_repo.get_disturbances()
        assert result == {}

    @pytest.mark.unit
    def test_save_and_get_disturbances(self, disturbance_repo, sample_disturbances):
        """save_disturbances writes data that get_disturbances can read back."""
        assert disturbance_repo.save_disturbances(sample_disturbances) is True
        result = disturbance_repo.get_disturbances()
        assert result == sample_disturbances

    @pytest.mark.unit
    def test_save_disturbances_rejects_invalid_data(self, disturbance_repo):
        """save_disturbances returns False for data without segmentId dict."""
        assert disturbance_repo.save_disturbances({}) is False
        assert disturbance_repo.save_disturbances({"segmentId": "not_dict"}) is False

    @pytest.mark.unit
    def test_get_disturbances_handles_non_dict(self, disturbance_repo, tmp_path):
        """get_disturbances returns empty dict for non-dict JSON."""
        data_path = tmp_path / "traffic_disturbance_data.json"
        data_path.write_text(json.dumps([1, 2, 3]))
        result = disturbance_repo.get_disturbances()
        assert result == {}

    @pytest.mark.unit
    def test_save_disturbances_creates_parent_directory(
        self, tmp_path, sample_disturbances
    ):
        """save_disturbances creates parent directories if needed."""
        repo = JsonDisturbanceRepository(
            data_path=tmp_path / "subdir" / "disturbances.json",
        )
        assert repo.save_disturbances(sample_disturbances) is True
        assert (tmp_path / "subdir" / "disturbances.json").exists()
