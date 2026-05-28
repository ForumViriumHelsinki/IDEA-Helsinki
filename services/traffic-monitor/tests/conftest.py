"""Pytest fixtures for Traffic Monitor service tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_intersection_detector():
    """Mock IntersectionDetector for testing."""
    mock_detector = MagicMock()
    mock_detector.check_if_file_path_exists.return_value = True
    mock_detector.load_wfs_geojson.return_value = MagicMock()
    mock_detector.load_fcd_segment_data.return_value = MagicMock()
    mock_detector.find_intersecting_features.return_value = []
    mock_detector.process_intersections_to_extended_model.return_value = []
    mock_detector.write_json_records.return_value = True
    return mock_detector


@pytest.fixture
def mock_wfs_allu_client():
    """Mock HelsinkiAlluWFSClient for testing."""
    mock_client = MagicMock()
    mock_client.request_wfs_features_from_list.return_value = []
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    return mock_client
