"""Thread-safe wrapper for health check objects."""

import threading


class ThreadSafeHealthCheckWrapper:
    """Thread-safe wrapper for health check objects accessed by multiple workers."""

    def __init__(self, health_check):
        """Initialize the wrapper.

        Args:
            health_check: The health check object to wrap (e.g., ProcessingPipelineHealthCheck)

        """
        self._health_check = health_check
        self._lock = threading.Lock()

    def record_processing_start(self):
        """Thread-safe: Record start of processing."""
        with self._lock:
            self._health_check.record_processing_start()

    def record_processing_complete(self, count: int):
        """Thread-safe: Record successful processing completion.

        Args:
            count: Number of items processed

        """
        with self._lock:
            self._health_check.record_processing_complete(count)

    def record_error(self, error: str):
        """Thread-safe: Record a processing error.

        Args:
            error: Error message to record

        """
        with self._lock:
            self._health_check.record_error(error)

    def update_timestamp(self):
        """Thread-safe: Update the last successful update timestamp."""
        if hasattr(self._health_check, "update_timestamp"):
            with self._lock:
                self._health_check.update_timestamp()
