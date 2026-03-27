"""Tests for repository factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from idea_shared.data.factory import create_repositories
from idea_shared.data.json_backend import (
    JsonDisturbanceRepository,
    JsonSegmentRepository,
)
from idea_shared.data.sqlite_backend import (
    SqliteDisturbanceRepository,
    SqliteProfileRepository,
    SqliteSegmentRepository,
)
from idea_shared.feature_flags import FeatureFlag


@pytest.mark.unit
def test_create_repositories_returns_sqlite_when_flag_enabled(tmp_path):
    """When USE_SQLITE_STORAGE is enabled, SQLite repositories are returned."""
    mock_flags = MagicMock()
    mock_flags.is_enabled.return_value = True

    with patch("idea_shared.data.factory.get_feature_flags", return_value=mock_flags):
        segment_repo, disturbance_repo, profile_repo = create_repositories(
            sqlite_db_path=tmp_path / "test.db",
        )

    mock_flags.is_enabled.assert_called_once_with(FeatureFlag.USE_SQLITE_STORAGE)
    assert isinstance(segment_repo, SqliteSegmentRepository)
    assert isinstance(disturbance_repo, SqliteDisturbanceRepository)
    assert isinstance(profile_repo, SqliteProfileRepository)


@pytest.mark.unit
def test_create_repositories_returns_json_when_flag_disabled(tmp_path):
    """When USE_SQLITE_STORAGE is disabled, JSON repositories are returned."""
    mock_flags = MagicMock()
    mock_flags.is_enabled.return_value = False

    with patch("idea_shared.data.factory.get_feature_flags", return_value=mock_flags):
        segment_repo, disturbance_repo, profile_repo = create_repositories(
            mapping_path=tmp_path / "mapping.json",
            changelog_path=tmp_path / "changelog.json",
            archive_path=tmp_path / "archive.json",
            disturbance_path=tmp_path / "disturbance.json",
        )

    mock_flags.is_enabled.assert_called_once_with(FeatureFlag.USE_SQLITE_STORAGE)
    assert isinstance(segment_repo, JsonSegmentRepository)
    assert isinstance(disturbance_repo, JsonDisturbanceRepository)
    assert profile_repo is None
