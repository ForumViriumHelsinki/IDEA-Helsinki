"""
Tests for InfluxDBWriteQueue - Thread-safe InfluxDB write coordination.

Following TDD RED-GREEN-REFACTOR cycle.
"""

import threading
from datetime import UTC, datetime
from queue import Full

import pytest

from idea_shared.threading.write_queue import InfluxDBWriteQueue, WriteRequest


class TestWriteRequest:
    """Tests for WriteRequest data class."""

    def test_write_request_creation(self):
        """Test creating a WriteRequest."""
        fcd_data = {"segmentId": {"123": {"data": "test"}}}
        timestamp = datetime.now(UTC)

        request = WriteRequest(fcd_data=fcd_data, worker_id=1, timestamp=timestamp)

        assert request.fcd_data == fcd_data
        assert request.worker_id == 1
        assert request.timestamp == timestamp


class TestInfluxDBWriteQueue:
    """Tests for InfluxDBWriteQueue."""

    def test_queue_initialization(self):
        """Test queue initializes with default max size."""
        queue = InfluxDBWriteQueue()

        stats = queue.get_stats()
        assert stats["total_writes"] == 0
        assert stats["failed_writes"] == 0
        assert stats["queue_size"] == 0
        assert not queue.is_shutdown()

    def test_queue_with_custom_max_size(self):
        """Test queue initialization with custom max size."""
        queue = InfluxDBWriteQueue(max_queue_size=50)

        # Queue should be created successfully
        assert not queue.is_shutdown()

    def test_put_write_request(self):
        """Test adding a write request to the queue."""
        queue = InfluxDBWriteQueue()
        fcd_data = {"segmentId": {"123": {"data": "test"}}}

        queue.put_write_request(fcd_data, worker_id=1)

        stats = queue.get_stats()
        assert stats["queue_size"] == 1

    def test_get_next_request(self):
        """Test getting the next write request from queue."""
        queue = InfluxDBWriteQueue()
        fcd_data = {"segmentId": {"123": {"data": "test"}}}

        queue.put_write_request(fcd_data, worker_id=1)

        request = queue.get_next_request(timeout=0.1)
        assert request is not None
        assert request.fcd_data == fcd_data
        assert request.worker_id == 1
        assert isinstance(request.timestamp, datetime)

    def test_get_next_request_empty_queue(self):
        """Test that empty queue returns None after timeout."""
        queue = InfluxDBWriteQueue()

        request = queue.get_next_request(timeout=0.1)
        assert request is None

    def test_mark_completed_success(self):
        """Test marking a write request as completed successfully."""
        queue = InfluxDBWriteQueue()
        fcd_data = {"segmentId": {"123": {"data": "test"}}}

        queue.put_write_request(fcd_data, worker_id=1)
        _ = queue.get_next_request()
        queue.mark_completed(success=True)

        stats = queue.get_stats()
        assert stats["total_writes"] == 1
        assert stats["failed_writes"] == 0

    def test_mark_completed_failure(self):
        """Test marking a write request as failed."""
        queue = InfluxDBWriteQueue()
        fcd_data = {"segmentId": {"123": {"data": "test"}}}

        queue.put_write_request(fcd_data, worker_id=1)
        _ = queue.get_next_request()
        queue.mark_completed(success=False)

        stats = queue.get_stats()
        assert stats["total_writes"] == 1
        assert stats["failed_writes"] == 1

    def test_shutdown(self):
        """Test shutdown signal."""
        queue = InfluxDBWriteQueue()

        assert not queue.is_shutdown()

        queue.shutdown()

        assert queue.is_shutdown()

    def test_get_next_request_after_shutdown(self):
        """Test that get_next_request returns None after shutdown."""
        queue = InfluxDBWriteQueue()

        queue.shutdown()

        request = queue.get_next_request(timeout=0.1)
        assert request is None

    def test_multiple_requests_fifo(self):
        """Test that requests are processed in FIFO order."""
        queue = InfluxDBWriteQueue()

        # Add three requests
        queue.put_write_request({"data": "first"}, worker_id=1)
        queue.put_write_request({"data": "second"}, worker_id=2)
        queue.put_write_request({"data": "third"}, worker_id=3)

        # Get them in order
        req1 = queue.get_next_request(timeout=0.1)
        req2 = queue.get_next_request(timeout=0.1)
        req3 = queue.get_next_request(timeout=0.1)

        assert req1.fcd_data == {"data": "first"}
        assert req2.fcd_data == {"data": "second"}
        assert req3.fcd_data == {"data": "third"}

    def test_queue_full_blocks(self):
        """Test that queue blocks when full."""
        queue = InfluxDBWriteQueue(max_queue_size=2)

        # Fill the queue
        queue.put_write_request({"data": "first"}, worker_id=1)
        queue.put_write_request({"data": "second"}, worker_id=2)

        # Third put should timeout (queue is full)
        with pytest.raises(Full):
            queue.put_write_request({"data": "third"}, worker_id=3, timeout=0.1)

    def test_thread_safety_stats(self):
        """Test that statistics tracking is thread-safe."""
        queue = InfluxDBWriteQueue()

        def producer(worker_id):
            """Producer thread that adds write requests."""
            for i in range(10):
                queue.put_write_request(
                    {"data": f"worker{worker_id}_item{i}"}, worker_id
                )

        def consumer():
            """Consumer thread that processes write requests."""
            processed = 0
            while processed < 30:  # 3 workers * 10 items
                request = queue.get_next_request(timeout=1.0)
                if request:
                    queue.mark_completed(success=True)
                    processed += 1

        # Start 3 producers and 1 consumer
        producers = [threading.Thread(target=producer, args=(i,)) for i in range(3)]
        consumer_thread = threading.Thread(target=consumer)

        for t in producers:
            t.start()
        consumer_thread.start()

        for t in producers:
            t.join()
        consumer_thread.join()

        # All 30 writes should be completed
        stats = queue.get_stats()
        assert stats["total_writes"] == 30
        assert stats["failed_writes"] == 0

    def test_multiple_producers_single_consumer(self):
        """Test multiple producers with single consumer pattern."""
        queue = InfluxDBWriteQueue()
        items_per_producer = 5
        num_producers = 4

        def producer(worker_id):
            """Producer adds items to queue."""
            for i in range(items_per_producer):
                queue.put_write_request({"worker": worker_id, "item": i}, worker_id)

        def consumer():
            """Consumer processes items until shutdown."""
            total_processed = 0
            expected = num_producers * items_per_producer

            while total_processed < expected:
                request = queue.get_next_request(timeout=0.5)
                if request:
                    queue.mark_completed(success=True)
                    total_processed += 1

        # Start producers
        producer_threads = [
            threading.Thread(target=producer, args=(i,)) for i in range(num_producers)
        ]
        for t in producer_threads:
            t.start()

        # Start consumer
        consumer_thread = threading.Thread(target=consumer)
        consumer_thread.start()

        # Wait for completion
        for t in producer_threads:
            t.join()
        consumer_thread.join()

        stats = queue.get_stats()
        assert stats["total_writes"] == num_producers * items_per_producer
        assert stats["queue_size"] == 0  # All consumed

    def test_write_request_timestamp_set(self):
        """Test that write request timestamp is set when created."""
        queue = InfluxDBWriteQueue()
        before = datetime.now(UTC)

        queue.put_write_request({"data": "test"}, worker_id=1)
        request = queue.get_next_request()

        after = datetime.now(UTC)

        assert before <= request.timestamp <= after
