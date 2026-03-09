"""
Tests for DateRangeQueue - Thread-safe date range distribution.

Following TDD RED-GREEN-REFACTOR cycle.
"""

from datetime import UTC, datetime

from idea_shared.threading.date_queue import DateRange, DateRangeQueue


class TestDateRange:
    """Tests for DateRange data class."""

    def test_date_range_creation(self):
        """Test creating a DateRange."""
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        date_range = DateRange(start=start, end=end)

        assert date_range.start == start
        assert date_range.end == end
        assert date_range.worker_id == 0  # Default

    def test_date_range_with_worker_id(self):
        """Test creating a DateRange with worker_id."""
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        date_range = DateRange(start=start, end=end, worker_id=5)

        assert date_range.worker_id == 5


class TestDateRangeQueue:
    """Tests for DateRangeQueue."""

    def test_queue_initialization(self):
        """Test queue initializes empty."""
        queue = DateRangeQueue()

        assert queue.get_progress() == (0, 0)
        assert queue.is_complete()

    def test_populate_single_chunk(self):
        """Test populating queue with a single chunk."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 5, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        completed, total = queue.get_progress()
        assert completed == 0
        assert total == 1
        assert not queue.is_complete()

    def test_populate_multiple_chunks(self):
        """Test populating queue with multiple chunks."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 31, tzinfo=UTC)  # 31 days

        queue.populate(start, end, chunk_days=7)

        completed, total = queue.get_progress()
        assert completed == 0
        # 31 days with 7-day chunks = 5 chunks (1-7, 8-14, 15-21, 22-28, 29-31)
        assert total == 5
        assert not queue.is_complete()

    def test_get_next_range(self):
        """Test getting the next date range from queue."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 14, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        # Get first range
        range1 = queue.get_next_range(timeout=0.1)
        assert range1 is not None
        assert range1.start == datetime(2025, 1, 1, tzinfo=UTC)
        assert range1.end == datetime(2025, 1, 7, tzinfo=UTC)

        # Get second range
        range2 = queue.get_next_range(timeout=0.1)
        assert range2 is not None
        assert range2.start == datetime(2025, 1, 8, tzinfo=UTC)
        assert range2.end == datetime(2025, 1, 14, tzinfo=UTC)

        # Queue should be empty now
        range3 = queue.get_next_range(timeout=0.1)
        assert range3 is None

    def test_mark_completed(self):
        """Test marking ranges as completed."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 14, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        # Initially 0 completed
        assert queue.get_progress() == (0, 2)

        # Get and mark one as completed
        _ = queue.get_next_range()
        queue.mark_completed()

        assert queue.get_progress() == (1, 2)
        assert not queue.is_complete()

        # Get and mark second as completed
        _ = queue.get_next_range()
        queue.mark_completed()

        assert queue.get_progress() == (2, 2)
        assert queue.is_complete()

    def test_empty_queue_returns_none(self):
        """Test that empty queue returns None quickly."""
        queue = DateRangeQueue()

        # Empty queue should return None after timeout
        result = queue.get_next_range(timeout=0.1)
        assert result is None

    def test_chunk_boundary_alignment(self):
        """Test that chunks don't exceed end date."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 10, tzinfo=UTC)  # 10 days

        queue.populate(start, end, chunk_days=7)

        # First chunk: full 7 days
        range1 = queue.get_next_range()
        assert range1 is not None
        assert range1.start == datetime(2025, 1, 1, tzinfo=UTC)
        assert range1.end == datetime(2025, 1, 7, tzinfo=UTC)

        # Second chunk: only 3 days (8, 9, 10)
        range2 = queue.get_next_range()
        assert range2 is not None
        assert range2.start == datetime(2025, 1, 8, tzinfo=UTC)
        assert range2.end == datetime(2025, 1, 10, tzinfo=UTC)  # Capped at end date

        # No more ranges
        assert queue.get_next_range(timeout=0.1) is None

    def test_thread_safety_progress(self):
        """Test that progress tracking is thread-safe."""
        import threading

        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 31, tzinfo=UTC)
        queue.populate(start, end, chunk_days=1)  # 31 chunks

        def worker():
            """Worker thread that gets and marks ranges."""
            while True:
                range_item = queue.get_next_range(timeout=0.1)
                if range_item is None:
                    break
                queue.mark_completed()

        # Spawn multiple threads
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All ranges should be completed
        assert queue.is_complete()
        assert queue.get_progress() == (31, 31)

    def test_single_day_range(self):
        """Test with start and end on the same day."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 1, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        completed, total = queue.get_progress()
        assert total == 1

        range1 = queue.get_next_range()
        assert range1 is not None
        assert range1.start == start
        assert range1.end == end

    def test_large_chunk_size(self):
        """Test with chunk size larger than date range."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 5, tzinfo=UTC)

        queue.populate(start, end, chunk_days=30)  # Larger than range

        completed, total = queue.get_progress()
        assert total == 1  # Should be single chunk

        range1 = queue.get_next_range()
        assert range1 is not None
        assert range1.start == start
        assert range1.end == end


class TestDateRangeRetry:
    """Tests for DateRange retry functionality."""

    def test_date_range_with_retry_defaults(self):
        """Test DateRange initializes with retry defaults."""
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        date_range = DateRange(start=start, end=end)

        assert date_range.retry_count == 0
        assert date_range.last_error is None

    def test_date_range_with_retry_values(self):
        """Test DateRange with explicit retry values."""
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        date_range = DateRange(
            start=start, end=end, retry_count=2, last_error="Test error"
        )

        assert date_range.retry_count == 2
        assert date_range.last_error == "Test error"

    def test_requeue_failed_increments_retry(self):
        """Test that requeue_failed increments retry count."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        # Get a range
        date_range = queue.get_next_range()
        assert date_range is not None
        assert date_range.retry_count == 0

        # Requeue as failed
        queue.requeue_failed(date_range, "Test error message")

        # Get it again
        requeued_range = queue.get_next_range()
        assert requeued_range is not None
        assert requeued_range.retry_count == 1
        assert requeued_range.last_error == "Test error message"

    def test_requeue_failed_multiple_times(self):
        """Test requeuing the same range multiple times."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        date_range = queue.get_next_range()
        assert date_range is not None

        # Requeue 3 times
        for i in range(1, 4):
            queue.requeue_failed(date_range, f"Error {i}")
            date_range = queue.get_next_range()
            assert date_range is not None
            assert date_range.retry_count == i
            assert date_range.last_error == f"Error {i}"

    def test_move_to_dead_letter(self):
        """Test moving a failed range to dead-letter queue."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        date_range = queue.get_next_range()
        assert date_range is not None
        date_range.retry_count = 3
        date_range.last_error = "Final error"

        # Move to dead-letter
        queue.move_to_dead_letter(date_range)

        # Should be in dead-letter queue
        dead_letter_ranges = queue.get_dead_letter_ranges()
        assert len(dead_letter_ranges) == 1
        assert dead_letter_ranges[0].start == start
        assert dead_letter_ranges[0].retry_count == 3

    def test_get_dead_letter_ranges_empty(self):
        """Test get_dead_letter_ranges when empty."""
        queue = DateRangeQueue()

        dead_letter_ranges = queue.get_dead_letter_ranges()
        assert dead_letter_ranges == []

    def test_multiple_dead_letter_ranges(self):
        """Test multiple ranges in dead-letter queue."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 14, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        # Move both ranges to dead-letter
        range1 = queue.get_next_range()
        range2 = queue.get_next_range()
        assert range1 is not None
        assert range2 is not None

        queue.move_to_dead_letter(range1)
        queue.move_to_dead_letter(range2)

        dead_letter_ranges = queue.get_dead_letter_ranges()
        assert len(dead_letter_ranges) == 2

    def test_requeue_does_not_affect_total_ranges(self):
        """Test that requeue doesn't change total_ranges count."""
        queue = DateRangeQueue()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 7, tzinfo=UTC)

        queue.populate(start, end, chunk_days=7)

        assert queue.get_progress() == (0, 1)

        date_range = queue.get_next_range()
        assert date_range is not None
        queue.requeue_failed(date_range, "Error")

        # Total should still be 1
        assert queue.get_progress() == (0, 1)
