# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import asyncio
from datetime import UTC, datetime, timedelta

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.IdeaHelsinkiRoadSegment import IdeaHelsinkiRoadSegment
from idea_shared.classes.Logger import Logger
from idea_shared.resilience import CircuitBreaker
from idea_shared.resilience.retry import ErrorTracker, calculate_backoff
from idea_shared.threading.file_locks import read_json_with_retry


class IdeaHelsinkiManager:
    """Configuration constants for resilience patterns."""

    # Maximum consecutive errors before escalating worker failure
    _WORKER_MAX_ERRORS = 10
    # Maximum consecutive errors before escalating main loop failure
    _MAIN_LOOP_MAX_ERRORS = 10
    """
    Manages IdeaHelsinkiRoadSegments objects and updates them with the latest traffic disturbance information.
    Creates and removes IdeaHelsinkiRoadSegments objects based on the latest traffic disturbance information.
    The class can focus only on specific road segments, it a "target_fcd_segments" list is provided to it.
    This is the go-go-jee-jee manager of the program.
    """

    def __init__(
        self,
        validation_frequency: int,
        profile_time_frame_weeks: int,
        profile_end_lead_time_hours: int,
        validation_max_age_days: int,
        traffic_disturbance_data_file_location: str,
        traffic_disturbance_update_frequency: int,
        db_org: str,
        db_url: str,
        db_fcd_bucket: str,
        db_fcd_token: str,
        db_validation_bucket: str,
        db_validation_token: str,
        target_fcd_segments: list | None = None,
    ):
        self.validation_frequency = validation_frequency
        self.profile_time_frame_weeks = profile_time_frame_weeks
        self.profile_end_lead_time_hours = profile_end_lead_time_hours
        self.validation_max_age_days = validation_max_age_days
        self.traffic_disturbance_data_file_location = (
            traffic_disturbance_data_file_location
        )
        self.traffic_disturbance_update_frequency = traffic_disturbance_update_frequency
        self.db_org: str = db_org
        self.db_url: str = db_url
        self.db_fcd_bucket: str = db_fcd_bucket
        self.db_fcd_token: str = db_fcd_token
        self.db_validation_bucket: str = db_validation_bucket
        self.db_validation_token: str = db_validation_token
        self.target_fcd_segments = target_fcd_segments
        self.active_segments = {}  # Stores segment_id -> segment_object
        self.logger = Logger(__name__)
        # Health monitoring attributes
        self.last_cycle_time = datetime.now(UTC)
        self.last_discovery_time = None
        # Resilience infrastructure
        self.error_tracker = ErrorTracker(max_consecutive=10)
        self.circuit_breaker = CircuitBreaker(
            name="manager",
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=3,
        )

    def _get_disturbance_data(self, file_path: str) -> dict:
        """
        Loads the latest validated disturbance data with intersections.

        Args:
            file_path: Path to the JSON file containing the latest validated disturbance data.

        returns:
            Dictionary containing the latest validated disturbance data.
        """
        data = read_json_with_retry(file_path)
        if data is None:
            self.logger.error(
                f"Could not load disturbance data from '{file_path}'"
            )
            return {}
        if not isinstance(data, dict):
            self.logger.error(
                f"Disturbance data from '{file_path}' is not a dict"
            )
            return {}
        return data

    async def _wait_for_next_management_cycle(self):
        """
        Void method that pauses the manager until the next management cycle.
        Bases the wait time on the "clock" to determine the number of seconds it needs to sleep.
        Example: a 60-minute wait is always the next hour on the clock (15:00, 16:00 etc.), regardless of the current time.
        Example: A function called at 16:47 will wait until 17:00.
        Based on the traffic_disturbance_update_frequency.
        """
        now = datetime.now(UTC)
        minutes_to_add = self.traffic_disturbance_update_frequency - (
            now.minute % self.traffic_disturbance_update_frequency
        )

        resume_time = now + timedelta(minutes=minutes_to_add)
        resume_time = resume_time.replace(second=0, microsecond=0)

        if resume_time <= now:
            resume_time += timedelta(minutes=self.traffic_disturbance_update_frequency)

        self.logger.info(
            f"Pausing... Next management cycle at {resume_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await asyncio.sleep((resume_time - now).total_seconds())

    async def _run_management_cycle_with_error_isolation(self):
        """
        Run a single management cycle with error isolation.
        Wrapped by run_main_loop for resilience.
        """
        # Update cycle time for health monitoring
        self.last_cycle_time = datetime.now(UTC)

        self.logger.info(
            "Manager starting new cycle: discovering and updating tasks."
        )

        # Load the latest disturbance data with intersections
        disturbance_data = self._get_disturbance_data(
            self.traffic_disturbance_data_file_location
        )

        # Group disturbances by segment ID, if target_fcd_segments is specified, focuses only on them.
        segments_to_process = {}

        for segment_id, data in disturbance_data.get("segmentId", {}).items():
            if self.target_fcd_segments:
                if (
                    segment_id in self.target_fcd_segments
                    or not self.target_fcd_segments
                ):
                    segments_to_process[segment_id] = data.get(
                        "detailedCollisions", []
                    )
            else:
                segments_to_process[segment_id] = data.get("detailedCollisions", [])

        # Update and manage the segment tasks
        current_ids = set(segments_to_process.keys())
        active_ids = set(self.active_segments.keys())

        # Deactivate and remove tasks for segments that are no longer listed containing disturbance.

        # RFC: Should this be based on or with the road segment class objects own "active" status?
        # Program vise there is not that much of a difference, since the object ends its validation cycle once the end date has passed.
        # This current approach is the one decided on in the preliminary development meeting, when the disturbance is removed from the listing,
        # the object is terminated (or schwarzeneggered [patent pending...]).

        for segment_id in active_ids - current_ids:
            self.logger.info(
                f"Disturbance ended for segment {segment_id}. Deactivating task."
            )
            active_segment = self.active_segments.pop(segment_id)
            active_segment["task"].cancel()  # Stop the asyncio task (worker loop)

        # Create or update tasks for segments that are listed for processing
        for segment_id, disturbances in segments_to_process.items():
            if segment_id in self.active_segments:
                # If already active, update it with the latest disturbance info
                self.active_segments[segment_id]["instance"].update_segment(
                    disturbances
                )
            else:
                # If new, create the class instance and start its lifecycle task
                self.logger.info(
                    f"New disturbance detected for segment {segment_id}. Starting validation task."
                )
                # Track discovery time for health monitoring
                self.last_discovery_time = datetime.now(UTC)
                segment_instance = IdeaHelsinkiRoadSegment(
                    segment_id=segment_id,
                    reported_disturbances=disturbances,
                    validation_frequency=self.validation_frequency,
                    validation_max_age_days=self.validation_max_age_days,
                    profile_time_frame_weeks=self.profile_time_frame_weeks,
                    profile_end_lead_time_hours=self.profile_end_lead_time_hours,
                    db_org=self.db_org,
                    db_url=self.db_url,
                    db_fcd_bucket=self.db_fcd_bucket,
                    db_fcd_token=self.db_fcd_token,
                    db_validation_bucket=self.db_validation_bucket,
                    db_validation_token=self.db_validation_token,
                )
                # Wrap worker lifecycle with error isolation
                task = asyncio.create_task(
                    self._run_worker_with_error_isolation(segment_instance)
                )
                self.active_segments[segment_id] = {
                    "instance": segment_instance,
                    "task": task,
                }

        self.logger.info(
            f"Manager cycle complete. Active tasks: {len(self.active_segments)}."
        )

    async def _run_worker_with_error_isolation(
        self, segment_instance: IdeaHelsinkiRoadSegment
    ):
        """
        Run a worker lifecycle with error isolation and retry logic.

        Prevents individual worker failures from affecting the main manager loop.
        Implements exponential backoff for worker restart on failure.
        """
        segment_id = segment_instance.segment_id
        consecutive_errors = 0

        try:
            while consecutive_errors < self._WORKER_MAX_ERRORS:
                try:
                    await segment_instance.run_lifecycle()
                    # If run_lifecycle exits normally, reset error count
                    consecutive_errors = 0
                except asyncio.CancelledError:
                    # Always propagate cancellation
                    self.logger.info(
                        f"Worker for segment {segment_id} cancelled gracefully"
                    )
                    raise
                except Exception as e:
                    consecutive_errors += 1
                    self.logger.error(
                        f"Worker error for segment {segment_id} "
                        f"(attempt {consecutive_errors}/{self._WORKER_MAX_ERRORS}): {e}",
                        exc_info=True,
                    )

                    if consecutive_errors >= self._WORKER_MAX_ERRORS:
                        self.logger.error(
                            f"Worker for segment {segment_id} exceeded maximum consecutive errors. "
                            f"Terminating worker."
                        )
                        break

                    # Exponential backoff with jitter before retry
                    backoff = calculate_backoff(
                        attempt=consecutive_errors, base_delay=5.0, max_delay=60.0
                    )
                    self.logger.info(
                        f"Restarting worker for segment {segment_id} in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
        except asyncio.CancelledError:
            # Final cleanup on cancellation
            self.logger.info(f"Worker cleanup for segment {segment_id} complete")
            raise

    async def run_main_loop(self):
        """
        The main orchestration loop for managing IdeaHelsinkiRoadSegments.

        Includes resilience patterns:
        - Exception handling to prevent cascade shutdown
        - Error tracking for adaptive backoff
        - Circuit breaker integration (future enhancement)
        """
        while True:
            try:
                await self._run_management_cycle_with_error_isolation()
                self.error_tracker.record_success()
            except asyncio.CancelledError:
                # Always propagate cancellation (from SIGTERM/SIGINT)
                self.logger.info("Main loop cancelled, shutting down gracefully")
                raise
            except Exception as e:
                self.error_tracker.record_failure()
                self.logger.error(
                    f"Main loop error (consecutive: {self.error_tracker.consecutive_errors}): {e}",
                    exc_info=True,
                )

                # Check if we should escalate (systemic failure)
                if self.error_tracker.should_escalate():
                    self.logger.critical(
                        f"Main loop exceeded {self.error_tracker.max_consecutive} consecutive errors. "
                        f"Exiting to trigger pod restart."
                    )
                    raise

                # Exponential backoff with jitter based on error frequency
                backoff = calculate_backoff(
                    attempt=self.error_tracker.consecutive_errors,
                    base_delay=5.0,
                    max_delay=60.0,
                )
                self.logger.warning(
                    f"Main loop will retry in {backoff:.1f}s "
                    f"(error count: {self.error_tracker.consecutive_errors})"
                )
                await asyncio.sleep(backoff)
                continue

            # Take a break and enjoy the bits and bytes.
            await self._wait_for_next_management_cycle()

    async def get_worker_health_stats(self):
        """
        Return health statistics for monitoring.
        Used by health checks to assess the state of the service.
        """
        return {
            "total_workers": len(self.active_segments),
            "last_discovery": self.last_discovery_time.isoformat()
            if self.last_discovery_time
            else None,
            "last_cycle": self.last_cycle_time.isoformat()
            if self.last_cycle_time
            else None,
            "active_segments": list(self.active_segments.keys()),
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "error_tracker": self.error_tracker.get_stats(),
        }
