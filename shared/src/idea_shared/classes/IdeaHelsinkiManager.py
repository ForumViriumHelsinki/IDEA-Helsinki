#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
import asyncio
from datetime import datetime, timezone, timedelta
import json

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from idea_shared.classes.IdeaHelsinkiRoadSegment import IdeaHelsinkiRoadSegment
from idea_shared.classes.Logger import Logger

class IdeaHelsinkiManager:
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
        self.traffic_disturbance_data_file_location = traffic_disturbance_data_file_location
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

    def _get_disturbance_data(self, file_path: str) -> dict:
        """
        Loads the latest validated disturbance data with intersections.

        Args:
            file_path: Path to the JSON file containing the latest validated disturbance data.

        returns:
            Dictionary containing the latest validated disturbance data.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Could not load disturbance data from '{file_path}': {e}")
            return {}

    async def _wait_for_next_management_cycle(self):
        """
        Void method that pauses the manager until the next management cycle.
        Bases the wait time on the "clock" to determine the number of seconds it needs to sleep.
        Example: a 60-minute wait is always the next hour on the clock (15:00, 16:00 etc.), regardless of the current time.
        Example: A function called at 16:47 will wait until 17:00.
        Based on the traffic_disturbance_update_frequency.
        """
        now = datetime.now(timezone.utc)
        minutes_to_add = self.traffic_disturbance_update_frequency  - (now.minute % self.traffic_disturbance_update_frequency)

        resume_time = now + timedelta(minutes=minutes_to_add)
        resume_time = resume_time.replace(second=0, microsecond=0)

        if resume_time <= now:
            resume_time += timedelta(minutes=self.traffic_disturbance_update_frequency)

        self.logger.info(f"Pausing... Next management cycle at {resume_time.strftime('%Y-%m-%d %H:%M:%S')}")
        await asyncio.sleep((resume_time - now).total_seconds())

    async def run_main_loop(self):
        """
        The main orchestration loop for managing IdeaHelsinkiRoadSegments.
        """
        while True:
            self.logger.info("Manager starting new cycle: discovering and updating tasks.")

            # Load the latest disturbance data with intersections
            disturbance_data = self._get_disturbance_data(self.traffic_disturbance_data_file_location)

            # Group disturbances by segment ID, if target_fcd_segments is specified, focuses only on them.
            segments_to_process = {}

            for segment_id, data in disturbance_data.get("segmentId", {}).items():
                if self.target_fcd_segments:
                    if segment_id in self.target_fcd_segments or not self.target_fcd_segments:
                        segments_to_process[segment_id] = data.get("detailedCollisions", [])
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
                self.logger.info(f"Disturbance ended for segment {segment_id}. Deactivating task.")
                active_segment = self.active_segments.pop(segment_id)
                active_segment["task"].cancel()  # Stop the asyncio task (worker loop)

            # Create or update tasks for segments that are listed for processing
            for segment_id, disturbances in segments_to_process.items():
                if segment_id in self.active_segments:
                    # If already active, update it with the latest disturbance info
                    self.active_segments[segment_id]["instance"].update_segment(disturbances)
                else:
                    # If new, create the class instance and start its lifecycle task
                    self.logger.info(f"New disturbance detected for segment {segment_id}. Starting validation task.")
                    segment_instance = IdeaHelsinkiRoadSegment(
                        segment_id=segment_id,
                        reported_disturbances=disturbances,
                        validation_frequency=self.validation_frequency,
                        validation_max_age_days = self.validation_max_age_days,
                        profile_time_frame_weeks=self.profile_time_frame_weeks,
                        profile_end_lead_time_hours = self.profile_end_lead_time_hours,
                        db_org = self.db_org,
                        db_url = self.db_url,
                        db_fcd_bucket = self.db_fcd_bucket,
                        db_fcd_token = self.db_fcd_token,
                        db_validation_bucket = self.db_validation_bucket,
                        db_validation_token = self.db_validation_token,
                    )
                    # Create and store the task
                    task = asyncio.create_task(segment_instance.run_lifecycle())
                    self.active_segments[segment_id] = {"instance": segment_instance,"task": task,}

            self.logger.info(f"Manager cycle complete. Active tasks: {len(self.active_segments)}.")
            # Take a break and enjoy the bits and bytes.
            await self._wait_for_next_management_cycle()
