"""
Thread-safe date range queue for distributing work to backfill workers.
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from queue import Empty, Queue


@dataclass
class DateRange:
    """Represents a range of dates to process."""

    start: datetime
    end: datetime
    worker_id: int = 0  # For tracking which worker processes it


class DateRangeQueue:
    """Thread-safe queue for distributing date ranges to workers."""

    def __init__(self):
        """Initialize an empty date range queue."""
        self._queue = Queue()
        self._total_ranges = 0
        self._completed_ranges = 0
        self._lock = threading.Lock()

    def populate(self, start_date: datetime, end_date: datetime, chunk_days: int = 7):
        """
        Divide the date range into chunks and populate the queue.

        Args:
            start_date: Start of the overall date range
            end_date: End of the overall date range
            chunk_days: Size of each chunk in days
        """
        current = start_date
        range_count = 0

        while current <= end_date:
            chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
            self._queue.put(DateRange(start=current, end=chunk_end))
            current = chunk_end + timedelta(days=1)
            range_count += 1

        with self._lock:
            self._total_ranges = range_count

    def get_next_range(self, timeout: float = 1.0) -> DateRange | None:
        """
        Get the next date range to process.

        Args:
            timeout: How long to wait for a range (seconds)

        Returns:
            DateRange or None if queue is empty
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def mark_completed(self):
        """Mark a range as completed."""
        with self._lock:
            self._completed_ranges += 1
        self._queue.task_done()

    def get_progress(self) -> tuple[int, int]:
        """
        Get progress information.

        Returns:
            (completed_ranges, total_ranges)
        """
        with self._lock:
            return (self._completed_ranges, self._total_ranges)

    def is_complete(self) -> bool:
        """Check if all ranges have been processed."""
        with self._lock:
            return self._completed_ranges >= self._total_ranges
