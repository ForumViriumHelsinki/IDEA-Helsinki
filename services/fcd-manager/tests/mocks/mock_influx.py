"""Mock InfluxDB Writer for testing."""

import threading
from typing import Any


class MockInfluxWriter:
    """Mock InfluxDB writer for deterministic testing.

    Features:
    - Thread-safe point collection
    - Canonical point representation
    - Diagnostic counters
    - Order-agnostic comparison support
    """

    def __init__(self):
        """Initialize mock InfluxDB writer."""
        self._points: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._counters = {
            "points_written": 0,
            "batches_written": 0,
            "rows_skipped_malformed": 0,
            "rows_skipped_missing_geometry": 0,
            "duplicates_collapsed": 0,
        }

    def write_points(self, points: list[dict[str, Any]]):
        """Write points to mock storage.

        Args:
            points: List of point dictionaries with {measurement, tags, fields, time}

        """
        with self._lock:
            self._points.extend(points)
            self._counters["points_written"] += len(points)
            self._counters["batches_written"] += 1

    def write_point(self, measurement: str, tags: dict, fields: dict, timestamp):
        """Write single point to mock storage.

        Args:
            measurement: Measurement name
            tags: Tag dictionary
            fields: Field dictionary
            timestamp: Point timestamp

        """
        point = {
            "measurement": measurement,
            "tags": tags,
            "fields": fields,
            "time": timestamp,
        }
        self.write_points([point])

    def increment_counter(self, counter_name: str, value: int = 1):
        """Increment diagnostic counter.

        Args:
            counter_name: Name of counter to increment
            value: Amount to increment (default: 1)

        """
        with self._lock:
            if counter_name in self._counters:
                self._counters[counter_name] += value

    def get_points(self) -> list[dict[str, Any]]:
        """Get all collected points.

        Returns:
            List of point dictionaries

        """
        with self._lock:
            return self._points.copy()

    def get_counters(self) -> dict[str, int]:
        """Get diagnostic counters.

        Returns:
            Dictionary of counter names to values

        """
        with self._lock:
            return self._counters.copy()

    def reset(self):
        """Reset all points and counters."""
        with self._lock:
            self._points.clear()
            self._counters = {
                "points_written": 0,
                "batches_written": 0,
                "rows_skipped_malformed": 0,
                "rows_skipped_missing_geometry": 0,
                "duplicates_collapsed": 0,
            }
