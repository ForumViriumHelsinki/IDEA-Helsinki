"""
Thread coordinator for multi-threaded FCD processing.

Orchestrates backfill workers, real-time workers, and InfluxDB writer thread.
"""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from idea_shared.lib.Constants.Constants import (
    FCD_MAX_CHUNK_RETRIES,
    FCD_MAX_WRITE_RETRIES,
    FCD_PROCESSING_BATCH_SIZE,
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
        batch_size: int = FCD_PROCESSING_BATCH_SIZE,
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
            batch_size: Number of blobs to process per batch
        """
        self.num_backfill_workers = num_backfill_workers
        self.azure_manager = azure_manager
        self.influx_config = influx_config
        self.logger = logger
        self.processing_function = processing_function
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.batch_size = batch_size

        # Create queues
        self.date_queue = DateRangeQueue()
        self.write_queue = InfluxDBWriteQueue(max_queue_size=max_write_queue_size)

        # Thread management
        self._worker_threads: list[threading.Thread] = []
        self._writer_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

        # Initialize InfluxDB client for writer thread (if config is complete)
        self._influx_client = None
        required_keys = ["url", "token", "org", "bucket"]
        if all(key in influx_config for key in required_keys):
            from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager

            self._influx_client = FCDInfluxDBManager(
                url=influx_config["url"],
                token=influx_config["token"],
                org=influx_config["org"],
                bucket=influx_config["bucket"],
            )
            self.logger.info("InfluxDB client initialized for writer thread")
        else:
            self.logger.warning(
                "InfluxDB config incomplete - writer thread will not persist data"
            )

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
                daemon=True,
            )
            thread.start()
            self._worker_threads.append(thread)
            self.logger.info(f"Started backfill worker {worker_id}")

    def _start_writer_thread(self):
        """Start the InfluxDB writer thread."""
        self._writer_thread = threading.Thread(
            target=self._influxdb_writer,
            name="InfluxDBWriter",
            daemon=True,
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
                # Check if queue is truly empty and all work is complete
                if self.date_queue.is_complete() and self.date_queue.is_empty():
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
                    self.azure_manager,
                    date_range.start,
                    date_range.end,
                    self.batch_size,
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

        while retry_count < FCD_MAX_WRITE_RETRIES:
            try:
                self.write_queue.put_write_request(
                    fcd_data, worker_id, timeout=FCD_WRITE_QUEUE_TIMEOUT
                )
                return
            except Exception as e:
                retry_count += 1
                if retry_count >= FCD_MAX_WRITE_RETRIES:
                    self.logger.error(
                        f"Worker {worker_id} failed to submit write after "
                        f"{FCD_MAX_WRITE_RETRIES} retries: {e}"
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
                    self._influx_client.write_fcd_model(request.fcd_data)

                self.write_queue.mark_completed(success=True)
                self.logger.debug(
                    f"Wrote data from worker {request.worker_id} to InfluxDB"
                )

            except Exception as e:
                self.logger.error(f"InfluxDB write failed: {e}")
                self.write_queue.mark_completed(success=False)

        self.logger.info("InfluxDB writer thread shutting down")

    def start_realtime(
        self,
        update_function,
        update_interval_minutes: int = 5,
    ):
        """Start real-time continuous update worker.

        Launches a daemon-less thread that runs a perpetual update cycle,
        calling the provided update function each interval. Can run concurrently
        with backfill workers.

        Args:
            update_function: Callable that performs one update cycle.
                Signature: () -> bool (returns True on success)
            update_interval_minutes: Minutes between update cycles
        """
        self._realtime_update_function = update_function
        self._realtime_interval = update_interval_minutes
        self._realtime_worker_thread = threading.Thread(
            target=self._realtime_worker,
            name="RealTimeWorker",
            daemon=False,
        )
        self._realtime_worker_thread.start()
        self.logger.info(
            f"Real-time worker started (interval: {update_interval_minutes}m)"
        )

    def _realtime_worker(self):
        """Real-time worker thread that runs continuous update cycles.

        Similar to single-threaded mode's update loop but coordinates
        shutdown with the ThreadCoordinator's shutdown event.
        """
        self.logger.info("Real-time worker running")

        while not self._shutdown_event.is_set():
            try:
                success = self._realtime_update_function()
                if success:
                    self.logger.info("Real-time update cycle completed successfully")
                else:
                    self.logger.warning("Real-time update cycle returned failure")

            except Exception as e:
                self.logger.error(f"Real-time worker error: {e}")

            # Calculate next aligned cycle time
            current = datetime.now(UTC)
            minutes_to_add = self._realtime_interval - (
                current.minute % self._realtime_interval
            )
            next_cycle = (current + timedelta(minutes=minutes_to_add)).replace(
                second=0, microsecond=0
            )

            # Sleep until next cycle or shutdown
            while datetime.now(UTC) < next_cycle and not self._shutdown_event.is_set():
                time.sleep(1)

        self.logger.info("Real-time worker stopped")

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

        # Wait for real-time worker to finish current cycle
        start_time = time.time()
        if (
            hasattr(self, "_realtime_worker_thread")
            and self._realtime_worker_thread.is_alive()
        ):
            remaining = timeout - (time.time() - start_time)
            if remaining > 0:
                self._realtime_worker_thread.join(timeout=remaining)
                self.logger.info("Real-time worker stopped")

        # Wait for workers to finish current tasks
        for thread in self._worker_threads:
            remaining = timeout - (time.time() - start_time)
            if remaining > 0:
                thread.join(timeout=remaining)

        # Wait for all pending writes to complete before shutting down
        self.logger.info("Waiting for pending writes to complete...")
        try:
            remaining = timeout - (time.time() - start_time)
            if remaining > 0:
                # Wait for write queue to drain
                self.write_queue._queue.join()
                self.logger.info("All pending writes completed")
        except Exception as e:
            self.logger.warning(f"Error waiting for write queue to drain: {e}")

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
