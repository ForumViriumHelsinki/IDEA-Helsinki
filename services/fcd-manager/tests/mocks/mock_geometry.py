"""Mock Segment Geometry Store for testing."""

import hashlib
import json
from pathlib import Path


class MockSegmentGeometryStore:
    """
    Mock segment geometry store for deterministic testing.

    Features:
    - Dictionary-based segment lookups
    - Stable SHA-256 hashing
    - Support for geometry version changes
    - Thread-safe (immutable after initialization)
    """

    def __init__(self, fixture_file: Path):
        """
        Initialize mock geometry store.

        Args:
            fixture_file: Path to geometry mapping JSON fixture
        """
        self.fixture_file = fixture_file
        self._geometries: dict[str, dict] = {}
        self._load_fixtures()

    def _load_fixtures(self):
        """Load geometry mappings from fixture file."""
        with open(self.fixture_file) as f:
            self._geometries = json.load(f)

    def _canonicalize_wkt(self, wkt: str) -> str:
        """
        Canonicalize WKT for stable hashing.

        Args:
            wkt: Well-Known Text geometry

        Returns:
            Canonicalized WKT (trimmed, lowercase, no whitespace variance)
        """
        return wkt.strip().lower().replace("  ", " ")

    def _compute_sha256(self, wkt: str) -> str:
        """
        Compute SHA-256 hash of geometry.

        Args:
            wkt: Well-Known Text geometry

        Returns:
            SHA-256 hash hex string
        """
        canonical_wkt = self._canonicalize_wkt(wkt)
        return hashlib.sha256(canonical_wkt.encode()).hexdigest()[:12]

    def get_geometry(self, segment_id: str, version: str | None = None) -> dict | None:
        """
        Get geometry for segment ID.

        Args:
            segment_id: Segment identifier
            version: Optional version suffix (e.g., "v1", "v2")

        Returns:
            Geometry dict with {wkt, version, sha256} or None if not found
        """
        # Support versioned lookups (e.g., S3_v1, S3_v2)
        key = f"{segment_id}_{version}" if version else segment_id

        if key in self._geometries:
            return self._geometries[key]
        elif segment_id in self._geometries:
            return self._geometries[segment_id]

        return None

    def has_geometry(self, segment_id: str) -> bool:
        """
        Check if geometry exists for segment.

        Args:
            segment_id: Segment identifier

        Returns:
            True if geometry exists, False otherwise
        """
        return segment_id in self._geometries

    def get_sha256(self, segment_id: str, version: str | None = None) -> str | None:
        """
        Get SHA-256 hash for segment geometry.

        Args:
            segment_id: Segment identifier
            version: Optional version suffix

        Returns:
            SHA-256 hash or None if not found
        """
        geom = self.get_geometry(segment_id, version)
        return geom["sha256"] if geom else None
