"""Pytest fixtures for IDEA Helsinki service tests."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture
def mock_idea_manager():
    """Mock IdeaHelsinkiManager for testing."""
    mock_manager = MagicMock()
    mock_manager.active_segments = {}
    mock_manager.last_cycle_time = None
    mock_manager.run_main_loop = AsyncMock()
    return mock_manager


@pytest.fixture
def mock_road_segment():
    """Mock IdeaHelsinkiRoadSegment for testing."""
    mock_segment = AsyncMock()
    mock_segment.segment_id = "test_segment_001"
    mock_segment.is_healthy = True
    mock_segment.last_validation_time = None
    return mock_segment
