"""Shared test fixtures for data backend tests."""

import pytest


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
