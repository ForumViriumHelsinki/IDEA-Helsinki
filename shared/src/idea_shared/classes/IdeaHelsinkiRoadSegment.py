# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import asyncio
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager
from idea_shared.classes.Logger import Logger
from idea_shared.data.profile_serialization import (
    deserialize_profile,
    serialize_profile,
)
from idea_shared.lib import IdeaHelsinkiDataPreProcessor
from idea_shared.lib.Constants.Constants import (
    INFLUX_FCD_MEASUREMENT,
    INFLUX_VALIDATION_MEASUREMENT,
)

# ------------------------------------------------------#
# ------------- PROJECT MODULE IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.lib.idea.exceptions import IDEAError
from idea_shared.lib.idea.profile import util as idea_util
from idea_shared.lib.idea.profile.profile import calculate_profile_from_hourly
from idea_shared.lib.idea.validation.validation import validate_roadwork
from idea_shared.resilience import CircuitBreaker
from idea_shared.resilience.retry import ErrorTracker, calculate_backoff

if TYPE_CHECKING:
    from idea_shared.data.repositories import ProfileRepository


class IdeaHelsinkiRoadSegment:
    """Use the IDEA algorithm to profile and validate a single road segment.

    Autonomous in nature, determines the necessary start and end dates based on
    the road disturbances associated with it.
    """

    # Number of weeks per chunk when fetching 26-week profile data
    _PROFILING_CHUNK_WEEKS = 4

    def __init__(
        self,
        segment_id: str,
        reported_disturbances: list,
        validation_frequency: int,
        profile_time_frame_weeks: int,
        profile_end_lead_time_hours: int,
        db_org: str,
        db_url: str,
        db_fcd_bucket: str,
        db_fcd_token: str,
        db_validation_bucket: str,
        db_validation_token: str,
        profiling_semaphore: asyncio.Semaphore | None = None,
        validation_semaphore: asyncio.Semaphore | None = None,
        validation_history_weeks: int = 4,
        profile_repository: "ProfileRepository | None" = None,
    ):
        self.segment_id = segment_id
        self.validation_frequency: int = validation_frequency
        self.profile_time_frame_weeks: int = profile_time_frame_weeks
        self.profile_end_lead_time_hours: int = profile_end_lead_time_hours
        self.profile_repository = profile_repository
        self.db_org: str = db_org
        self.db_url: str = db_url
        self.db_fcd_bucket: str = db_fcd_bucket
        self.db_fcd_token: str = db_fcd_token
        self.db_validation_bucket: str = db_validation_bucket
        self.db_validation_token: str = db_validation_token
        self.disturbance_start_date, self.disturbance_end_date = (
            IdeaHelsinkiDataPreProcessor.determine_disturbance_dates(
                reported_disturbances=reported_disturbances
            )
        )
        # End point for the profile history, (example. datetime 2025-6-10), based on the disturbance start date.
        self.profiling_end_date = (
            IdeaHelsinkiDataPreProcessor.calculate_profiling_end_date(
                disturbance_start_date=self.disturbance_start_date,
                lead_time_hours=self.profile_end_lead_time_hours,
            )
        )
        # Starting point for the profile history, (example. datetime 2025-1-10), based on the profiling_end_date.
        self.profiling_start_date = (
            IdeaHelsinkiDataPreProcessor.calculate_profiling_start_date(
                profiling_end_date=self.profiling_end_date,
                profile_time_frame_weeks=self.profile_time_frame_weeks,
            )
        )
        # This attribute init also checks if the segment has been already profiled (happens in cases when the program has been terminated unexpectedly)
        self.last_validation_update: datetime | None = None
        self.segment_profile: pd.DataFrame | None = None
        self.last_segment_validation: pd.DataFrame | None = None
        self.segment_active: bool = True
        self.profiling_semaphore = profiling_semaphore
        self.validation_semaphore = validation_semaphore
        self.validation_history_weeks = validation_history_weeks
        self.logger = Logger(f"Helsinki IDEA road segment ID : {self.segment_id}")
        # Resilience infrastructure
        self.error_tracker = ErrorTracker(max_consecutive=10)
        self.db_circuit_breaker = CircuitBreaker(
            name=f"influxdb-{segment_id}",
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=3,
        )
        self.logger.info("Segment object created")

    def _initialize_last_validation_update(self, current_date: datetime) -> None:
        """Sets the initial last_validation_update date, clamping it to the history window.

        Called once when last_validation_update is None and validation is ready to begin.
        For long-running disturbances this prevents loading months of data.

        When validation_history_weeks is 0, no history is recalculated: the start
        point is set to one validation cycle before now so the first query captures
        only the freshest data.
        """
        if self.validation_history_weeks == 0:
            # No history: start from one cycle ago so the first query is non-empty.
            self.last_validation_update = current_date - timedelta(
                minutes=self.validation_frequency
            )
            return
        if self.profiling_end_date.date() < current_date.date():
            # Increment one day to avoid overlapping with the segment profiling.
            candidate = self.profiling_end_date + timedelta(days=1)
            # Clamp: don't recalculate further back than validation_history_weeks.
            earliest_allowed = current_date - timedelta(
                weeks=self.validation_history_weeks
            )
            self.last_validation_update = max(candidate, earliest_allowed)
        else:
            # profiling_end_date is today: start one cycle before now so the
            # first validation query covers a non-empty time window.
            # Setting last_validation_update = current_date would produce an
            # empty range (start == stop) and cause InfluxDB to return 400.
            self.last_validation_update = current_date - timedelta(
                minutes=self.validation_frequency
            )

    async def _wait_for_next_cycle(self):
        """Pause the road segment until the next validation cycle.

        Base the wait time on the clock to determine the number of seconds to sleep.
        Example: a 5-minute wait is always the five minutes on the clock (15:05, 15:10 etc.).
        A function called at 16:47 will wait until 16:50. Based on the validation_frequency.
        """
        now = datetime.now(UTC)
        minutes_to_add = self.validation_frequency - (
            now.minute % self.validation_frequency
        )

        resume_time = now + timedelta(minutes=minutes_to_add)
        resume_time = resume_time.replace(second=0, microsecond=0)

        if resume_time <= now:
            resume_time += timedelta(minutes=self.validation_frequency)

        self.logger.info(
            f"Pausing. Next validation cycle at {resume_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await asyncio.sleep((resume_time - now).total_seconds())

    async def __validate_segment(self, current_time: datetime):
        """A void method that profiles and validates a single road segment.

        Args:
            current_time (datetime): The current time UTC.

        """
        # Sleep for 10 seconds before beginning validation, so the current segment data is updated and available.
        await asyncio.sleep(10)

        needs_generation = True
        existing_serialized_profile: bytes | None = None
        if self.segment_profile is not None:
            needs_generation = False
        elif self.profile_repository is not None:
            existing_serialized_profile = await asyncio.to_thread(
                self.profile_repository.get_profile, self.segment_id
            )
            if existing_serialized_profile is not None:
                needs_generation = False

        if needs_generation:
            self.logger.info("Generating segment profile...")
            async with (
                self.profiling_semaphore
                if self.profiling_semaphore is not None
                else nullcontext()
            ):
                hourly_profile_data = await self.__get_hourly_profile_data()
                if hourly_profile_data is not None and not hourly_profile_data.empty:
                    try:
                        profile = await asyncio.to_thread(
                            calculate_profile_from_hourly,
                            hourly_df=hourly_profile_data,
                        )
                    except IDEAError as e:
                        self.logger.error(
                            f"Profile validation failed: {e.message}. "
                            f"Segment had {len(hourly_profile_data)} hourly data points for period "
                            f"{self.profiling_start_date} to {self.profiling_end_date}. "
                            f"This typically means the FCD coverage quality is too low "
                            f"(too many gaps or zeros in the data)."
                        )
                        return
                    finally:
                        del hourly_profile_data

                    if not profile.empty:
                        self.logger.info("Segment profile generated")
                        if self.profile_repository is not None:
                            try:
                                serialized_profile = serialize_profile(profile)
                                now = datetime.now(UTC)
                                now_str = now.isoformat()
                                # Profile expires 1 week after generation. Can be re-generated if needed.
                                expires_str = (now + timedelta(days=7)).isoformat()
                                await asyncio.to_thread(
                                    self.profile_repository.save_profile,
                                    segment_id=self.segment_id,
                                    profile_data=serialized_profile,
                                    computed_at=now_str,
                                    expires_at=expires_str,
                                )
                                # Reuse the just-serialized bytes for the validation
                                # phase below to avoid a redundant DB fetch.
                                existing_serialized_profile = serialized_profile
                                self.segment_profile = (
                                    None  # explicit None to drop memory
                                )
                            except Exception as e:
                                self.logger.error(
                                    f"Failed to save profile to SQLite: {e}"
                                )
                                # fallback to memory if save fails
                                self.segment_profile = profile
                        else:
                            self.segment_profile = profile
                    else:
                        self.logger.error("IDEA returned an empty segment profile")
                        return
                else:
                    # No FCD data available at all for this segment/period
                    self.logger.error(
                        f"No FCD data available for segment. "
                        f"Query returned empty/None for period "
                        f"{self.profiling_start_date} to {self.profiling_end_date}."
                    )
                    return
        else:
            self.logger.debug(
                f"Segment profile fetched from database for segment {self.segment_id}"
            )

        assert self.last_validation_update is not None, (
            "last_validation_update must be set before validation"
        )

        self.logger.info(
            f"Validating segment for timestamps {self.last_validation_update} - {current_time} "
        )
        segment_data_to_validate = (
            await self.__get_idea_formated_segment_data_from_influxdb(
                segment_id=self.segment_id,
                start_time=self.last_validation_update,
                end_time=current_time,
            )
        )

        if self.last_segment_validation is None:
            async with (
                self.validation_semaphore
                if self.validation_semaphore is not None
                else nullcontext()
            ):
                self.last_segment_validation = (
                    await self.__get_validation_dataframe_from_influxdb(
                        segment_id=self.segment_id,
                        start_time=self.last_validation_update,
                        end_time=current_time,
                    )
                )

        if segment_data_to_validate is not None and not segment_data_to_validate.empty:
            active_profile = self.segment_profile
            if self.profile_repository is not None:
                serialized_data = existing_serialized_profile
                if serialized_data is None:
                    serialized_data = await asyncio.to_thread(
                        self.profile_repository.get_profile, self.segment_id
                    )
                if serialized_data is not None:
                    try:
                        active_profile = deserialize_profile(serialized_data)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to deserialize profile for validation: {e}"
                        )
                        return

            if active_profile is None:
                self.logger.error("Active profile is None during validation phase.")
                return

            try:
                segment_validation = await asyncio.to_thread(
                    validate_roadwork,
                    fcd_during_roadwork=segment_data_to_validate,
                    profile=active_profile,
                    last_segment_validation=self.last_segment_validation
                    if self.last_segment_validation is not None
                    else pd.DataFrame(),
                )
            finally:
                # Explicitly delete the local DataFrame reference to ensure garbage
                # collection can reclaim the memory immediately.
                del active_profile

            if not segment_validation.empty:
                if await self.__write_dataframe_to_influxdb(
                    df=segment_validation,
                    segment_id=self.segment_id,
                    measurement_name=INFLUX_VALIDATION_MEASUREMENT,
                ):
                    self.logger.info("Segment validation updated to database.")
                    self.last_segment_validation = segment_validation
                    self.last_validation_update = current_time
                else:
                    self.logger.info("Segment validation NOT updated to database.")
            else:
                self.logger.info("IDEA returned an empty segment validation!")
        else:
            self.logger.info(
                "Segment validation data could not be fetched from database."
            )

    async def run_lifecycle(self):
        """Run the main loop for profiling and validating the FCD segment.

        Run as long as the reported disturbance is active.

        Includes resilience patterns:
        - Exception handling to prevent worker crashes
        - Error tracking for adaptive backoff
        - Circuit breaker integration for database operations
        """
        self.logger.info("Starting main loop...")

        try:
            while True:
                try:
                    # Update current time in loop
                    current_date = datetime.now(UTC)

                    # Check is segment profiling and validation can be done
                    # Determine if the segment has history enough for the IDEA algorithm.
                    # Fetch the latest measurement time for the segment.
                    segment_history_start_date = (
                        await self.__get_segment_first_timestamp_from_influxdb(
                            segment_id=self.segment_id
                        )
                    )

                    valid_segment = segment_history_start_date is not None and (
                        segment_history_start_date
                        + timedelta(weeks=self.profile_time_frame_weeks)
                        <= current_date
                    )

                    if valid_segment:
                        if self.profiling_end_date.date() <= current_date.date():
                            # self.last_validation_update variable can be None if this is the first run after object init, or the last influxDB query returned None.
                            # Otherwise, the variable is incremented (datetime) after each validation.
                            if self.last_validation_update is None:
                                self._initialize_last_validation_update(current_date)

                            await self.__validate_segment(current_date)
                        else:
                            self.logger.info(
                                f"Segment validation NOT started, disturbance validation is set to start at {self.profiling_end_date.date()}"
                            )
                    else:
                        self.logger.warning(
                            f"Segment is not valid for profiling and validation!!! Segment history start date: {segment_history_start_date}"
                        )

                    # Successful cycle, reset error tracker
                    self.error_tracker.record_success()

                except asyncio.CancelledError:
                    # Always propagate cancellation
                    self.logger.info("Lifecycle cancelled, performing cleanup")
                    raise
                except Exception as e:
                    self.error_tracker.record_failure()
                    self.logger.error(
                        f"Lifecycle error (consecutive: {self.error_tracker.consecutive_errors}): {e}",
                        exc_info=True,
                    )

                    # Check if we should escalate (systemic failure)
                    if self.error_tracker.should_escalate():
                        self.logger.error(
                            f"Worker exceeded {self.error_tracker.max_consecutive} consecutive errors. "
                            f"Exiting worker lifecycle."
                        )
                        raise

                    # Exponential backoff with jitter based on error frequency
                    backoff = calculate_backoff(
                        attempt=self.error_tracker.consecutive_errors,
                        base_delay=2.0,
                        max_delay=60.0,
                    )
                    self.logger.warning(
                        f"Worker will retry in {backoff:.1f}s "
                        f"(error count: {self.error_tracker.consecutive_errors})"
                    )
                    await asyncio.sleep(backoff)
                    continue

                await self._wait_for_next_cycle()

        except asyncio.CancelledError:
            # Final cleanup on cancellation
            self.logger.info("Lifecycle cleanup complete")
            raise

        # Once the main loop has finished, the segment deactivates itself and can be removed from processing.
        # This means there is no more go-go-jee-jee for this segment :(

        # self.logger.info("Main loop finished. Disturbance period has ended.")
        # self.segment_active = False

    async def __write_dataframe_to_influxdb(
        self, df: pd.DataFrame, segment_id: str, measurement_name: str
    ) -> bool:
        """Writes a pandas dataframe to the InfluxDB database.

        Args:
            df (pandas.DataFrame): The IDEA validation dataframe to write to the database.
            segment_id (str): The FCD segment ID.
            measurement_name (str): The name of the measurement to write to the database.

        Returns:
            bool: True if the writing was successful.

        """
        try:
            # Use circuit breaker to protect against InfluxDB failures
            async with self.db_circuit_breaker:
                with FCDInfluxDBManager(
                    url=self.db_url,
                    token=self.db_validation_token,
                    org=self.db_org,
                    bucket=self.db_validation_bucket,
                ) as manager:
                    if not await asyncio.to_thread(manager.check_connection):
                        self.logger.error("FCD database connection error!")
                        return False
                    await asyncio.to_thread(
                        manager.write_dataframe,
                        df=df,
                        segment_id=segment_id,
                        measurement_name=measurement_name,
                    )
                    return True
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")
            return False

    async def __get_segment_last_timestamp_from_influxdb(
        self, segment_id: str
    ) -> datetime | None:
        """Retrieves the last segment timestamp from the InfluxDB database. Note that this is the measurement timestamp.

        Args:
            segment_id (str): The FCD segment ID.

        Returns:
            datetime: The last segment measurement timestamp or None if not available (Segment is not in the database).

        """
        segment_date = None

        try:
            # Use circuit breaker to protect against InfluxDB failures
            async with self.db_circuit_breaker:
                with FCDInfluxDBManager(
                    url=self.db_url,
                    token=self.db_fcd_token,
                    org=self.db_org,
                    bucket=self.db_fcd_bucket,
                ) as manager:
                    if not await asyncio.to_thread(manager.check_connection):
                        self.logger.error("FCD database connection error!")
                        return None
                    segment_date = await asyncio.to_thread(
                        manager.get_last_segment_update_timestamp,
                        segment_id=segment_id,
                        measurement_name=INFLUX_FCD_MEASUREMENT,
                    )
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")

        return segment_date

    async def __get_segment_first_timestamp_from_influxdb(
        self, segment_id: str
    ) -> datetime | None:
        """Retrieves the first segment timestamp from the InfluxDB database. Note that this is the measurement timestamp.

        Args:
            segment_id (str): The FCD segment ID.

        Returns:
            datetime: The first segment measurement timestamp or None if not available (Segment is not in the database).

        """
        segment_date = None

        try:
            # Use circuit breaker to protect against InfluxDB failures
            async with self.db_circuit_breaker:
                with FCDInfluxDBManager(
                    url=self.db_url,
                    token=self.db_fcd_token,
                    org=self.db_org,
                    bucket=self.db_fcd_bucket,
                ) as manager:
                    if not await asyncio.to_thread(manager.check_connection):
                        self.logger.error("FCD database connection error!")
                        return None
                    segment_date = await asyncio.to_thread(
                        manager.get_first_segment_update_timestamp,
                        segment_id=segment_id,
                        measurement_name=INFLUX_FCD_MEASUREMENT,
                    )
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")

        return segment_date

    async def __get_hourly_profile_data(self) -> pd.DataFrame | None:
        """Fetch the full profiling period in chunks and pre-aggregate to hourly resolution.

        Use chunks defined by _PROFILING_CHUNK_WEEKS to reduce peak memory.

        For example, with 4-week chunks, this reduces peak memory by ~12× compared
        to loading the full 26-week DataFrame at once: each raw chunk (~3,000 rows)
        is reduced to hourly aggregates (~672 rows) before the next chunk is fetched.

        Returns:
            A concatenated hourly DataFrame with columns:
            ``hour_of_date``, ``fcd_mean``, ``max_consecutive_zeros``,
            ``max_consecutive_zeros_or_ones``.
            Returns None if no chunks contain data.

        """
        hourly_chunks: list[pd.DataFrame] = []
        current = self.profiling_start_date

        while current < self.profiling_end_date:
            chunk_end = min(
                current + timedelta(weeks=self._PROFILING_CHUNK_WEEKS),
                self.profiling_end_date,
            )

            chunk_df = await self.__get_idea_formated_segment_data_from_influxdb(
                segment_id=self.segment_id,
                start_time=current,
                end_time=chunk_end,
            )

            if chunk_df is not None and not chunk_df.empty:
                interpolated = idea_util.interpolate_missing_minutes(
                    chunk_df, current, chunk_end
                )
                filled = idea_util.fill_nan_columns_with_zeros(
                    interpolated, column_subset=["fcd"]
                )
                hourly = idea_util.aggregate_by_hour(filled)
                hourly_chunks.append(hourly)
                del chunk_df, interpolated, filled

            current = chunk_end

        if not hourly_chunks:
            return None

        return pd.concat(hourly_chunks, ignore_index=True)

    async def __get_idea_formated_segment_data_from_influxdb(
        self, segment_id: str, start_time: datetime, end_time: datetime
    ) -> pd.DataFrame | None:
        """Retrieves measurement data from the InfluxDB database for a single segment.

        Args:
            segment_id (str): The FCD segment ID.
            start_time (datetime): The start time for the query.
            end_time (datetime): The end time for the query.

        Returns:
            pd.DataFrame or None if the query was unsuccessful.

            NOTE: This function returns the date frame in "IDEA" FCD format:

            '';'fcd;
            datetime;integer
            datetime;integer

        """
        try:
            # Use circuit breaker to protect against InfluxDB failures
            async with self.db_circuit_breaker:
                with FCDInfluxDBManager(
                    url=self.db_url,
                    token=self.db_fcd_token,
                    org=self.db_org,
                    bucket=self.db_fcd_bucket,
                ) as manager:
                    if not await asyncio.to_thread(manager.check_connection):
                        self.logger.error("FCD database connection error!")
                        return None

                    segment_data_df = await asyncio.to_thread(
                        manager.get_segment_data_dataframe,
                        segment_id=segment_id,
                        measurement_name=INFLUX_FCD_MEASUREMENT,
                        start_time=start_time,
                        end_time=end_time,
                        latest_only=False,
                        query_fields=["fcd_coverage"],
                        interval_minutes=self.validation_frequency,
                    )

                    if segment_data_df is not None and not segment_data_df.empty:
                        segment_data_df.set_index("_time", inplace=True)
                        segment_data_df.index.name = ""
                        segment_data_df.rename(
                            columns={"fcd_coverage": "fcd"}, inplace=True
                        )
                        return segment_data_df
                    else:
                        self.logger.warning("FCD database query returned no results")
                        return None
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")
            return None

    async def __get_validation_dataframe_from_influxdb(
        self,
        segment_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> pd.DataFrame | None:
        """Get segment data as a pandas dataframe.

        Args:
            segment_id (str): The FCD segment ID.
            start_time (datetime): The start time of the query. If None, the query will be done from the earliest measurement timestamp.
            end_time (datetime): The end time of the query. If None, the query will be done from the latest measurement timestamp.

        Returns:
             pd.DataFrame or None if the query was unsuccessful.

        """
        try:
            # Use circuit breaker to protect against InfluxDB failures
            async with self.db_circuit_breaker:
                with FCDInfluxDBManager(
                    url=self.db_url,
                    token=self.db_validation_token,
                    org=self.db_org,
                    bucket=self.db_validation_bucket,
                ) as manager:
                    if not await asyncio.to_thread(manager.check_connection):
                        self.logger.error("FCD database connection error!")
                        return None

                    validation_data_df = await asyncio.to_thread(
                        manager.get_segment_data_dataframe,
                        segment_id=segment_id,
                        measurement_name=INFLUX_VALIDATION_MEASUREMENT,
                        start_time=start_time,
                        end_time=end_time,
                        latest_only=True,
                        query_fields=[
                            "fcd",
                            "consecutive_zeros",
                            "consecutive_low",
                            "day_of_week",
                            "hour_of_day",
                            "max_consecutive_zeros_q95",
                            "max_consecutive_zeros_or_ones_q95",
                            "fcd_mean_median",
                            "running_mean",
                            "segment_closure_status",
                        ],
                        interval_minutes=self.validation_frequency,
                    )

                    if validation_data_df is not None and not validation_data_df.empty:
                        validation_data_df.rename(
                            columns={"_time": "time"}, inplace=True
                        )
                        return validation_data_df
                    else:
                        self.logger.warning("FCD database query returned no results")
                        return None
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")
            return None

    # ------------------------------------------------------#
    # --------------- PUBLIC CLASS METHODS -----------------#
    # ------------------------------------------------------#

    async def update_segment(self, reported_disturbances: list):
        """Update the segment profile based on updated disturbance data.

        This usually affects the start and/or end of the reported disturbances,
        which might affect the profiling dates.
        """
        self.logger.info("Updating segment with new disturbance data.")
        new_disturbance_start_date, new_disturbance_end_date = (
            IdeaHelsinkiDataPreProcessor.determine_disturbance_dates(
                reported_disturbances=reported_disturbances
            )
        )

        if new_disturbance_start_date.date() != self.disturbance_start_date.date():
            self.disturbance_start_date = new_disturbance_start_date
            # Recalculate the profiling dates
            # End point for the profile history, (example. datetime 2025-6-10), based on the disturbance start date.
            self.profiling_end_date = (
                IdeaHelsinkiDataPreProcessor.calculate_profiling_end_date(
                    disturbance_start_date=self.disturbance_start_date,
                    lead_time_hours=self.profile_end_lead_time_hours,
                )
            )
            # Starting point for the profile history, (example. datetime 2025-1-10), based on the profiling_end_date.
            self.profiling_start_date = (
                IdeaHelsinkiDataPreProcessor.calculate_profiling_start_date(
                    profiling_end_date=self.profiling_end_date,
                    profile_time_frame_weeks=self.profile_time_frame_weeks,
                )
            )
            # Reassign the segment_profile attribute to None. This change will be caught in the main loop, and the segment will be reprofiled if needed.
            self.segment_profile = None
            if self.profile_repository is not None:
                try:
                    await asyncio.to_thread(
                        self.profile_repository.delete_profile, self.segment_id
                    )
                except Exception as e:
                    self.logger.error(f"Failed to delete profile from SQLite: {e}")

        if new_disturbance_end_date.date() != self.disturbance_end_date.date():
            self.disturbance_end_date = new_disturbance_end_date
