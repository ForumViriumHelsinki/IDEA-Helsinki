"""Abstract repository interfaces for IDEA Helsinki data access.

These interfaces decouple business logic from storage backends (JSON files,
SQLite, etc.), enabling migration from GCS FUSE JSON files to SQLite without
changing service code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SegmentRepository(ABC):
    """Repository for FCD segment mapping and history data.

    Manages three conceptual data stores:
    - **segments**: Current segment geometries (segments_mapping.json equivalent)
    - **changelog**: Master segment history tracking geometry changes over time
    - **archive**: Removed segments with their final geometry state
    """

    @abstractmethod
    def get_segments(self) -> dict:
        """Get all current segment mappings.

        Returns:
            Dict in format ``{"segmentId": {id: {"geometry": ...}}}``,
            or empty dict if no data available.
        """

    @abstractmethod
    def save_segments(self, segments: dict) -> bool:
        """Save segment mappings.

        Args:
            segments: Dict in format ``{"segmentId": {id: {"geometry": ...}}}``

        Returns:
            True if successful, False otherwise.
        """

    @abstractmethod
    def get_changelog(self) -> dict:
        """Get the master segment history changelog.

        Returns:
            Dict mapping segment_id to history records, or empty dict.
        """

    @abstractmethod
    def save_changelog(self, changelog: dict) -> None:
        """Save the master segment history changelog.

        Args:
            changelog: Dict mapping segment_id to history records.

        Raises:
            OSError: If the write operation fails.
        """

    @abstractmethod
    def get_archive(self) -> dict:
        """Get the archived (removed) segment history.

        Returns:
            Dict mapping segment_id to archived records, or empty dict.
        """

    @abstractmethod
    def save_archive(self, archive: dict) -> None:
        """Save the archived segment history.

        Args:
            archive: Dict mapping segment_id to archived records.

        Raises:
            OSError: If the write operation fails.
        """


class DisturbanceRepository(ABC):
    """Repository for traffic disturbance intersection data.

    Manages the intersection results between FCD segments and traffic
    disturbances from Helsinki WFS services.
    """

    @abstractmethod
    def get_disturbances(self) -> dict:
        """Get current traffic disturbance intersection data.

        Returns:
            Dict in format ``{"segmentId": {id: {"geometry": ..., "detailedCollisions": [...]}}}``,
            or empty dict if no data available.
        """

    @abstractmethod
    def save_disturbances(self, data: dict) -> bool:
        """Save traffic disturbance intersection data.

        Args:
            data: Dict in format ``{"segmentId": {id: {"geometry": ..., "detailedCollisions": [...]}}}``

        Returns:
            True if successful, False otherwise.
        """
