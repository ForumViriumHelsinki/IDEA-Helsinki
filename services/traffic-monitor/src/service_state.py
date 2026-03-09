"""Service state tracking for health monitoring."""

import threading
from datetime import UTC, datetime


class ServiceState:
    """Thread-safe state management for service monitoring."""

    def __init__(self):
        """Initialize service state."""
        self._lock = threading.RLock()  # Use reentrant lock to allow nested locking
        self.startup_time = datetime.now(UTC)  # Track service startup time
        self.last_wfs_success = None
        self.last_wfs_attempt = None
        self.last_wfs_fetch = None  # Track last WFS fetch time
        self.last_processing_time = None
        self.last_intersection_calc = None  # Track last intersection calculation
        self.last_file_write = None  # Track last file write
        self.last_error = None
        self.is_processing = False
        self.wfs_consecutive_failures = 0
        self.current_disturbance_count = 0  # Current number of disturbances
        self.current_intersection_count = 0  # Current number of intersections
        self.detector = None

    def update_wfs_fetch(
        self,
        success: bool,
        disturbance_count: int | None = None,
        error: str | None = None,
    ):
        """Update WFS fetch status.

        Args:
            success: Whether the fetch was successful
            disturbance_count: Number of disturbances fetched (if successful)
            error: Error message if fetch failed
        """
        with self._lock:
            self.last_wfs_attempt = datetime.now(UTC)
            self.last_wfs_fetch = self.last_wfs_attempt
            if success:
                self.last_wfs_success = self.last_wfs_attempt
                self.wfs_consecutive_failures = 0
                self.last_error = None
                if disturbance_count is not None:
                    self.current_disturbance_count = disturbance_count
            else:
                self.wfs_consecutive_failures += 1
                if error:
                    self.last_error = error

    def update_processing(self, processing_time: datetime):
        """Update processing status.

        Args:
            processing_time: When processing completed
        """
        with self._lock:
            self.last_processing_time = processing_time
            self.is_processing = False

    def set_detector(self, detector):
        """Set the IntersectionDetector reference.

        Args:
            detector: IntersectionDetector instance
        """
        with self._lock:
            self.detector = detector

    def get_detector(self):
        """Get the IntersectionDetector reference.

        Returns:
            IntersectionDetector instance or None
        """
        with self._lock:
            return self.detector

    def set_processing(self, processing: bool):
        """Set the processing state.

        Args:
            processing: Whether processing is active
        """
        with self._lock:
            self.is_processing = processing

    def start_processing(self):
        """Mark that processing has started (deprecated - use set_processing)."""
        self.set_processing(True)

    def get_summary(self) -> dict:
        """Get a summary of the current state.

        Returns:
            Dictionary containing state summary
        """
        with self._lock:
            now = datetime.now(UTC)
            summary = {
                "is_processing": self.is_processing,
                "wfs_consecutive_failures": self.wfs_consecutive_failures,
                "has_error": self.last_error is not None,
            }

            if self.last_wfs_success:
                minutes_since_success = (
                    now - self.last_wfs_success
                ).total_seconds() / 60
                summary["minutes_since_wfs_success"] = minutes_since_success

            if self.last_wfs_attempt:
                minutes_since_attempt = (
                    now - self.last_wfs_attempt
                ).total_seconds() / 60
                summary["minutes_since_wfs_attempt"] = minutes_since_attempt

            if self.last_processing_time:
                minutes_since_processing = (
                    now - self.last_processing_time
                ).total_seconds() / 60
                summary["minutes_since_processing"] = minutes_since_processing

            if self.last_error:
                summary["last_error"] = self.last_error

            summary["has_detector"] = self.detector is not None

            return summary

    def get_wfs_minutes_since_success(self) -> float | None:
        """Get minutes since last successful WFS fetch.

        Returns:
            Minutes since last success or None if never succeeded
        """
        with self._lock:
            if self.last_wfs_success:
                return (datetime.now(UTC) - self.last_wfs_success).total_seconds() / 60
            return None

    def get_processing_minutes_since_last(self) -> float | None:
        """Get minutes since last processing completed.

        Returns:
            Minutes since last processing or None if never processed
        """
        with self._lock:
            if self.last_processing_time:
                return (
                    datetime.now(UTC) - self.last_processing_time
                ).total_seconds() / 60
            return None

    def get_wfs_failure_count(self) -> int:
        """Get consecutive WFS failure count.

        Returns:
            Number of consecutive failures
        """
        with self._lock:
            return self.wfs_consecutive_failures

    def reset_error(self):
        """Clear the last error message."""
        with self._lock:
            self.last_error = None

    def update_intersection(self, intersection_count: int):
        """Update intersection calculation status.

        Args:
            intersection_count: Number of intersections calculated
        """
        with self._lock:
            self.last_intersection_calc = datetime.now(UTC)
            self.current_intersection_count = intersection_count

    def update_file_write(self, success: bool, error: str | None = None):
        """Update file write status.

        Args:
            success: Whether the file write was successful
            error: Error message if write failed
        """
        with self._lock:
            self.last_file_write = datetime.now(UTC)
            if not success and error:
                self.last_error = error

    def get_status_summary(self) -> dict:
        """Get a detailed status summary for health checks.

        Returns:
            Dictionary containing detailed status information
        """
        with self._lock:
            summary = self.get_summary()  # Start with basic summary

            # Add startup tracking
            summary["startup_time"] = self.startup_time
            summary["uptime_minutes"] = (
                datetime.now(UTC) - self.startup_time
            ).total_seconds() / 60

            # Add additional fields for health checks
            summary["current_disturbance_count"] = self.current_disturbance_count
            summary["current_intersection_count"] = self.current_intersection_count

            if self.last_wfs_fetch:
                summary["last_wfs_fetch"] = self.last_wfs_fetch

            if self.last_wfs_success:
                summary["last_wfs_success"] = self.last_wfs_success

            if self.last_intersection_calc:
                summary["last_intersection_calc"] = self.last_intersection_calc

            if self.last_file_write:
                summary["last_file_write"] = self.last_file_write

            return summary
