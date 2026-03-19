"""JSON file backend for IDEA Helsinki repositories.

Wraps existing file I/O functions (read_json_with_retry, atomic_write_json)
behind the repository interfaces. This is the current production backend;
SQLite will be added as an alternative in Phase 2.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from idea_shared.data.repositories import DisturbanceRepository, SegmentRepository
from idea_shared.threading.file_locks import atomic_write_json, read_json_with_retry

logger = logging.getLogger(__name__)


class JsonSegmentRepository(SegmentRepository):
    """JSON file-backed segment repository.

    Manages three JSON files:
    - mapping_path: segments_mapping.json (current geometries)
    - changelog_path: master_segment_history.json (geometry change tracking)
    - archive_path: archived_segment_history.json (removed segments)
    """

    def __init__(
        self,
        mapping_path: str | Path,
        changelog_path: str | Path,
        archive_path: str | Path,
    ):
        self._mapping_path = Path(mapping_path)
        self._changelog_path = Path(changelog_path)
        self._archive_path = Path(archive_path)

    def get_segments(self) -> dict:
        """Read segment mappings from JSON file.

        Uses read_json_with_retry for ESTALE resilience on GCS FUSE.
        """
        data = read_json_with_retry(self._mapping_path)
        if data is None:
            return {}
        if not isinstance(data, dict):
            logger.warning(
                f"Segment mapping file '{self._mapping_path}' did not contain a dict. "
                f"Returning empty."
            )
            return {}
        segment_ids = data.get("segmentId")
        if not isinstance(segment_ids, dict):
            logger.warning(
                f"Segment mapping file '{self._mapping_path}' missing 'segmentId' dict. "
                f"Returning empty."
            )
            return {}
        logger.info(
            f"Read {len(segment_ids)} segment records from '{self._mapping_path}'."
        )
        return data

    def save_segments(self, segments: dict) -> bool:
        """Write segment mappings to JSON file atomically."""
        segment_ids = segments.get("segmentId")
        if not isinstance(segment_ids, dict):
            logger.error("Segment data missing 'segmentId' dict, cannot save.")
            return False
        try:
            atomic_write_json(self._mapping_path, segments)
            logger.info(
                f"Successfully wrote {len(segment_ids)} segments "
                f"to '{self._mapping_path}'."
            )
            return True
        except OSError as e:
            logger.error(f"Failed to write segments to '{self._mapping_path}': {e}")
            return False

    def get_changelog(self) -> dict:
        """Read master segment history from JSON file.

        Includes corruption recovery: if the file is corrupted (truncated JSON
        from pod termination), backs up the corrupted file and returns empty dict.
        """
        if not self._changelog_path.exists():
            return {}
        try:
            with open(self._changelog_path, encoding="utf-8") as f:
                changelog = json.load(f)
            if not isinstance(changelog, dict):
                logger.warning(
                    f"Changelog file '{self._changelog_path}' is not a dict. "
                    f"Returning empty."
                )
                return {}
            return changelog
        except json.JSONDecodeError as e:
            logger.warning(f"Changelog file corrupted: {e}. Attempting recovery...")
            backup_suffix = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            backup_path = self._changelog_path.with_suffix(
                f".{backup_suffix}.corrupted"
            )
            try:
                shutil.copy2(self._changelog_path, backup_path)
                logger.info(f"Corrupted file backed up to: {backup_path}")
            except OSError as backup_error:
                logger.warning(f"Could not backup corrupted file: {backup_error}")
            logger.warning(
                "Starting with empty changelog. "
                "Historical geometry changes will be lost."
            )
            return {}
        except OSError as e:
            logger.error(f"Could not load changelog file '{self._changelog_path}': {e}")
            return {}

    def save_changelog(self, changelog: dict) -> None:
        """Write master segment history to JSON file atomically."""
        atomic_write_json(self._changelog_path, changelog)
        logger.info("Segment changelog file has been updated.")

    def get_archive(self) -> dict:
        """Read archived segment history from JSON file."""
        if not self._archive_path.exists():
            return {}
        try:
            with open(self._archive_path, encoding="utf-8") as f:
                archive = json.load(f)
            if not isinstance(archive, dict):
                logger.warning(
                    f"Archive file '{self._archive_path}' is not a dict. "
                    f"Returning empty."
                )
                return {}
            return archive
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                f"Could not load archive file '{self._archive_path}': {e}. "
                f"A new one may be created."
            )
            return {}

    def save_archive(self, archive: dict) -> None:
        """Write archived segment history to JSON file atomically."""
        atomic_write_json(self._archive_path, archive)
        logger.info("Segment archive file has been updated.")


class JsonDisturbanceRepository(DisturbanceRepository):
    """JSON file-backed disturbance repository.

    Manages the traffic_disturbance_data.json file containing intersection
    results between FCD segments and traffic disturbances.
    """

    def __init__(self, data_path: str | Path):
        self._data_path = Path(data_path)

    def get_disturbances(self) -> dict:
        """Read traffic disturbance data from JSON file.

        Uses read_json_with_retry for ESTALE resilience on GCS FUSE.
        """
        data = read_json_with_retry(self._data_path)
        if data is None:
            logger.error(f"Could not load disturbance data from '{self._data_path}'")
            return {}
        if not isinstance(data, dict):
            logger.error(f"Disturbance data from '{self._data_path}' is not a dict")
            return {}
        return data

    def save_disturbances(self, data: dict) -> bool:
        """Write traffic disturbance data to JSON file atomically."""
        segment_ids = data.get("segmentId")
        if not isinstance(segment_ids, dict):
            logger.error("Disturbance data missing 'segmentId' dict, cannot save.")
            return False
        try:
            atomic_write_json(self._data_path, data)
            logger.info(
                f"Successfully wrote {len(segment_ids)} disturbance records "
                f"to '{self._data_path}'."
            )
            return True
        except OSError as e:
            logger.error(
                f"Failed to write disturbance data to '{self._data_path}': {e}"
            )
            return False
