"""
Thread coordinator for multi-threaded FCD processing.

Orchestrates backfill workers, real-time workers, and InfluxDB writer thread.
"""

import logging
import threading
import time
from datetime import datetime

from idea_shared.lib.Constants.Constants import (
    FCD_MAX_CHUNK_RETRIES,
    FCD_RETRY_DELAY_SECONDS,
    FCD_SHUTDOWN_TIMEOUT_SECONDS,
    FCD_WRITE_QUEUE_MAX_SIZE,
    FCD_WRITE_QUEUE_TIMEOUT,
)
from idea_shared.threading.date_queue import DateRangeQueue
from idea_shared.threading.write_queue import InfluxDBWriteQueue


class ThreadCoordinator:
    """Coordinates multi-threaded FCD processing with backfill and real-time workers."""

    def __init__(
        self,
        num_backfill_workers: int,
        azure_manager,
        influx_config: dict,
        logger: logging.Logger,
        processing_function,
        max_write_queue_size: int = FCD_WRITE_QUEUE_MAX_SIZE,
        max_retries: int = FCD_MAX_CHUNK_RETRIES,
        retry_delay: int = FCD_RETRY_DELAY_SECONDS,
    ):
        """
        Initialize the thread coordinator.

        Args:
            num_backfill_workers: Number of backfill worker threads
            azure_manager: Azure blob storage manager
            influx_config: InfluxDB configuration
            logger: Logger instance
            processing_function: Function to process date ranges (generator that yields batches)
                                Signature: (azure_manager, start_date, end_date, batch_size) -> Generator[dict, None, None]
            max_write_queue_size: Maximum write queue size
            max_retries: Maximum retries for failed chunks
            retry_delay: Base delay for exponential backoff (seconds)
        """
        self.num_backfill_workers = num_backfill_workers
        self.azure_manager = azure_manager
        self.influx_config = influx_config
        self.logger = logger
        self.processing_function = processing_function
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Create queues
        self.date_queue = DateRangeQueue()
        self.write_queue = InfluxDBWriteQueue(max_queue_size=max_write_queue_size)

        # Thread management
        self._worker_threads: list[threading.Thread] = []
        self._writer_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

        # InfluxDB client (initialized when needed)
        self._influx_client = None

        self.logger.info(
            f"ThreadCoordinator initialized with {num_backfill_workers} workers"
        )

    def start_backfill(self, start_date: datetime, end_date: datetime, chunk_days: int):
        """
        Start backfill processing with worker threads.

        Args:
            start_date: Start date for backfill
            end_date: End date for backfill
            chunk_days: Number of days per chunk
        """
        self.logger.info(
            f"Starting backfill from {start_date} to {end_date} "
            f"with {chunk_days}-day chunks"
        )

        # Populate date queue
        self.date_queue.populate(start_date, end_date, chunk_days)

        # Start writer thread
        self._start_writer_thread()

        # Start backfill worker threads
        for worker_id in range(self.num_backfill_workers):
            thread = threading.Thread(
                target=self._backfill_worker,
                args=(worker_id,),
                name=f"BackfillWorker-{worker_id}",
                daemon=False,
            )
            thread.start()
            self._worker_threads.append(thread)
            self.logger.info(f"Started backfill worker {worker_id}")

    def _start_writer_thread(self):
        """Start the InfluxDB writer thread."""
        self._writer_thread = threading.Thread(
            target=self._influxdb_writer,
            name="InfluxDBWriter",
            daemon=False,
        )
        self._writer_thread.start()
        self.logger.info("Started InfluxDB writer thread")

    def _backfill_worker(self, worker_id: int):
        """
        Backfill worker function - processes date ranges from queue.

        Args:
            worker_id: Unique worker identifier
        """
        self.logger.info(f"Worker {worker_id} starting")

        while not self._shutdown_event.is_set():
            # Get next date range
            date_range = self.date_queue.get_next_range(timeout=1.0)

            if date_range is None:
                # Check if queue is truly empty
                if self.date_queue.is_empty():
                    self.logger.info(
                        f"Worker {worker_id} finished - no more date ranges"
                    )
                    break
                continue

            try:
                self.logger.debug(
                    f"Worker {worker_id} processing {date_range.start} to {date_range.end}"
                )

                # Process date range using streaming (yields batches)
                batch_count = 0
                for batch_data in self.processing_function(
                    self.azure_manager, date_range.start, date_range.end
                ):
                    # Submit batch to write queue (with retry on Queue.Full)
                    self._submit_write_with_retry(batch_data, worker_id)
                    batch_count += 1
                    self.logger.debug(
                        f"Worker {worker_id} submitted batch {batch_count} from date range"
                    )

                # Mark date range as completed
                self.date_queue.mark_completed()
                self.logger.debug(
                    f"Worker {worker_id} completed date range ({batch_count} batches)"
                )

            except Exception as e:
                self.logger.error(
                    f"Worker {worker_id} failed processing date range: {e}"
                )

                # Retry logic
                if date_range.retry_count < self.max_retries:
                    # Exponential backoff
                    delay = self.retry_delay * (2**date_range.retry_count)
                    self.logger.warning(
                        f"Requeueing date range after {delay}s "
                        f"(attempt {date_range.retry_count + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    self.date_queue.requeue_failed(date_range, str(e))
                else:
                    # Move to dead-letter queue
                    self.logger.error(
                        "Date range exceeded max retries, moving to dead-letter queue"
                    )
                    self.date_queue.move_to_dead_letter(date_range)

        self.logger.info(f"Worker {worker_id} shutting down")

    def _submit_write_with_retry(self, fcd_data: dict, worker_id: int):
        """
        Submit write request with retry on Queue.Full.

        Args:
            fcd_data: FCD data to write
            worker_id: Worker submitting the request
        """
        retry_count = 0
        max_write_retries = 5

        while retry_count < max_write_retries:
            try:
                self.write_queue.put_write_request(
                    fcd_data, worker_id, timeout=FCD_WRITE_QUEUE_TIMEOUT
                )
                return
            except Exception as e:
                retry_count += 1
                if retry_count >= max_write_retries:
                    self.logger.error(
                        f"Worker {worker_id} failed to submit write after "
                        f"{max_write_retries} retries: {e}"
                    )
                    raise
                # Exponential backoff
                delay = 1 * (2**retry_count)
                self.logger.warning(
                    f"Write queue full, retrying in {delay}s (attempt {retry_count})"
                )
                time.sleep(delay)

    def _influxdb_writer(self):
        """InfluxDB writer thread - serializes writes from multiple workers."""
        self.logger.info("InfluxDB writer thread starting")

        while not self.write_queue.is_shutdown():
            request = self.write_queue.get_next_request(timeout=1.0)

            if request is None:
                continue

            try:
                # Write to InfluxDB (if client is initialized)
                if self._influx_client:
                    self._influx_client.write_fcd_data(request.fcd_data)

                self.write_queue.mark_completed(success=True)
                self.logger.debug(
                    f"Wrote data from worker {request.worker_id} to InfluxDB"
                )

            except Exception as e:
                self.logger.error(f"InfluxDB write failed: {e}")
                self.write_queue.mark_completed(success=False)

        self.logger.info("InfluxDB writer thread shutting down")

    def wait_for_backfill_completion(self, timeout: float | None = None) -> bool:
        """
        Wait for all backfill workers to complete.

        Args:
            timeout: Maximum time to wait (seconds), None for indefinite

        Returns:
            True if completed within timeout, False otherwise
        """
        start_time = time.time()

        for thread in self._worker_threads:
            if timeout is not None:
                elapsed = time.time() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    self.logger.warning("Backfill completion timeout reached")
                    return False
                thread.join(timeout=remaining)
            else:
                thread.join()

            if thread.is_alive():
                return False

        self.logger.info("All backfill workers completed")
        return True

    def shutdown(self, timeout: float = FCD_SHUTDOWN_TIMEOUT_SECONDS):
        """
        Gracefully shutdown all threads.

        Args:
            timeout: Maximum time to wait for threads to finish (seconds)
        """
        self.logger.info("Initiating graceful shutdown")
        self._shutdown_event.set()

        # Wait for workers to finish current tasks
        start_time = time.time()
        for thread in self._worker_threads:
            remaining = timeout - (time.time() - start_time)
            if remaining > 0:
                thread.join(timeout=remaining)

        # Shutdown write queue and wait for writer thread
        self.write_queue.shutdown()
        if self._writer_thread:
            remaining = timeout - (time.time() - start_time)
            if remaining > 0:
                self._writer_thread.join(timeout=remaining)

        self.logger.info("Shutdown complete")

    def is_shutdown(self) -> bool:
        """Check if shutdown has been initiated."""
        return self._shutdown_event.is_set()

    def get_progress_stats(self) -> dict:
        """
        Get current progress statistics.

        Returns:
            Dictionary with progress information
        """
        return {
            "date_queue": self.date_queue.get_stats(),
            "write_queue": self.write_queue.get_stats(),
            "workers_alive": sum(1 for t in self._worker_threads if t.is_alive()),
            "writer_alive": (
                self._writer_thread.is_alive() if self._writer_thread else False
            ),
            "dead_letter_count": len(self.date_queue.get_dead_letter_ranges()),
        }
