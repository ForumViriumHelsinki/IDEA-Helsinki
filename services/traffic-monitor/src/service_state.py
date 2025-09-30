"""Service state tracking for health monitoring."""

import threading
from datetime import UTC, datetime


class ServiceState:
    """Thread-safe state management for service monitoring."""

    def __init__(self):
        """Initialize service state."""
        self._lock = threading.Lock()
        self.last_wfs_success = None
        self.last_wfs_attempt = None
        self.last_processing_time = None
        self.last_error = None
        self.is_processing = False
        self.wfs_consecutive_failures = 0
        self.detector = None

    def update_wfs_fetch(self, success: bool, error: str = None):
        """Update WFS fetch status.

        Args:
            success: Whether the fetch was successful
            error: Error message if fetch failed
        """
        with self._lock:
            self.last_wfs_attempt = datetime.now(UTC)
            if success:
                self.last_wfs_success = self.last_wfs_attempt
                self.wfs_consecutive_failures = 0
                self.last_error = None
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

    def start_processing(self):
        """Mark that processing has started."""
        with self._lock:
            self.is_processing = True

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
                minutes_since_success = (now - self.last_wfs_success).total_seconds() / 60
                summary["minutes_since_wfs_success"] = minutes_since_success

            if self.last_wfs_attempt:
                minutes_since_attempt = (now - self.last_wfs_attempt).total_seconds() / 60
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