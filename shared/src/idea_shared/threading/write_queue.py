"""
Thread-safe write queue for coordinating InfluxDB writes.
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Queue


@dataclass
class WriteRequest:
    """Represents a request to write FCD data to InfluxDB."""

    fcd_data: dict
    worker_id: int
    timestamp: datetime


class InfluxDBWriteQueue:
    """Thread-safe queue for coordinating InfluxDB writes."""

    def __init__(self, max_queue_size: int = 100):
        """
        Initialize the write queue.

        Args:
            max_queue_size: Maximum number of write requests to buffer
        """
        self._queue = Queue(maxsize=max_queue_size)
        self._shutdown = threading.Event()
        self._total_writes = 0
        self._failed_writes = 0
        self._lock = threading.Lock()

    def put_write_request(self, fcd_data: dict, worker_id: int, timeout: float = 10.0):
        """
        Add a write request to the queue.

        Args:
            fcd_data: FCD data dictionary to write
            worker_id: ID of the worker submitting this request
            timeout: How long to wait if queue is full (seconds)

        Raises:
            queue.Full: If queue is full and timeout expires
        """
        request = WriteRequest(
            fcd_data=fcd_data, worker_id=worker_id, timestamp=datetime.now(UTC)
        )
        self._queue.put(request, timeout=timeout)

    def get_next_request(self, timeout: float = 1.0) -> WriteRequest | None:
        """
        Get the next write request (called by writer thread).

        Args:
            timeout: How long to wait for a request (seconds)

        Returns:
            WriteRequest or None if timeout or shutdown
        """
        if self._shutdown.is_set():
            return None

        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def mark_completed(self, success: bool = True):
        """
        Mark a write request as completed.

        Args:
            success: Whether the write succeeded
        """
        with self._lock:
            self._total_writes += 1
            if not success:
                self._failed_writes += 1
        self._queue.task_done()

    def shutdown(self):
        """Signal shutdown to writer thread."""
        self._shutdown.set()

    def is_shutdown(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown.is_set()

    def get_stats(self) -> dict:
        """Get write statistics."""
        with self._lock:
            return {
                "total_writes": self._total_writes,
                "failed_writes": self._failed_writes,
                "queue_size": self._queue.qsize(),
            }
