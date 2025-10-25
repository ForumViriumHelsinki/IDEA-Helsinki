# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import os
import signal
import sys
from datetime import UTC, datetime, timedelta

# ------------------------------------------------------#
# ------------- PROJECT MODULE IMPORTS -----------------#
# ------------------------------------------------------#
import idea_shared.lib.FcdUtils as FcdUtils
import idea_shared.lib.TomTomFcdAggregator as TomTomFcdAggregator
import pause
import sentry_sdk

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.AzureBlobContainerManager import (
    AzureBlobContainerManager,
    TimePrecision,
)
from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager
from idea_shared.classes.Logger import Logger

# ------------------------------------------------------#
# ------------- FEATURE FLAGS IMPORTS ------------------#
# ------------------------------------------------------#
from idea_shared.feature_flags import (
    FeatureFlag,
    get_feature_flags,
    initialize_feature_flags,
)
from idea_shared.feature_flags.providers import (
    EnvironmentVariableProvider,
    JsonFileProvider,
)
from idea_shared.health.idea_checks import (
    AzureBlobStorageHealthCheck,
    FCDDataFreshnessHealthCheck,
    InfluxDBHealthCheck,
    SegmentMappingIntegrityHealthCheck,
)
from idea_shared.health.server import HealthServer

# ------------------------------------------------------#
# ------------------ CONSTANTS -------------------------#
# ------------------------------------------------------#
from idea_shared.lib.Constants.Constants import (
    ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION,
    DATA_DIR,
    FCD_BACKFILL_CHUNK_DAYS,
    FCD_BACKFILL_WORKER_COUNT,
    FCD_HISTORY_START_DATE,
    FCD_MAP_DATA_FILE_LOCATION,
    FCD_MAPPING_MAX_AGE_MINUTES,
    FCD_MAX_CHUNK_RETRIES,
    FCD_PROCESSING_BATCH_SIZE,
    FCD_RETRY_DELAY_SECONDS,
    FCD_SHUTDOWN_TIMEOUT_SECONDS,
    FCD_UPDATE_FREQUENCY,
    FCD_WRITE_QUEUE_MAX_SIZE,
    HEALTH_CHECK_CACHE_TTL_SECONDS,
    HEALTH_CHECK_PORT,
    MASTER_SEGMENT_HISTORY_FILE_LOCATION,
    MAX_FCD_DATA_BASE_UPDATE_DOWNTIME,
    UPDATE_FRESHNESS_DEGRADED_MINUTES,
    UPDATE_FRESHNESS_HEALTHY_MINUTES,
)
from idea_shared.lib.Constants.PrivateConstants import (
    AZURE_ACCOUNT_NAME,
    AZURE_CONTAINER_NAME,
    AZURE_SAS_TOKEN,
    INFLUX_DB_FCD_BUCKET,
    INFLUX_DB_FCD_TOKEN,
    INFLUX_DB_ORG,
    INFLUX_DB_URL,
)
from idea_shared.threading import ThreadCoordinator

# ------------------------------------------------------#
# ----------- THREADING MODULE IMPORTS -----------------#
# ------------------------------------------------------#
from fcd_processing import process_date_range_streaming

# ------------------------------------------------------#
# -------------- HEALTH CHECK IMPORTS ------------------#
# ------------------------------------------------------#
from health_checks import (
    ProcessingPipelineHealthCheck,
    SegmentMappingFreshnessHealthCheck,
    UpdateCycleHealthCheck,
)

logger = Logger(__name__)

# Global health server and check instances
health_server = None
update_cycle_check = None
pipeline_check = None

# Global thread coordinator (for multi-threaded mode)
thread_coordinator = None


def handle_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")

    global health_server, thread_coordinator

    # Shutdown thread coordinator first (if running in multi-threaded mode)
    if thread_coordinator:
        logger.info("Shutting down thread coordinator...")
        try:
            thread_coordinator.shutdown(timeout=FCD_SHUTDOWN_TIMEOUT_SECONDS)
            logger.info("Thread coordinator shutdown complete")
        except Exception as e:
            logger.error(f"Error during thread coordinator shutdown: {e}")

    # Stop health server
    if health_server:
        logger.info("Stopping health server...")
        health_server.stop()

    sys.exit(0)


def run_singlethreaded(azure_manager: AzureBlobContainerManager):
    """
    Run FCD synchronization in single-threaded mode (original implementation).

    This mode processes data sequentially and is used when FCD_ENABLE_MULTITHREADING=False.
    Maintains backward compatibility with the original implementation.

    Args:
        azure_manager: Azure blob container manager instance
    """
    logger.info("Running in SINGLE-THREADED mode")
    logger.info("###########################################")
    logger.info("Updating FCD database on program start")
    logger.info("###########################################")

    if not initialize_database_update(azure_manager, update_fcd_mapping=True):
        logger.error("Program failed to initialize database update, Exiting...")
        return False

    last_fcd_mapping_done = datetime.now(UTC)

    while True:
        logger.info("###########################################")
        logger.info("Update cycle started!")
        logger.info("###########################################")

        # Get current time
        current_time = datetime.now(UTC)

        # Determine if the FCD mapping should be updated
        update_fcd_mapping = (current_time - last_fcd_mapping_done) >= timedelta(
            minutes=FCD_UPDATE_FREQUENCY
        )

        if update_fcd_database(
            azure_manager, current_time, update_fcd_mapping=update_fcd_mapping
        ):
            logger.info("FCD database update!")
            # Update health check timestamp for successful update
            if update_cycle_check:
                update_cycle_check.update_timestamp()
            if update_fcd_mapping:
                last_fcd_mapping_done = current_time
                FcdUtils.update_segment_changelog(
                    FCD_MAP_DATA_FILE_LOCATION,
                    MASTER_SEGMENT_HISTORY_FILE_LOCATION,
                    ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION,
                    current_time,
                )
        else:
            logger.error(
                f"FCD database could not be updated, retrying in {FCD_UPDATE_FREQUENCY} minutes!"
            )
            # Record error in pipeline health check
            if pipeline_check:
                pipeline_check.record_error("FCD database update failed")

        # Pause the cycle until the next update
        current_time = datetime.now(UTC)

        # Get the next FCD_UPDATE_FREQUENCY mark
        minutes_to_add = FCD_UPDATE_FREQUENCY - (
            current_time.minute % FCD_UPDATE_FREQUENCY
        )
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


def run_multithreaded(azure_manager: AzureBlobContainerManager):
    """
    Run FCD synchronization in multi-threaded mode with ThreadCoordinator.

    This mode uses multiple backfill worker threads and a single InfluxDB writer thread
    to process historical data in parallel. Provides better performance for large
    date ranges and catches up faster on startup.

    Args:
        azure_manager: Azure blob container manager instance
    """
    global thread_coordinator

    logger.info("Running in MULTI-THREADED mode")
    logger.info(f"  - Backfill workers: {FCD_BACKFILL_WORKER_COUNT}")
    logger.info(f"  - Chunk size: {FCD_BACKFILL_CHUNK_DAYS} days")
    logger.info(f"  - Write queue size: {FCD_WRITE_QUEUE_MAX_SIZE}")
    logger.info(f"  - Max retries: {FCD_MAX_CHUNK_RETRIES}")

    # Prepare InfluxDB configuration
    influx_config = {
        "url": INFLUX_DB_URL,
        "token": INFLUX_DB_FCD_TOKEN,
        "org": INFLUX_DB_ORG,
        "bucket": INFLUX_DB_FCD_BUCKET,
    }

    # Initialize ThreadCoordinator with streaming processing function
    thread_coordinator = ThreadCoordinator(
        num_backfill_workers=FCD_BACKFILL_WORKER_COUNT,
        azure_manager=azure_manager,
        influx_config=influx_config,
        logger=logger,
        processing_function=process_date_range_streaming,
        max_write_queue_size=FCD_WRITE_QUEUE_MAX_SIZE,
        max_retries=FCD_MAX_CHUNK_RETRIES,
        retry_delay=FCD_RETRY_DELAY_SECONDS,
        batch_size=FCD_PROCESSING_BATCH_SIZE,
    )

    logger.info("###########################################")
    logger.info("Starting multi-threaded backfill on program start")
    logger.info("###########################################")

    # Determine backfill date range
    with FCDInfluxDBManager(
        url=INFLUX_DB_URL,
        token=INFLUX_DB_FCD_TOKEN,
        org=INFLUX_DB_ORG,
        bucket=INFLUX_DB_FCD_BUCKET,
    ) as manager:
        if not manager.check_connection():
            logger.error("Failed to connect to InfluxDB, cannot start backfill")
            return False

        data_base_last_update = manager.get_last_update_timestamp()
        if data_base_last_update is None:
            logger.info(
                f"FCD data base is empty, backfilling from {FCD_HISTORY_START_DATE}"
            )
            start_date = datetime.strptime(FCD_HISTORY_START_DATE, "%Y-%m-%d").replace(
                tzinfo=UTC
            )
        else:
            logger.info(f"FCD data base last updated at {data_base_last_update.date()}")
            start_date = data_base_last_update

        end_date = datetime.now(UTC)

        # Start backfill with ThreadCoordinator
        thread_coordinator.start_backfill(start_date, end_date, FCD_BACKFILL_CHUNK_DAYS)

        # Wait for backfill to complete
        logger.info("Waiting for backfill to complete...")
        while True:
            stats = thread_coordinator.get_progress_stats()
            logger.info(
                f"Progress: {stats['date_queue']['completed_ranges']}/{stats['date_queue']['total_ranges']} "
                f"ranges completed, {stats['write_queue']['completed_writes']} writes done"
            )

            # Check if all work is complete
            if (
                stats["date_queue"]["completed_ranges"]
                == stats["date_queue"]["total_ranges"]
                and stats["write_queue"]["queue_size"] == 0
                and not stats["workers_alive"]
            ):
                logger.info("Backfill complete!")
                break

            # Sleep before checking again
            import time

            time.sleep(5)

    # TODO: In future, implement continuous update cycle for multi-threaded mode
    # For now, just run backfill once and exit
    logger.info("###########################################")
    logger.info("Multi-threaded backfill completed")
    logger.info("###########################################")

    # Update FCD mapping after backfill
    logger.info("Updating FCD segment mapping after backfill")
    # Get the most recent data for mapping update
    # For now, we'll trigger a mapping update in the next update cycle

    return True


def main():
    """
    Initializes and runs the continuous FCD synchronization service.

    The service can operate in two modes based on the FCD_ENABLE_MULTITHREADING feature flag:

    Single-threaded mode (FCD_ENABLE_MULTITHREADING=False):
    1. Initial "catch-up" sync on startup, which processes all historical
       data from the last known timestamp in the database to the present.
    2. Perpetual 5-minute update cycle that fetches and processes only the
       newest data, ensuring the database remains up to date.

    Multi-threaded mode (FCD_ENABLE_MULTITHREADING=True):
    1. Initial backfill using ThreadCoordinator with multiple worker threads
       to process historical data in parallel.
    2. TODO: Continuous update cycle (to be implemented in future iteration).
    """
    global health_server, update_cycle_check, pipeline_check

    # Initialize feature flags early in startup
    logger.info("Initializing feature flags...")
    try:
        # Use environment variables in production, JSON file in development
        # Check if we're in production by looking for ENVIRONMENT env var
        environment = os.getenv("ENVIRONMENT", "development")
        if environment == "production":
            logger.info("Using environment variable provider for feature flags")
            provider = EnvironmentVariableProvider()
        else:
            logger.info("Using JSON file provider for feature flags")
            feature_flags_path = os.path.join(DATA_DIR, "feature_flags.json")
            provider = JsonFileProvider(feature_flags_path)

        initialize_feature_flags(provider)
        logger.info("Feature flags initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize feature flags: {e}")
        logger.warning("Continuing with default flag values")

    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Initialize health server
    logger.info(f"Starting health server on port {HEALTH_CHECK_PORT}")
    health_server = HealthServer(
        port=HEALTH_CHECK_PORT,
        app_name="FCD Manager Service",
        enable_metrics=True,
    )

    # Add Azure Blob Storage health check
    azure_check = AzureBlobStorageHealthCheck(
        name="azure_storage",
        account_name=AZURE_ACCOUNT_NAME,
        container_name=AZURE_CONTAINER_NAME,
        sas_token=AZURE_SAS_TOKEN,
        timeout=10.0,
        critical=True,
        cache_ttl=HEALTH_CHECK_CACHE_TTL_SECONDS,
    )
    health_server.add_check("azure_storage", azure_check)

    # Add InfluxDB health check
    influx_check = InfluxDBHealthCheck(
        name="influxdb",
        url=INFLUX_DB_URL,
        token=INFLUX_DB_FCD_TOKEN,
        org=INFLUX_DB_ORG,
        bucket=INFLUX_DB_FCD_BUCKET,
        timeout=5.0,
        critical=True,
        cache_ttl=HEALTH_CHECK_CACHE_TTL_SECONDS,
    )
    health_server.add_check("influxdb", influx_check)

    # Add FCD data freshness check
    freshness_check = FCDDataFreshnessHealthCheck(
        name="data_freshness",
        url=INFLUX_DB_URL,
        token=INFLUX_DB_FCD_TOKEN,
        org=INFLUX_DB_ORG,
        bucket=INFLUX_DB_FCD_BUCKET,
        max_age_minutes=UPDATE_FRESHNESS_DEGRADED_MINUTES,
        measurement="fcd_data",
        timeout=10.0,
        critical=False,  # Not critical for readiness
        cache_ttl=60.0,
    )
    health_server.add_check("data_freshness", freshness_check)

    # Add segment mapping integrity check
    mapping_integrity_check = SegmentMappingIntegrityHealthCheck(
        name="segment_mapping",
        mapping_file_path=FCD_MAP_DATA_FILE_LOCATION,
        history_file_path=MASTER_SEGMENT_HISTORY_FILE_LOCATION,
        timeout=5.0,
        critical=True,
        cache_ttl=300.0,
    )
    health_server.add_check("mapping_integrity", mapping_integrity_check)

    # Add segment mapping freshness check
    mapping_freshness_check = SegmentMappingFreshnessHealthCheck(
        name="mapping_freshness",
        mapping_file_path=FCD_MAP_DATA_FILE_LOCATION,
        max_age_minutes=FCD_MAPPING_MAX_AGE_MINUTES,
        timeout=2.0,
        critical=False,
        cache_ttl=30.0,
    )
    health_server.add_check("mapping_freshness", mapping_freshness_check)

    # Add update cycle health check
    update_cycle_check = UpdateCycleHealthCheck(
        name="update_cycle",
        healthy_threshold_minutes=UPDATE_FRESHNESS_HEALTHY_MINUTES,
        degraded_threshold_minutes=UPDATE_FRESHNESS_DEGRADED_MINUTES,
        timeout=1.0,
        critical=False,
        cache_ttl=5.0,
    )
    health_server.add_check("update_cycle", update_cycle_check)

    # Add processing pipeline health check
    pipeline_check = ProcessingPipelineHealthCheck(
        name="processing_pipeline",
        timeout=2.0,
        critical=False,
        cache_ttl=10.0,
    )
    health_server.add_check("processing_pipeline", pipeline_check)

    # Start health server in background thread
    health_server.start_background()
    logger.info(f"Health server started on http://0.0.0.0:{HEALTH_CHECK_PORT}")
    logger.info(f"  - Liveness:  http://0.0.0.0:{HEALTH_CHECK_PORT}/healthz")
    logger.info(f"  - Readiness: http://0.0.0.0:{HEALTH_CHECK_PORT}/ready")
    logger.info(f"  - Startup:   http://0.0.0.0:{HEALTH_CHECK_PORT}/startup")
    logger.info(f"  - Details:   http://0.0.0.0:{HEALTH_CHECK_PORT}/health/detail")

    # Initialize Azure manager
    azure_manager = AzureBlobContainerManager(
        AZURE_ACCOUNT_NAME, AZURE_CONTAINER_NAME, AZURE_SAS_TOKEN
    )

    # Route to appropriate execution mode based on feature flag
    flags = get_feature_flags()
    multithreading_enabled = flags.is_enabled(
        FeatureFlag.FCD_ENABLE_MULTITHREADING, default=False
    )

    if multithreading_enabled:
        # Multi-threaded mode with ThreadCoordinator
        logger.info("Multi-threading is ENABLED via feature flag")
        try:
            success = run_multithreaded(azure_manager)
            if not success:
                logger.error("Multi-threaded execution failed, exiting...")
                if health_server:
                    health_server.stop()
                sys.exit(1)
        except Exception as e:
            logger.error(f"Multi-threaded execution error: {e}")
            if health_server:
                health_server.stop()
            sys.exit(1)
    else:
        # Single-threaded mode (original implementation)
        logger.info(
            "Multi-threading is DISABLED via feature flag (using single-threaded mode)"
        )
        try:
            run_singlethreaded(azure_manager)
        except Exception as e:
            logger.error(f"Single-threaded execution error: {e}")
            if health_server:
                health_server.stop()
            sys.exit(1)


def update_fcd_segment_mapping(fcd_segments: dict) -> bool:
    """
    This function updates the fcd segment mapping and writes it in a JSON file (FCD_MAP_DATA_FILE_LOCATION),
    this is used for intersection detection with road disturbances.

    Args:
        fcd_segments: A dictionary containing FCD segment data in the FCD data model (docs/data_models.md).

    Returns:
        bool: True or False depending on if the fcd segment mapping was updated and written.
    """

    logger.info("Updating FCD segment mapping")
    mapped_fcd_segments = FcdUtils.get_fcd_geometries(fcd_segments)
    if mapped_fcd_segments:
        return FcdUtils.write_json_records(
            mapped_fcd_segments, FCD_MAP_DATA_FILE_LOCATION
        )
    else:
        return False


def initialize_database_update(
    azure_manager: AzureBlobContainerManager, update_fcd_mapping: bool = False
) -> bool:
    """
    A function that checks the current status of the FCD database and updates it with the missing time (years, months, days).
    This is meant to be run at the start of the program, before the regular update cycle is started.

    Args:
        azure_manager: AzureBlobContainerManager class object for downloading FCD blobs
        update_fcd_mapping: bool, if the fcd mapping should be updated or not.
    Returns:
        True if the FCD database is updated, false otherwise.
    """

    try:
        with FCDInfluxDBManager(
            url=INFLUX_DB_URL,
            token=INFLUX_DB_FCD_TOKEN,
            org=INFLUX_DB_ORG,
            bucket=INFLUX_DB_FCD_BUCKET,
        ) as manager:
            if manager.check_connection():
                data_base_last_update = manager.get_last_update_timestamp()
                if data_base_last_update is None:
                    logger.info(
                        f"FCD data base is empty, updating from FCD history start date : {FCD_HISTORY_START_DATE}"
                    )
                    data_base_last_update = datetime.strptime(
                        FCD_HISTORY_START_DATE, "%Y-%m-%d"
                    ).replace(tzinfo=UTC)
                else:
                    logger.info(
                        f"FCD data base last updated at {data_base_last_update.date()}"
                    )

                # Begin the database update loop, this will download to memory, process and update FCD history one day at a time,
                # beginning from the start of the history (FCD_HISTORY_START_DATE).
                # This way the program can catch the most recent update during the last update of the cycle (current day).

                # Find if there are any folders in the Azure container.
                search_prefixes = azure_manager.get_search_prefixes()
                if not search_prefixes:
                    logger.error("No search prefixes found. Cannot proceed.")
                    return False

                # Iinit the datetime iterator
                date_i = data_base_last_update

                while date_i.date() <= datetime.now(UTC).date():
                    # An aggregation dictionary used for FCD segments. This is incase there are multiple folders in the container.
                    daily_aggregated_data = {}

                    for search_prefix in search_prefixes:
                        # Get the blobs that fall in the time frame (day).
                        blobs_to_process = azure_manager.get_blobs_by_prefix(
                            date_i, TimePrecision.DAY, search_prefix
                        )

                        # Use the helper function to process the blobs.
                        folder_aggregated_data = _process_and_update_blob_list(
                            blobs_to_process, azure_manager
                        )

                        # Update the aggregation dictionary if we have new segment data.
                        if folder_aggregated_data:
                            daily_aggregated_data = TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
                                folder_aggregated_data, daily_aggregated_data
                            )
                        else:
                            logger.info(
                                f"No processable blobs found for day {date_i.date()} on folder {search_prefix}"
                            )

                    # Update the FCD database with the current day if we have data from this day.
                    if daily_aggregated_data:
                        logger.info(
                            f"Updating FCD segment data to the database for day {date_i.date()}"
                        )

                        # Sort the data by date, A "nice to have" function.
                        final_daily_file = TomTomFcdAggregator.sort_tomtom_data_aggregation_file_by_date(
                            daily_aggregated_data
                        )

                        manager.write_fcd_model(final_daily_file)

                    # Update FCD after each day, this way we can catch up changes in the history.
                    if update_fcd_mapping:
                        if update_fcd_segment_mapping(final_daily_file):
                            logger.info("FCD segment mapping updated")
                            FcdUtils.update_segment_changelog(
                                FCD_MAP_DATA_FILE_LOCATION,
                                MASTER_SEGMENT_HISTORY_FILE_LOCATION,
                                ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION,
                                date_i,
                            )
                        else:
                            logger.error("FCD segment mapping update failed")

                    date_i += timedelta(days=1)
            else:
                logger.error("FCD data base update failed")
                return False
        # If no errors have occurred, return True for a successful update.
        logger.info("FCD segments updated to the database!")
        return True
    except Exception as e:
        logger.error(f"FCD database update failed: {e}")
        return False


def update_fcd_database(
    azure_manager: AzureBlobContainerManager,
    current_time: datetime,
    update_fcd_mapping: bool = False,
) -> bool:
    """ "
    A function that checks the last update from the FCD database and updates it with the missing time (target frequency: every 5 minutes).
    This function is not meant to be used for database initialization (use initialize_database_update() for that),
    because it does not address possible memory limitations of the host machine.
    This function is meant to be used only in short (less than 24 hours) update cycles.


    Args:
        azure_manager: AzureBlobContainerManager class object for downloading FCD blobs
        current_time: datetime, current time to compare against the las database update timestamp.
        update_fcd_mapping: bool, if the fcd mapping should be updated or not.
    Returns:
        True if the FCD database is updated, false otherwise.
    """

    try:
        with FCDInfluxDBManager(
            url=INFLUX_DB_URL,
            token=INFLUX_DB_FCD_TOKEN,
            org=INFLUX_DB_ORG,
            bucket=INFLUX_DB_FCD_BUCKET,
        ) as manager:
            if manager.check_connection():
                data_base_last_update = manager.get_last_update_timestamp()
                if data_base_last_update is None:
                    logger.info(
                        "FCD data base is empty! Please run the initialize_database_update() function! Aborting.."
                    )
                    return False

                if (current_time - data_base_last_update) >= timedelta(
                    days=MAX_FCD_DATA_BASE_UPDATE_DOWNTIME
                ):
                    logger.info(
                        f"Last FCD data base update is older than {MAX_FCD_DATA_BASE_UPDATE_DOWNTIME} days! Please run the initialize_database_update() function! Aborting.."
                    )
                    return False

                logger.info(
                    f"FCD data base last updated at {data_base_last_update}, updating to current time {current_time}"
                )

                # Get the blobs that fall in the last update - current time frame.
                blobs_to_process = azure_manager.get_blobs_in_range(
                    data_base_last_update, current_time
                )

                # Use the helper function to process the blobs.
                fcd_database_update_file = _process_and_update_blob_list(
                    blobs_to_process, azure_manager
                )

                # Update the FCD database if there is dictionary is not empty.
                if fcd_database_update_file:
                    manager.write_fcd_model(fcd_database_update_file)

                    # Update the FCD geometry from the last observation batch if it defined in the function argument.
                    if update_fcd_mapping:
                        if update_fcd_segment_mapping(fcd_database_update_file):
                            logger.info("FCD segment mapping updated")
                        else:
                            logger.error("FCD segment mapping update failed")
                else:
                    logger.info("No new data found for DATA base update.")
                    return True
            else:
                logger.error("FCD data base update failed")
                return False
        # If no errors have occurred, return True for a successful update.
        logger.info("FCD segments updated to the database!")
        return True
    except Exception as e:
        logger.error(f"FCD database update failed: {e}")
        return False


def _process_and_update_blob_list(
    blobs_to_process: list, azure_manager: AzureBlobContainerManager
) -> dict:
    """
    Helper to process a list of blobs, returning a single aggregated data dictionary.
    """
    global pipeline_check

    if not blobs_to_process:
        return {}

    # Record processing start
    if pipeline_check:
        pipeline_check.record_processing_start()

    aggregated_fcd_data = {}
    # Iterate through the blobs found.
    for i, blob in enumerate(blobs_to_process):
        blob_name = blob.name
        logger.info(f"Processing blob {i + 1}/{len(blobs_to_process)}: '{blob_name}'")

        # Get the blob timestamp from the blob name
        blob_timestamp_str = FcdUtils.extract_timestamp_str_from_file_name(blob_name)
        if blob_timestamp_str is None:
            logger.warning(
                f"Skipping blob '{blob_name}' due to inability to extract timestamp."
            )
            continue

        # Download the blob
        blob_content_bytes = azure_manager.download_blob_content(blob_name)
        if blob_content_bytes is None:
            logger.warning(
                f"Skipping blob '{blob_name}', download returned no content."
            )
            continue

        # Parse the blob content to a JSON dictionary
        blob_raw_data = FcdUtils.parse_json_from_bytes(blob_content_bytes)
        if blob_raw_data is None:
            logger.warning(
                f"Skipping blob '{blob_name}', downloaded content could not be parsed."
            )
            continue
        # Transform the blob raw data to the FCD data model
        transformed_items = (
            TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
                blob_raw_data, blob_timestamp_str, blob_name
            )
        )
        # Aggregate the Transformed blob raw data to form a dictionary that contains the whole days observations.
        aggregated_fcd_data = (
            TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
                transformed_items, aggregated_fcd_data
            )
        )

    # Sort the Aggregated file based on date (this is a non-critical, "nice to have" thing)
    fcd_database_update_file = (
        TomTomFcdAggregator.sort_tomtom_data_aggregation_file_by_date(
            aggregated_fcd_data
        )
    )

    # Record successful processing completion
    if pipeline_check and fcd_database_update_file:
        pipeline_check.record_processing_complete(len(blobs_to_process))

    # Return the aggregated and sorted FCD dictionary for database update.
    return fcd_database_update_file


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
