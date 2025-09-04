# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
from datetime import UTC, datetime, timedelta

# ------------------------------------------------------#
# ------------- PROJECT MODULE IMPORTS -----------------#
# ------------------------------------------------------#
import idea_shared.lib.DisturbanceValidator as DisturbanceValidator
import pause

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.HelsinkiWFSClient import HelsinkiAlluWFSClient
from idea_shared.classes.IntersectionDetector import IntersectionDetector
from idea_shared.classes.Logger import Logger

# ------------------------------------------------------#
# ------------------ CONSTANTS -------------------------#
# ------------------------------------------------------#
from idea_shared.lib.Constants.Constants import (
    FCD_HISTORY_START_DATE,
    FCD_MAP_DATA_FILE_LOCATION,
    PROFILE_TIME_FRAME_WEEKS,
    TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
    TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY,
    TRAFFIC_DISTURBANCES_TO_MONITOR,
)

logger = Logger(__name__)


def main():
    """
    Initializes and runs the continuous traffic disturbance analysis service.

    The service operates in a perpetual loop, performing the following tasks
    at a set frequency (example: every 60 minutes):
    1.  Fetches traffic disturbance data from the Helsinki Allu WFS API.
    2.  Validates the fetched disturbances against historical data requirements.
    3.  Loads the valid disturbances and a local FCD road segment map.
    4.  Performs a spatial intersection to find which road segments are
        affected by the disturbances.
    5.  Saves the resulting intersection data to a JSON file.
    """

    detector = IntersectionDetector()

    while True:
        logger.info("###########################################")
        logger.info("Update cycle started!")
        logger.info("###########################################")

        # The loop needs the FCD mapping file to be available.
        # Check is the file location exists, if not, pause and start the loop again.

        if not detector.check_if_file_path_exists(FCD_MAP_DATA_FILE_LOCATION):
            logger.warning(
                f"FCD mapping file not found : {FCD_MAP_DATA_FILE_LOCATION}. Update cycle paused for FCD mapping retry.s"
            )
            # Pause the cycle until the next update retry. This time is defined in the TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY variable (in minutes)
            update_cycle_pause(TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY)
            continue

        try:
            with HelsinkiAlluWFSClient() as allu_client:
                allu_wfs_data = allu_client.request_wfs_features_from_list(
                    TRAFFIC_DISTURBANCES_TO_MONITOR
                )
        except Exception as e:
            logger.error(f"Failed to get data from Allu: {e}")
            continue

        if allu_wfs_data:
            logger.info("Successfully fetched WFS data")

            # If we get data, validate the reported disturbances.
            # This checks what disturbances we can check based on the FCD history (FCD history start date + minimum time for IDEA profile)
            history_start_date = datetime.strptime(FCD_HISTORY_START_DATE, "%Y-%m-%d")
            validation_date = history_start_date + timedelta(
                weeks=PROFILE_TIME_FRAME_WEEKS
            )

            validated_allu_data = DisturbanceValidator.validate_disturbance_dates(
                validation_date, allu_wfs_data
            )
            if validated_allu_data:
                logger.info("Successfully validated WFS data for IDEA")

                # Once we have confirmed that we have traffic disturbances that can be passed on to IDEA, time to find intersections with FCD segments.
                logger.info("Performing intersection detection...")

                logger.info("Loading Allu WFS data")
                allu_wfs_gdf = detector.load_wfs_geojson(validated_allu_data)

                logger.info("Loading FCD segment map data")
                # Note that the detector class validates if the FCD_MAP_DATA_FILE_LOCATION location is valid and a file is found.
                tomtom_segments_gdf = detector.load_tomtom_segment_data(
                    FCD_MAP_DATA_FILE_LOCATION
                )

                # Find intersections
                intersecting_features = detector.find_intersecting_features(
                    allu_wfs_gdf, tomtom_segments_gdf
                )

                # Process intersections to an intersection data model
                # Note that usually there is a numerical difference between the "intersecting_features" and the "final_model_data".
                # This is because the "intersecting_features" contains ALL intersections and the "final_model_data" contains segments that have one OR MORE intersections.
                # Brake down: find_intersecting_features() reports all intersections, process_intersections_to_new_model() reports segments that intersect.
                final_model_data = detector.process_intersections_to_new_model(
                    intersecting_features
                )

                detector.write_json_records(
                    final_model_data, TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION
                )
            else:
                logger.info(
                    "No disturbances were found that match validation criteria."
                )
        else:
            logger.error("Failed to fetch WFS data.")

        # Pause the cycle until the next update. This time is defined in the TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY variable (in minutes)
        update_cycle_pause(TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY)


def update_cycle_pause(pause_time: int) -> None:
    """
    A void function for pausing the while loop for predetermined number of minutes.

    Args:
        pause_time (int): The number of minutes to pause.
    """
    # Get a time stamp. Note timezone.
    current_time = datetime.now(UTC)

    # Get the next TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY mark
    minutes_to_add = pause_time - (current_time.minute % pause_time)
    resume_time = current_time + timedelta(minutes=minutes_to_add)
    resume_time = resume_time.replace(second=0, microsecond=0)

    logger.info("###########################################")
    logger.info(
        f"Update cycle finished at {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logger.info(
        f"Next update cycle scheduled at {resume_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logger.info("###########################################")
    pause.until(resume_time)


if __name__ == "__main__":
    logger.info("Starting program!.")
    main()
