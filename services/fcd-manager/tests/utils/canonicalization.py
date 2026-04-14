"""Canonicalization utilities for deterministic testing.

Provides order-agnostic comparison of InfluxDB points by:
1. Creating canonical keys from (measurement, sorted tags, timestamp)
2. Rounding field values to fixed precision
3. Comparing as sets instead of lists
"""

from typing import Any


class CanonicalPoint:
    """Canonical representation of an InfluxDB point.

    Provides deterministic comparison independent of:
    - Processing order
    - Batch boundaries
    - Thread execution sequence
    """

    def __init__(self, point: dict[str, Any]):
        """Create canonical point from raw point data.

        Args:
            point: Point dictionary with {measurement, tags, fields, time}

        """
        self.measurement = point["measurement"]
        self.tags = tuple(sorted(point["tags"].items()))
        self.timestamp = point["time"]

        # Round fields to 3 decimal places for deterministic comparison
        self.fields = {
            k: round(v, 3) if isinstance(v, float) else v
            for k, v in point["fields"].items()
        }

    def to_key(self) -> tuple:
        """Create canonical key for comparison.

        Returns:
            Tuple of (measurement, tags, timestamp)

        """
        return (self.measurement, self.tags, self.timestamp)

    def to_value(self) -> dict:
        """Get canonical fields.

        Returns:
            Dictionary of rounded field values

        """
        return self.fields

    def __hash__(self):
        """Hash based on canonical key."""
        return hash(self.to_key())

    def __eq__(self, other):
        """Equality based on canonical key and fields."""
        if not isinstance(other, CanonicalPoint):
            return False
        return self.to_key() == other.to_key() and self.fields == other.fields

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"CanonicalPoint({self.measurement}, "
            f"tags={dict(self.tags)}, "
            f"fields={self.fields}, "
            f"time={self.timestamp})"
        )


def canonicalize_points(points: list[dict[str, Any]]) -> set[CanonicalPoint]:
    """Convert list of points to canonical set.

    Args:
        points: List of point dictionaries

    Returns:
        Set of canonical points for order-agnostic comparison

    """
    return {CanonicalPoint(p) for p in points}


def compare_point_sets(
    points_a: list[dict[str, Any]], points_b: list[dict[str, Any]]
) -> tuple[bool, dict[str, Any]]:
    """Compare two point lists in an order-agnostic way.

    Args:
        points_a: First point list
        points_b: Second point list

    Returns:
        Tuple of (is_equal, diff_info)
        - is_equal: True if points are equivalent
        - diff_info: Dictionary with comparison details

    """
    canonical_a = canonicalize_points(points_a)
    canonical_b = canonicalize_points(points_b)

    is_equal = canonical_a == canonical_b

    diff_info = {
        "count_a": len(points_a),
        "count_b": len(points_b),
        "canonical_count_a": len(canonical_a),
        "canonical_count_b": len(canonical_b),
        "is_equal": is_equal,
        "only_in_a": canonical_a - canonical_b,
        "only_in_b": canonical_b - canonical_a,
    }

    return is_equal, diff_info
