"""Shared pytest fixtures for IDEA Helsinki tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_influxdb_client():
    """Mock InfluxDB client for testing database operations."""
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "pass"}
    mock_client.ping.return_value = True
    mock_client.close = MagicMock()
    return mock_client


@pytest.fixture
def mock_azure_blob_client():
    """Mock Azure Blob Storage client for testing blob operations."""
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_blob.name = "test_blob.json"
    mock_blob.last_modified = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    mock_client.list_blobs.return_value = [mock_blob]
    mock_client.get_blob_client.return_value = mock_blob
    return mock_client


@pytest.fixture
def sample_fcd_segment():
    """Sample FCD segment data for testing."""
    return {
        "segment_id": "1195756141337706497",
        "observations": [
            {
                "timestamp": "2024-01-15T10:00:00Z",
                "speed": 45.5,
                "confidence": 0.95,
            },
            {
                "timestamp": "2024-01-15T10:05:00Z",
                "speed": 48.2,
                "confidence": 0.92,
            },
        ],
        "geometry": {
            "type": "LineString",
            "coordinates": [[24.9384, 60.1699], [24.9404, 60.1719]],
        },
    }


@pytest.fixture
def sample_fcd_segments():
    """Sample collection of FCD segments."""
    return {
        "1195756141337706497": {
            "segment_id": "1195756141337706497",
            "observations": [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "speed": 45.5,
                    "confidence": 0.95,
                }
            ],
            "geometry": {
                "type": "LineString",
                "coordinates": [[24.9384, 60.1699], [24.9404, 60.1719]],
            },
        },
        "1195756141314637825": {
            "segment_id": "1195756141314637825",
            "observations": [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "speed": 35.2,
                    "confidence": 0.88,
                }
            ],
            "geometry": {
                "type": "LineString",
                "coordinates": [[24.9404, 60.1719], [24.9424, 60.1739]],
            },
        },
    }


@pytest.fixture
def sample_traffic_disturbance():
    """Sample traffic disturbance for testing."""
    return {
        "id": "TEST-2024-001",
        "name": "Road maintenance on Mannerheimintie",
        "start_time": "2024-01-15T00:00:00Z",
        "end_time": "2024-01-20T23:59:59Z",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [24.9384, 60.1699],
                    [24.9424, 60.1699],
                    [24.9424, 60.1739],
                    [24.9384, 60.1739],
                    [24.9384, 60.1699],
                ]
            ],
        },
        "severity": "moderate",
    }


@pytest.fixture
def sample_wfs_response():
    """Sample WFS API response for testing."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "TEST-2024-001",
                "properties": {
                    "name": "Road maintenance",
                    "startTime": "2024-01-15T00:00:00Z",
                    "endTime": "2024-01-20T23:59:59Z",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [24.9384, 60.1699],
                            [24.9424, 60.1699],
                            [24.9424, 60.1739],
                            [24.9384, 60.1739],
                            [24.9384, 60.1699],
                        ]
                    ],
                },
            }
        ],
    }


@pytest.fixture
def mock_wfs_client():
    """Mock WFS client for testing WFS operations."""
    mock_client = MagicMock()
    mock_client.request_wfs_features_from_list.return_value = [
        {
            "id": "TEST-2024-001",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [24.9384, 60.1699],
                        [24.9424, 60.1699],
                        [24.9424, 60.1739],
                        [24.9384, 60.1739],
                        [24.9384, 60.1699],
                    ]
                ],
            },
        }
    ]
    return mock_client


@pytest.fixture
async def mock_async_influxdb_client():
    """Mock async InfluxDB client for async testing."""
    mock_client = AsyncMock()
    mock_client.health = AsyncMock(return_value={"status": "pass"})
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.query_api = AsyncMock()
    mock_client.write_api = AsyncMock()
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def freeze_time():
    """Fixture to freeze time for testing time-dependent code."""
    from freezegun import freeze_time as _freeze_time

    return _freeze_time


@pytest.fixture
def fixed_datetime():
    """Fixed datetime for consistent testing."""
    return datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
