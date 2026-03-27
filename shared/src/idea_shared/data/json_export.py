"""JSON and GeoJSON export functions for TFDS_Dashboard compatibility.

Exports segment and disturbance data from repository interfaces to JSON files.
Two formats are supported:

- **Internal JSON**: Preserves the exact repository format for TFDS_Dashboard
  backwards compatibility.
- **GeoJSON**: RFC 7946 FeatureCollection format for standard-compliant external
  consumption. Per Section 4, no ``crs`` member is included (WGS84 is default).
"""

from __future__ import annotations

import logging
from pathlib import Path

from idea_shared.data.repositories import DisturbanceRepository, SegmentRepository
from idea_shared.threading.file_locks import atomic_write_json

logger = logging.getLogger(__name__)


def export_segments_json(repo: SegmentRepository, path: Path) -> bool:
    """Export segment data to JSON in the original TFDS_Dashboard format.

    Args:
        repo: Segment repository to read from.
        path: Destination file path.

    Returns:
        True on success, False on failure.
    """
    try:
        segments = repo.get_segments()
        atomic_write_json(path, segments)
        logger.info("Exported segments JSON to %s", path)
        return True
    except Exception:
        logger.exception("Failed to export segments JSON to %s", path)
        return False


def export_disturbances_json(repo: DisturbanceRepository, path: Path) -> bool:
    """Export disturbance data to JSON in the original TFDS_Dashboard format.

    Args:
        repo: Disturbance repository to read from.
        path: Destination file path.

    Returns:
        True on success, False on failure.
    """
    try:
        disturbances = repo.get_disturbances()
        atomic_write_json(path, disturbances)
        logger.info("Exported disturbances JSON to %s", path)
        return True
    except Exception:
        logger.exception("Failed to export disturbances JSON to %s", path)
        return False


def export_segments_geojson(repo: SegmentRepository, path: Path) -> bool:
    """Export segment data as an RFC 7946 GeoJSON FeatureCollection.

    Each segment becomes a Feature with its geometry and a ``segment_id``
    property. Per RFC 7946 Section 4, no ``crs`` member is included.

    Args:
        repo: Segment repository to read from.
        path: Destination file path.

    Returns:
        True on success, False on failure.
    """
    try:
        segments = repo.get_segments()
        features = _segments_to_features(segments)
        collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        atomic_write_json(path, collection)
        logger.info("Exported segments GeoJSON to %s (%d features)", path, len(features))
        return True
    except Exception:
        logger.exception("Failed to export segments GeoJSON to %s", path)
        return False


def export_disturbances_geojson(repo: DisturbanceRepository, path: Path) -> bool:
    """Export disturbance data as an RFC 7946 GeoJSON FeatureCollection.

    Each disturbance becomes a Feature with its geometry and properties
    including ``segment_id`` and ``detailedCollisions``. Per RFC 7946
    Section 4, no ``crs`` member is included.

    Args:
        repo: Disturbance repository to read from.
        path: Destination file path.

    Returns:
        True on success, False on failure.
    """
    try:
        disturbances = repo.get_disturbances()
        features = _disturbances_to_features(disturbances)
        collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        atomic_write_json(path, collection)
        logger.info(
            "Exported disturbances GeoJSON to %s (%d features)", path, len(features)
        )
        return True
    except Exception:
        logger.exception("Failed to export disturbances GeoJSON to %s", path)
        return False


def _segments_to_features(segments: dict) -> list[dict]:
    """Convert segment mapping dict to a list of GeoJSON Features."""
    features: list[dict] = []
    segment_id_map = segments.get("segmentId", {})
    for seg_id, seg_data in segment_id_map.items():
        properties: dict = {"segment_id": seg_id}
        geometry = None
        for key, value in seg_data.items():
            if key == "geometry":
                geometry = value
            else:
                properties[key] = value
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            }
        )
    return features


def _disturbances_to_features(disturbances: dict) -> list[dict]:
    """Convert disturbance mapping dict to a list of GeoJSON Features."""
    features: list[dict] = []
    segment_id_map = disturbances.get("segmentId", {})
    for seg_id, seg_data in segment_id_map.items():
        properties: dict = {"segment_id": seg_id}
        geometry = None
        for key, value in seg_data.items():
            if key == "geometry":
                geometry = value
            else:
                properties[key] = value
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            }
        )
    return features
