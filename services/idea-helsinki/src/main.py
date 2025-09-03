#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
import asyncio
import sys

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from idea_shared.classes.IdeaHelsinkiManager import IdeaHelsinkiManager
from idea_shared.classes.Logger import Logger

#------------------------------------------------------#
#------------------ CONSTANTS -------------------------#
#------------------------------------------------------#
from idea_shared.lib.Constants.Constants import PROFILE_TIME_FRAME_WEEKS
from idea_shared.lib.Constants.Constants import PROFILE_END_LEAD_TIME_HOURS
from idea_shared.lib.Constants.Constants import VALIDATION_UPDATE_FREQUENCY
from idea_shared.lib.Constants.Constants import VALIDATION_MAX_AGE_DAYS

from idea_shared.lib.Constants.Constants import TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY

from idea_shared.lib.Constants.Constants import TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION


from idea_shared.lib.Constants.PrivateConstants import INFLUX_DB_ORG
from idea_shared.lib.Constants.PrivateConstants import INFLUX_DB_URL
from idea_shared.lib.Constants.PrivateConstants import INFLUX_DB_FCD_BUCKET
from idea_shared.lib.Constants.PrivateConstants import INFLUX_DB_FCD_TOKEN
from idea_shared.lib.Constants.PrivateConstants import INFLUX_DB_VALIDATION_BUCKET
from idea_shared.lib.Constants.PrivateConstants import INFLUX_DB_VALIDATION_TOKEN

# for testing, based on intersected segments.
#target_fcd_segments = ["1195756141337706497","1195756141314637825"]

logger = Logger(__name__)

async def main():
    """
    Initializes and runs the main IdeaHelsinkiManager orchestration task.
    """
    logger.info("Initializing IDEA Helsinki Manager...")

    # Create an instance of the manager with the required configuration.
    # The target_fcd_segments argument is omitted to process all segments by default.
    manager = IdeaHelsinkiManager(
        validation_frequency=VALIDATION_UPDATE_FREQUENCY,
        validation_max_age_days=VALIDATION_MAX_AGE_DAYS,
        profile_time_frame_weeks=PROFILE_TIME_FRAME_WEEKS,
        profile_end_lead_time_hours=PROFILE_END_LEAD_TIME_HOURS,
        traffic_disturbance_data_file_location=TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
        traffic_disturbance_update_frequency=TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY,
        target_fcd_segments=None,
        db_org=INFLUX_DB_ORG,
        db_url=INFLUX_DB_URL,
        db_fcd_bucket=INFLUX_DB_FCD_BUCKET,
        db_fcd_token=INFLUX_DB_FCD_TOKEN,
        db_validation_bucket=INFLUX_DB_VALIDATION_BUCKET,
        db_validation_token=INFLUX_DB_VALIDATION_TOKEN
    )

    try:
        # Start the manager's main loop and let it run forever.
        # This loop will discover and manage all the individual road segment tasks.
        await manager.run_main_loop()
    except asyncio.CancelledError:
        logger.info("###########################################")
        logger.info("Main manager task was cancelled. Shutting down.")
        logger.info("###########################################")
    except Exception as e:
        logger.error(f"A critical error occurred in the IdeaHelsinkiManager: {e}", exc_info=True)
        sys.exit(1) # Exit with an error code

if __name__ == "__main__":
    logger.info("###########################################")
    logger.info("## Starting IDEA Helsinki Service Runner ##")
    logger.info("###########################################")
    try:
        # start the asyncio event loop and run the main function.
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program stopped by user (Ctrl+C).")