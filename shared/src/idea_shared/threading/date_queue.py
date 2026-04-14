"""Thread-safe date range queue for distributing work to backfill workers."""

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from queue import Empty, Queue

DEAD_LETTER_QUEUE_MAX_SIZE = 1000


@dataclass
class DateRange:
    """Represents a range of dates to process."""

    start: datetime
    end: datetime
    worker_id: int = 0  # For tracking which worker processes it
    retry_count: int = 0  # Number of times this range has been retried
    last_error: str | None = None  # Last error message if retried


class DateRangeQueue:
    """Thread-safe queue for distributing date ranges to workers."""

    def __init__(self):
        """Initialize an empty date range queue."""
        self._queue = Queue()
        self._total_ranges = 0
        self._completed_ranges = 0
        self._dead_letter_ranges: deque[DateRange] = deque(
            maxlen=DEAD_LETTER_QUEUE_MAX_SIZE
        )  # Failed ranges that exceeded max retries
        self._lock = threading.Lock()

    def populate(self, start_date: datetime, end_date: datetime, chunk_days: int = 7):
        """Divide the date range into chunks and populate the queue.

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
        """Get the next date range to process.

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
        """Get progress information.

        Returns:
            (completed_ranges, total_ranges)

        """
        with self._lock:
            return (self._completed_ranges, self._total_ranges)

    def is_complete(self) -> bool:
        """Check if all ranges have been processed."""
        with self._lock:
            return self._completed_ranges >= self._total_ranges

    def requeue_failed(self, date_range: DateRange, error: str):
        """Requeue a failed date range for retry.

        Args:
            date_range: The date range that failed
            error: Error message to record

        """
        date_range.retry_count += 1
        date_range.last_error = error
        self._queue.put(date_range)

    def move_to_dead_letter(self, date_range: DateRange):
        """Move a permanently failed date range to the dead-letter queue.

        Args:
            date_range: The date range that permanently failed

        """
        with self._lock:
            self._dead_letter_ranges.append(date_range)

    def get_dead_letter_ranges(self) -> list[DateRange]:
        """Get all date ranges in the dead-letter queue.

        Returns:
            List of permanently failed date ranges

        """
        with self._lock:
            return list(self._dead_letter_ranges)

    def is_empty(self) -> bool:
        """Check if the queue is empty.

        Returns:
            True if queue has no more ranges to process

        """
        return self._queue.empty()

    def get_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dictionary with queue statistics

        """
        with self._lock:
            return {
                "total_ranges": self._total_ranges,
                "completed_ranges": self._completed_ranges,
                "queue_size": self._queue.qsize(),
                "dead_letter_count": len(self._dead_letter_ranges),
            }
