"""Service state tracking for Traffic Monitor health monitoring."""

import logging
from datetime import UTC, datetime
from threading import Lock

logger = logging.getLogger(__name__)


class ServiceState:
    """Track operational state and metrics for health monitoring.

    This class maintains timestamps and counters for various service operations,
    allowing health checks to determine if the service is functioning properly.
    Thread-safe for access from both main loop and health check server.
    """

    def __init__(self):
        """Initialize service state with all metrics set to None/0."""
        self._lock = Lock()
        self.last_wfs_fetch = None
        self.last_wfs_success = None
        self.last_intersection_calc = None
        self.last_file_write = None
        self.is_processing = False
        self.current_disturbance_count = 0
        self.current_intersection_count = 0
        self.last_error = None
        self.startup_time = datetime.now(UTC)

    def update_wfs_fetch(self, success: bool, disturbance_count: int = 0, error: str = None):
        """Update WFS fetch status.

        Args:
            success: Whether the fetch was successful
            disturbance_count: Number of disturbances fetched (if successful)
            error: Error message if fetch failed
        """
        with self._lock:
            self.last_wfs_fetch = datetime.now(UTC)
            if success:
                self.last_wfs_success = datetime.now(UTC)
                self.current_disturbance_count = disturbance_count
                logger.info(f"WFS fetch successful: {disturbance_count} disturbances")
            else:
                self.last_error = error or "WFS fetch failed"
                logger.warning(f"WFS fetch failed: {self.last_error}")

    def update_intersection(self, intersection_count: int):
        """Update intersection calculation status.

        Args:
            intersection_count: Number of intersections found
        """
        with self._lock:
            self.last_intersection_calc = datetime.now(UTC)
            self.current_intersection_count = intersection_count
            logger.info(f"Intersection calculation complete: {intersection_count} intersections")

    def update_file_write(self, success: bool = True, error: str = None):
        """Update file write status.

        Args:
            success: Whether the write was successful
            error: Error message if write failed
        """
        with self._lock:
            if success:
                self.last_file_write = datetime.now(UTC)
                logger.info("Output file written successfully")
            else:
                self.last_error = error or "File write failed"
                logger.error(f"File write failed: {self.last_error}")

    def set_processing(self, is_processing: bool):
        """Set processing flag.

        Args:
            is_processing: Whether the service is currently processing
        """
        with self._lock:
            self.is_processing = is_processing
            if is_processing:
                logger.debug("Processing started")
            else:
                logger.debug("Processing completed")

    def get_status_summary(self) -> dict:
        """Get a summary of current service status.

        Returns:
            Dictionary containing current status information
        """
        with self._lock:
            now = datetime.now(UTC)
            summary = {
                "startup_time": self.startup_time.isoformat(),
                "uptime_minutes": (now - self.startup_time).total_seconds() / 60,
                "is_processing": self.is_processing,
                "current_disturbance_count": self.current_disturbance_count,
                "current_intersection_count": self.current_intersection_count,
            }

            if self.last_wfs_fetch:
                summary["last_wfs_fetch"] = self.last_wfs_fetch.isoformat()
                summary["last_wfs_fetch_minutes_ago"] = (
                    (now - self.last_wfs_fetch).total_seconds() / 60
                )

            if self.last_wfs_success:
                summary["last_wfs_success"] = self.last_wfs_success.isoformat()
                summary["last_wfs_success_minutes_ago"] = (
                    (now - self.last_wfs_success).total_seconds() / 60
                )

            if self.last_intersection_calc:
                summary["last_intersection_calc"] = self.last_intersection_calc.isoformat()
                summary["last_intersection_calc_minutes_ago"] = (
                    (now - self.last_intersection_calc).total_seconds() / 60
                )

            if self.last_file_write:
                summary["last_file_write"] = self.last_file_write.isoformat()
                summary["last_file_write_minutes_ago"] = (
                    (now - self.last_file_write).total_seconds() / 60
                )

            if self.last_error:
                summary["last_error"] = self.last_error

            return summary

    def reset_error(self):
        """Clear the last error message."""
        with self._lock:
            self.last_error = None