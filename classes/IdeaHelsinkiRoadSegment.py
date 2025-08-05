#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
import asyncio
import io
from datetime import datetime, timezone, timedelta
import pandas as pd

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from classes.Logger import Logger
from classes.FCDInfluxDBManager import FCDInfluxDBManager

#------------------------------------------------------#
#------------- PROJECT MODULE IMPORTS -----------------#
#------------------------------------------------------#
from lib.idea.profile.profile import calculate_profile
from lib.idea.validation.validation import validate_roadwork
import lib.IdeaHelsinkiDataPreProcessor as IdeaHelsinkiDataPreProcessor

class IdeaHelsinkiRoadSegment:
    """
    Class that uses the IDEA algorithm to profile and validate a single road.
    Autonomous in nature, determines the necessary start and end dates based on the road disturbances associated with it.
    This is the go-go-jee-jee of the Helsinki IDEA application.
    """

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
    ):
        self.segment_id = segment_id
        self.validation_frequency: int = validation_frequency
        self.profile_time_frame_weeks: int = profile_time_frame_weeks
        self.profile_end_lead_time_hours: int = profile_end_lead_time_hours
        self.db_org: str = db_org
        self.db_url: str = db_url
        self.db_fcd_bucket: str = db_fcd_bucket
        self.db_fcd_token: str = db_fcd_token
        self.db_validation_bucket: str = db_validation_bucket
        self.db_validation_token: str = db_validation_token
        self.disturbance_start_date, self.disturbance_end_date = IdeaHelsinkiDataPreProcessor.determine_disturbance_dates(reported_disturbances=reported_disturbances)
        # End point for the profile history, (example. datetime 2025-6-10), based on the disturbance start date.
        self.profiling_end_date = IdeaHelsinkiDataPreProcessor.calculate_profiling_end_date(disturbance_start_date=self.disturbance_start_date, lead_time_hours=self.profile_end_lead_time_hours)
        # Starting point for the profile history, (example. datetime 2025-1-10), based on the profiling_end_date.
        self.profiling_start_date = IdeaHelsinkiDataPreProcessor.calculate_profiling_start_date(profiling_end_date=self.profiling_end_date, profile_time_frame_weeks=self.profile_time_frame_weeks)
        # This attribute init also checks if the segment has been already profiled (happens in cases when the program has been terminated unexpectedly)
        self.last_validation_update = None
        self.segment_profile = None
        self.last_segment_validation = None
        self.segment_active:bool = True
        self.logger = Logger(f"Helsinki IDEA road segment ID : {self.segment_id}")
        self.logger.info("Segment object created")

    async def _wait_for_next_cycle(self):
        """
        Void method that pauses the road segment object until the next validation cycle.
        Bases the wait time on the "clock" to determine the number of seconds it needs to sleep.
        Example: a 5-minute wait is always the five minutes on the clock (15:05, 15:10 etc.), regardless of the current time.
        Example: A function called at 16:47 will wait until 16:50.
        Based on the validation_frequency
        """
        now = datetime.now(timezone.utc)
        minutes_to_add = self.validation_frequency - (now.minute % self.validation_frequency)

        resume_time = now + timedelta(minutes=minutes_to_add)
        resume_time = resume_time.replace(second=0, microsecond=0)

        if resume_time <= now:
            resume_time += timedelta(minutes=self.validation_frequency)

        self.logger.info(f"Pausing. Next validation cycle at {resume_time.strftime('%Y-%m-%d %H:%M:%S')}")
        await asyncio.sleep((resume_time - now).total_seconds())

    async def __validate_segment(self, current_time: datetime):
        """
        A void method that profiles and validates a single road segment.

        Args:
            current_time (datetime): The current time UTC.
        """

        # Sleep for 10 seconds before beginning validation, so the current segment data is updated and available.
        await asyncio.sleep(10)

        if self.segment_profile is None:
            self.logger.info("Generating segment profile...")
            segment_data_to_profile = await self.__get_segment_data_from_influxdb(segment_id=self.segment_id, start_time=self.profiling_start_date, end_time=self.profiling_end_date)
            if segment_data_to_profile is not None and not segment_data_to_profile.empty:
                profile = await asyncio.to_thread(calculate_profile,df=segment_data_to_profile,start=self.profiling_start_date,end=self.profiling_end_date)
                if not profile.empty:
                    self.logger.info("Segment profile generated")
                    self.segment_profile = profile
                else:
                    self.logger.error("IDEA returned an empty segment profile")
                    return
            else:
                self.logger.error("Segment profile could not be generated")
                return

        if self.last_segment_validation is not None and not self.last_segment_validation.empty:
            self.logger.info(f"Validating segment for timestamps {self.last_validation_update} - {current_time} ")
            segment_data_to_validate = await self.__get_segment_data_from_influxdb(segment_id=self.segment_id, start_time=self.last_validation_update, end_time=current_time)
        else:
            self.logger.info(f"Validating segment for the first time from {self.profiling_start_date} to {current_time} ")
            segment_data_to_validate = await self.__get_segment_data_from_influxdb(segment_id=self.segment_id,start_time=self.profiling_start_date,end_time=current_time)

        if segment_data_to_validate is not None and not segment_data_to_validate.empty:
            segment_validation = await asyncio.to_thread(validate_roadwork,fcd_during_roadwork=segment_data_to_validate, profile=self.segment_profile, last_segment_validation=self.last_segment_validation)
            if not segment_validation.empty:
                if await self.__write_dataframe_to_influxdb(df=segment_validation, segment_id=self.segment_id, measurement_name="idea_validation"):
                    self.logger.info("Segment validation updated to database.")
                    self.last_segment_validation = segment_validation
                    self.last_validation_update = current_time
                else:
                    self.logger.info('Segment validation NOT updated to database.')
            else:
                self.logger.info('IDEA returned an empty segment validation!')
        else:
            self.logger.info('Segment validation data could not be fetched from database.')

    async def run_lifecycle(self):
        """
        Class main loop for profiling and validating the FCD segment.
        Runs as long as the reported disturbance is active.
        """

        current_date = datetime.now(timezone.utc)

        self.logger.info("Starting main loop...")

        while self.disturbance_end_date.date() > current_date.date():
            # Update current time in loop
            current_date = datetime.now(timezone.utc)

            # Check is segment profiling and validation can be done
            # Determine if the segment has history enough for the IDEA algorithm.
            # Fetch the latest measurement time for the segment.
            segment_history_start_date = (await self.__get_segment_first_timestamp_from_influxdb(segment_id=self.segment_id))

            # self.last_validation_update variable can be None if this is the first run after object init, or the last influxDB query returned None.
            # Otherwise, the variable is incremented (datetime) after each validation.
            if self.last_validation_update is None:
                self.last_validation_update = (await self.__get_segment_last_timestamp_from_influxdb(segment_id=self.segment_id))

            valid_segment = (segment_history_start_date is not None and self.last_validation_update is not None and (segment_history_start_date+ timedelta(weeks=self.profile_time_frame_weeks)<= current_date))

            if valid_segment:
                if self.profiling_start_date.date() <= current_date.date():
                    await self.__validate_segment(current_date)
            else:
                self.logger.warning(f"Segment is not valid for profiling and validation!!! Segment history start date: {segment_history_start_date}, Last segment update date: {self.last_validation_update}")

            await self._wait_for_next_cycle()

        # Once the main loop has finished, the segment deactivates itself and can be removed from processing.
        # This means there is no more go-go-jee-jee for this segment :(
        self.logger.info("Main loop finished. Disturbance period has ended.")
        self.segment_active = False

    async def __write_dataframe_to_influxdb(self, df: pd.DataFrame, segment_id: str, measurement_name: str) -> bool:
        """
        Writes a pandas dataframe to the InfluxDB database.

        Args:
            df (pandas.DataFrame): The IDEA validation dataframe to write to the database.
            segment_id (str): The FCD segment ID.
            measurement_name (str): The name of the measurement to write to the database.

        Returns:
            bool: True if the writing was successful.
        """
        try:
            with FCDInfluxDBManager(url=self.db_url, token=self.db_validation_token, org=self.db_org, bucket=self.db_validation_bucket) as manager:
                if not await asyncio.to_thread(manager.check_connection):
                    self.logger.error("FCD database query failed")
                    return False
                await asyncio.to_thread(manager.write_dataframe,df=df, segment_id=segment_id, measurement_name=measurement_name)
                return True
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")
            return False

    async def __get_segment_last_timestamp_from_influxdb(self, segment_id: str) -> datetime | None:
        """
        Retrieves the last segment timestamp from the InfluxDB database. Note that this is the measurement timestamp.

        Args:
            segment_id (str): The FCD segment ID.

        Returns:
            datetime: The last segment measurement timestamp or None if not available (Segment is not in the database).
        """

        segment_date = None

        try:
            with FCDInfluxDBManager(url=self.db_url, token=self.db_fcd_token, org=self.db_org, bucket=self.db_fcd_bucket) as manager:
                if not await asyncio.to_thread(manager.check_connection):
                    self.logger.error("FCD database query failed")
                    return None
                segment_date = await asyncio.to_thread(manager.get_last_segment_update_timestamp, segment_id = segment_id)
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")

        return segment_date

    async def __get_segment_first_timestamp_from_influxdb(self, segment_id: str) -> datetime | None:
        """
        Retrieves the first segment timestamp from the InfluxDB database. Note that this is the measurement timestamp.

        Args:
            segment_id (str): The FCD segment ID.

        Returns:
            datetime: The first segment measurement timestamp or None if not available (Segment is not in the database).
        """

        segment_date = None

        try:
            with FCDInfluxDBManager(url=self.db_url, token=self.db_fcd_token, org=self.db_org, bucket=self.db_fcd_bucket) as manager:
                if not await asyncio.to_thread(manager.check_connection):
                    self.logger.error("FCD database query failed")
                    return None
                segment_date = await asyncio.to_thread(manager.get_first_segment_update_timestamp, segment_id = segment_id)
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")

        return segment_date

    async def __get_segment_data_from_influxdb(self, segment_id: str, start_time: datetime, end_time: datetime) -> pd.DataFrame | None:
        """
        Retrieves measurement data from the InfluxDB database for a single segment.

        Args:
            segment_id (str): The FCD segment ID.
            start_time (datetime): The start time for the query.
            end_time (datetime): The end time for the query.

        Returns:
            pd.DataFrame | None if the query was unsuccessful.

            NOTE: This function returns the date frame in "IDEA" FCD format:

            '';'fcd;
            datetime;integer
            datetime;integer
        """
        segment_data_df = pd.DataFrame()
        segment_data_csv: str

        # A helper function the parse the data for the IDEA algorithm.
        def _parse_csv_string_to_df(csv_data: str) -> pd.DataFrame | None:
            if not csv_data:
                return None
            try:
                return pd.read_csv(
                    io.StringIO(csv_data),
                    sep=";",
                    names=["", "fcd"],
                    index_col=0,
                    parse_dates=[0],
                )
            except Exception as err:
                self.logger.error(f"Pandas failed to parse CSV string: {err}")
                return None

        try:
            with FCDInfluxDBManager(url=self.db_url, token=self.db_fcd_token, org=self.db_org, bucket=self.db_fcd_bucket) as manager:
                if not await asyncio.to_thread(manager.check_connection):
                    self.logger.error("FCD database query failed")
                    return None

                segment_data_csv_str = await asyncio.to_thread(manager.get_segment_data_idea_format, segment_id = segment_id, start_time = start_time, end_time = end_time, latest_only=False, interval_minutes=self.validation_frequency)
                if not segment_data_csv_str:
                    self.logger.warning("FCD database query returned no results.")
                    return None

                segment_data_df = await asyncio.to_thread(_parse_csv_string_to_df, segment_data_csv_str)

                if segment_data_df is not None and not segment_data_df.empty:
                    return segment_data_df
                else:
                    self.logger.warning("FCD database query returned no results")
        except Exception as e:
            self.logger.error(f"FCD database query failed: {e}")
            return None

        return segment_data_df

    #------------------------------------------------------#
    #--------------- PUBLIC CLASS METHODS -----------------#
    #------------------------------------------------------#

    def update_segment(self, reported_disturbances: list):
        """
        A void function that updates the segment profile based on updated disturbance data.
        This usually affects the start and/or end of the reported disturbances, which might affect the profiling dates.
        """
        self.logger.info("Updating segment with new disturbance data.")
        new_disturbance_start_date, new_disturbance_end_date = IdeaHelsinkiDataPreProcessor.determine_disturbance_dates(reported_disturbances=reported_disturbances)

        if new_disturbance_start_date.date() != self.disturbance_start_date.date():
            self.disturbance_start_date = new_disturbance_start_date
            # Recalculate the profiling dates
            # End point for the profile history, (example. datetime 2025-6-10), based on the disturbance start date.
            self.profiling_end_date = IdeaHelsinkiDataPreProcessor.calculate_profiling_end_date(disturbance_start_date=self.disturbance_start_date, lead_time_hours=self.profile_end_lead_time_hours)
            # Starting point for the profile history, (example. datetime 2025-1-10), based on the profiling_end_date.
            self.profiling_start_date = IdeaHelsinkiDataPreProcessor.calculate_profiling_start_date(profiling_end_date=self.profiling_end_date, profile_time_frame_weeks=self.profile_time_frame_weeks)
            # Reassign the segment_profile attribute to None. This change will be caught in the main loop, and the segment will be reprofiled if needed.
            self.segment_profile = None

        if new_disturbance_end_date.date() != self.disturbance_end_date.date():
            self.disturbance_end_date = new_disturbance_end_date
