# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import json
import os
import signal
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ------------------------------------------------------#
# ------------- PROJECT MODULE IMPORTS -----------------#
# ------------------------------------------------------#
import idea_shared.lib.DisturbanceValidator as DisturbanceValidator
import pause
import sentry_sdk

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.HelsinkiWFSClient import HelsinkiAlluWFSClient
from idea_shared.classes.IntersectionDetector import IntersectionDetector
from idea_shared.classes.Logger import Logger
from idea_shared.feature_flags import init_feature_flags
from idea_shared.health.server import HealthServer

# ------------------------------------------------------#
# ------------------ CONSTANTS -------------------------#
# ------------------------------------------------------#
from idea_shared.lib.Constants.Constants import (
    FCD_HISTORY_START_DATE,
    FCD_MAP_DATA_FILE_LOCATION,
    FCD_MAPPING_MAX_AGE_MINUTES,
    HEALTH_CHECK_PORT,
    PROFILE_TIME_FRAME_WEEKS,
    TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
    TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY,
    TRAFFIC_DISTURBANCES_TO_MONITOR,
    UPDATE_FRESHNESS_DEGRADED_MINUTES,
    UPDATE_FRESHNESS_HEALTHY_MINUTES,
    WFS_HEALTH_CHECK_CACHE_TTL,
    WFS_HEALTH_CHECK_TIMEOUT,
)

# ------------------------------------------------------#
# ------------- SERVICE-SPECIFIC IMPORTS ----------------#
# ------------------------------------------------------#
from health_checks import (
    DetectorHealthCheck,
    FCDMappingHealthCheck,
    OutputFileHealthCheck,
    UpdateFreshnessHealthCheck,
    WFSAPIHealthCheck,
)
from service_state import ServiceState

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

    # Initialize feature flags early in startup
    logger.info("Initializing feature flags...")
    init_feature_flags(data_dir="/app/data", service_name="traffic-monitor")

    # Initialize core components
    detector = IntersectionDetector()
    service_state = ServiceState()

    # Initialize health server
    health_server = HealthServer(port=HEALTH_CHECK_PORT, app_name="Traffic Monitor")

    # =========================================================================
    # STARTUP-SPECIFIC HEALTH CHECKS
    # =========================================================================
    # These checks are used ONLY for the /startup endpoint during initial boot.
    # They verify WFS API connectivity without requiring:
    # - FCD mapping file (created by fcd-manager service)
    # - First update cycle completion
    #
    # This separation allows the pod to pass startup probes while waiting
    # for dependencies (fcd-manager) and completing initial data fetch.
    # =========================================================================
    logger.info("Registering startup-only health checks (WFS connectivity only)...")

    # Startup check: WFS API connectivity
    wfs_startup_check = WFSAPIHealthCheck(
        timeout=WFS_HEALTH_CHECK_TIMEOUT,
        cache_ttl=WFS_HEALTH_CHECK_CACHE_TTL,
    )
    health_server.add_check("wfs_api", wfs_startup_check, startup_only=True)

    # =========================================================================
    # REGULAR HEALTH CHECKS (for /ready and /health/detail endpoints)
    # =========================================================================
    logger.info("Registering regular health checks...")

    # Add health checks
    health_server.add_check(
        "wfs_api",
        WFSAPIHealthCheck(
            timeout=WFS_HEALTH_CHECK_TIMEOUT,
            cache_ttl=WFS_HEALTH_CHECK_CACHE_TTL,
        ),
    )
    health_server.add_check(
        "fcd_mapping",
        FCDMappingHealthCheck(
            max_age_minutes=FCD_MAPPING_MAX_AGE_MINUTES,
        ),
    )
    health_server.add_check(
        "output_file",
        OutputFileHealthCheck(critical=False),
    )
    health_server.add_check(
        "update_freshness",
        UpdateFreshnessHealthCheck(
            service_state=service_state,
            healthy_minutes=UPDATE_FRESHNESS_HEALTHY_MINUTES,
            degraded_minutes=UPDATE_FRESHNESS_DEGRADED_MINUTES,
        ),
    )
    health_server.add_check(
        "detector_status",
        DetectorHealthCheck(detector=detector),
    )

    # Define graceful shutdown handler
    def handle_shutdown(signum, frame):
        import time

        logger.info("Shutting down Traffic Monitor...")

        # Wait for current processing to complete with timeout
        if service_state.is_processing:
            logger.info("Waiting for current processing to complete...")
            max_wait_time = 30  # Maximum 30 seconds wait
            start_time = time.time()

            while (
                service_state.is_processing
                and (time.time() - start_time) < max_wait_time
            ):
                time.sleep(0.5)

            if service_state.is_processing:
                logger.warning(
                    f"Processing did not complete within {max_wait_time} seconds, forcing shutdown"
                )

        # Stop health server
        try:
            health_server.stop()
        except Exception as e:
            logger.error(f"Error stopping health server: {e}")

        # Close WFS session if exists
        from health_checks import WFSAPIHealthCheck

        WFSAPIHealthCheck.close_session_sync()

        logger.info("Shutdown complete")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start health server in background thread
    health_server.start_background()
    logger.info(f"Health server started on port {HEALTH_CHECK_PORT}")

    while True:
        logger.info("###########################################")
        logger.info("Update cycle started!")
        logger.info("###########################################")

        # Mark as processing
        service_state.set_processing(True)

        # The loop needs the FCD mapping file to be available.
        # Check is the file location exists, if not, pause and start the loop again.

        if not detector.check_if_file_path_exists(FCD_MAP_DATA_FILE_LOCATION):
            logger.warning(
                f"FCD mapping file not found : {FCD_MAP_DATA_FILE_LOCATION}. Update cycle paused for FCD mapping retry.s"
            )
            service_state.set_processing(False)
            # Pause the cycle until the next update retry. This time is defined in the TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY variable (in minutes)
            update_cycle_pause(TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY)
            continue

        wfs_cache_path = Path("data/wfs_cache.json")
        try:
            with HelsinkiAlluWFSClient() as allu_client:
                allu_wfs_data = allu_client.request_wfs_features_from_list(
                    TRAFFIC_DISTURBANCES_TO_MONITOR
                )
        except Exception as e:
            logger.error(f"Failed to get data from Allu: {e}")
            allu_wfs_data = None

        # Cache successful responses; fall back to cache on failure
        if allu_wfs_data:
            try:
                wfs_cache_path.write_text(
                    json.dumps(
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "data": allu_wfs_data,
                        }
                    )
                )
            except OSError as e:
                logger.warning(f"Failed to write WFS cache: {e}")
        elif wfs_cache_path.exists():
            try:
                cache = json.loads(wfs_cache_path.read_text())
                cache_age_hours = (
                    datetime.now(UTC) - datetime.fromisoformat(cache["timestamp"])
                ).total_seconds() / 3600
                if cache_age_hours < 24:
                    logger.warning(
                        f"Using cached WFS data ({cache_age_hours:.1f}h old)"
                    )
                    allu_wfs_data = cache["data"]
                else:
                    logger.warning("WFS cache too old (>24h), skipping")
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Failed to read WFS cache: {e}")

        if not allu_wfs_data:
            service_state.update_wfs_fetch(
                success=False, error="No data from WFS or cache"
            )
            service_state.set_processing(False)
            update_cycle_pause(TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY)
            continue

        if allu_wfs_data:
            logger.info("Successfully fetched WFS data")
            service_state.update_wfs_fetch(
                success=True,
                disturbance_count=len(allu_wfs_data)
                if isinstance(allu_wfs_data, list)
                else 0,
            )

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

                # Update intersection count
                service_state.update_intersection(
                    len(final_model_data)
                    if isinstance(final_model_data, list | dict)
                    else 0
                )

                try:
                    detector.write_json_records(
                        final_model_data, TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION
                    )
                    service_state.update_file_write(success=True)
                except Exception as e:
                    logger.error(f"Failed to write output file: {e}")
                    service_state.update_file_write(success=False, error=str(e))
            else:
                logger.info(
                    "No disturbances were found that match validation criteria."
                )
        else:
            logger.error("Failed to fetch WFS data.")
            service_state.update_wfs_fetch(
                success=False, error="No data returned from WFS"
            )

        # Mark processing as complete
        service_state.set_processing(False)

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
    # Initialize Sentry if DSN is provided
    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if sentry_dsn and sentry_dsn != "":
        sentry_sdk.init(
            dsn=sentry_dsn,
            sample_rate=0.1,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        logger.info("Sentry initialized for error tracking")
    else:
        logger.info("SENTRY_DSN not set, running without Sentry error tracking")

    logger.info("Starting program!.")
    main()
