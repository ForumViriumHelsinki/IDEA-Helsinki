"""Pytest fixtures for FCD Manager service tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mock_azure_manager():
    """Mock AzureBlobContainerManager for testing."""
    mock_manager = MagicMock()
    mock_manager.get_search_prefixes.return_value = ["folder1/"]
    mock_manager.get_blobs_by_prefix.return_value = []
    mock_manager.get_blobs_in_range.return_value = []
    mock_manager.download_blob_content.return_value = b'{"test": "data"}'
    return mock_manager


@pytest.fixture
def mock_fcd_influx_manager():
    """Mock FCDInfluxDBManager for testing."""
    mock_manager = MagicMock()
    mock_manager.check_connection.return_value = True
    mock_manager.get_last_update_timestamp.return_value = None
    mock_manager.write_fcd_model.return_value = True
    mock_manager.__enter__.return_value = mock_manager
    mock_manager.__exit__.return_value = None
    return mock_manager
