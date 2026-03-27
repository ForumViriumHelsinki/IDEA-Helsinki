"""Repository factory for IDEA Helsinki data access.

Selects JSON or SQLite backend based on the USE_SQLITE_STORAGE feature flag.
"""

from __future__ import annotations

import logging
from pathlib import Path

from idea_shared.data.repositories import (
    DisturbanceRepository,
    ProfileRepository,
    SegmentRepository,
)
from idea_shared.feature_flags import FeatureFlag, get_feature_flags

logger = logging.getLogger(__name__)


def create_repositories(
    *,
    # JSON backend paths (used when USE_SQLITE_STORAGE=False)
    mapping_path: str | Path = "",
    changelog_path: str | Path = "",
    archive_path: str | Path = "",
    disturbance_path: str | Path = "",
    # SQLite backend path (used when USE_SQLITE_STORAGE=True)
    sqlite_db_path: str | Path = "",
) -> tuple[SegmentRepository, DisturbanceRepository, ProfileRepository | None]:
    """Create repositories using the backend selected by feature flags.

    When USE_SQLITE_STORAGE is enabled, returns SQLite-backed repositories
    sharing a single connection. Otherwise, returns JSON file-backed
    repositories (the legacy default).

    Args:
        mapping_path: Path to segments_mapping.json (JSON backend).
        changelog_path: Path to master_segment_history.json (JSON backend).
        archive_path: Path to archived_segment_history.json (JSON backend).
        disturbance_path: Path to traffic_disturbance_data.json (JSON backend).
        sqlite_db_path: Path to SQLite database file (SQLite backend).

    Returns:
        Tuple of (SegmentRepository, DisturbanceRepository, ProfileRepository | None).
        ProfileRepository is None when using the JSON backend.
    """
    flags = get_feature_flags()
    use_sqlite = flags.is_enabled(FeatureFlag.USE_SQLITE_STORAGE)

    if use_sqlite:
        from idea_shared.data.sqlite_backend import create_sqlite_repositories

        logger.info("Using SQLite storage backend (db_path=%s)", sqlite_db_path)
        segment_repo, disturbance_repo, profile_repo = create_sqlite_repositories(
            sqlite_db_path
        )
        return segment_repo, disturbance_repo, profile_repo

    from idea_shared.data.json_backend import (
        JsonDisturbanceRepository,
        JsonSegmentRepository,
    )

    logger.info("Using JSON file storage backend")
    segment_repo = JsonSegmentRepository(
        mapping_path=mapping_path,
        changelog_path=changelog_path,
        archive_path=archive_path,
    )
    disturbance_repo = JsonDisturbanceRepository(data_path=disturbance_path)
    return segment_repo, disturbance_repo, None
