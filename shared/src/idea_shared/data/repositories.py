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


class ProfileRepository(ABC):
    """Repository for disk-backed segment profile data.

    Stores serialized segment profiles (e.g., Parquet-encoded DataFrames)
    as BLOBs with expiration tracking for automatic cleanup.
    """

    @abstractmethod
    def get_profile(self, segment_id: str) -> bytes | None:
        """Get serialized profile data for a segment.

        Args:
            segment_id: The segment identifier.

        Returns:
            Serialized profile bytes, or None if not found.

        """

    @abstractmethod
    def save_profile(
        self,
        segment_id: str,
        profile_data: bytes,
        computed_at: str,
        expires_at: str,
    ) -> None:
        """Save serialized profile data for a segment.

        Uses UPSERT semantics — inserts or replaces existing profile.

        Args:
            segment_id: The segment identifier.
            profile_data: Serialized profile bytes.
            computed_at: ISO 8601 timestamp of when the profile was computed.
            expires_at: ISO 8601 timestamp of when the profile expires.

        """

    @abstractmethod
    def delete_profile(self, segment_id: str) -> None:
        """Delete profile data for a segment.

        Args:
            segment_id: The segment identifier.

        """

    @abstractmethod
    def get_all_profile_ids(self) -> list[str]:
        """Get all segment IDs that have stored profiles.

        Returns:
            List of segment IDs with stored profiles.

        """

    @abstractmethod
    def delete_expired_profiles(self) -> int:
        """Delete all profiles whose expires_at is in the past.

        Returns:
            Number of profiles deleted.

        """
