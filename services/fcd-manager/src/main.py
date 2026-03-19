# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import sys
import threading
from datetime import UTC, datetime, timedelta

# ------------------------------------------------------#
# ------------- PROJECT MODULE IMPORTS -----------------#
# ------------------------------------------------------#
import idea_shared.lib.FcdUtils as FcdUtils
import idea_shared.lib.TomTomFcdAggregator as TomTomFcdAggregator

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.AzureBlobContainerManager import (
    AzureBlobContainerManager,
)
from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager
from idea_shared.classes.Logger import Logger
from idea_shared.data.json_backend import JsonSegmentRepository
from idea_shared.feature_flags import init_feature_flags
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

# Global thread coordinator
thread_coordinator = None

# Write protection: tracks when critical file writes are in progress
# to prevent data corruption during shutdown
_write_in_progress = threading.Event()


def handle_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")

    global health_server, thread_coordinator

    # Wait for any pending file writes to complete to prevent data corruption
    if _write_in_progress.is_set():
        logger.info("Waiting for pending file writes to complete...")
        # Wait up to 30 seconds for writes to finish
        start_time = datetime.now(UTC)
        while _write_in_progress.is_set():
            if (datetime.now(UTC) - start_time).total_seconds() > 30:
                logger.warning(
                    "Timeout waiting for file writes, proceeding with shutdown"
                )
                break
            import time

            time.sleep(0.1)

    # Shutdown thread coordinator first
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


def run(
    azure_manager: AzureBlobContainerManager,
    segment_repo: JsonSegmentRepository | None = None,
):
    """
    Run FCD synchronization with ThreadCoordinator.

    Uses configurable backfill worker threads (FCD_BACKFILL_WORKER_COUNT) and a single
    InfluxDB writer thread to process historical data. After backfill completes,
    transitions to continuous real-time updates.

    Args:
        azure_manager: Azure blob container manager instance
        segment_repo: Optional segment repository for changelog updates.
    """
    global thread_coordinator

    logger.info(
        f"Starting FCD synchronization with {FCD_BACKFILL_WORKER_COUNT} backfill workers"
    )
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
        logger=logger.logger,
        processing_function=process_date_range_streaming,
        max_write_queue_size=FCD_WRITE_QUEUE_MAX_SIZE,
        max_retries=FCD_MAX_CHUNK_RETRIES,
        retry_delay=FCD_RETRY_DELAY_SECONDS,
        batch_size=FCD_PROCESSING_BATCH_SIZE,
    )

    logger.info("###########################################")
    logger.info("Starting backfill on program start")
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

        data_base_last_update = manager.get_last_update_timestamp(search_all=True)
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

    logger.info("###########################################")
    logger.info("Backfill completed")
    logger.info("Starting continuous real-time updates")
    logger.info("###########################################")

    # Define the real-time update function that the coordinator will call each cycle
    def realtime_update_cycle() -> bool:
        """Perform one real-time update cycle (fetch recent data, write to InfluxDB, update mapping)."""
        current_time = datetime.now(UTC)
        try:
            blobs_to_process = azure_manager.get_blobs_in_range(
                current_time - timedelta(hours=1), current_time
            )

            if not blobs_to_process:
                logger.info("No recent blobs found for real-time update")
                return True

            fcd_data = _process_and_update_blob_list(blobs_to_process, azure_manager)
            if not fcd_data:
                logger.info("No processable data in recent blobs")
                return True

            # Write to InfluxDB
            with FCDInfluxDBManager(
                url=INFLUX_DB_URL,
                token=INFLUX_DB_FCD_TOKEN,
                org=INFLUX_DB_ORG,
                bucket=INFLUX_DB_FCD_BUCKET,
            ) as influx_manager:
                influx_manager.write_fcd_model(fcd_data)

            # Update segment mapping
            if update_fcd_segment_mapping(fcd_data):
                logger.info("FCD segment mapping updated")
                _write_in_progress.set()
                try:
                    if segment_repo is not None:
                        FcdUtils.update_segment_changelog_from_repo(
                            segment_repo, current_time
                        )
                    else:
                        FcdUtils.update_segment_changelog(
                            FCD_MAP_DATA_FILE_LOCATION,
                            MASTER_SEGMENT_HISTORY_FILE_LOCATION,
                            ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION,
                            current_time,
                        )
                finally:
                    _write_in_progress.clear()

            # Update health check timestamp
            if update_cycle_check:
                update_cycle_check.update_timestamp()

            return True
        except Exception as e:
            logger.error(f"Real-time update cycle error: {e}")
            if pipeline_check:
                pipeline_check.record_error(f"Real-time update failed: {e}")
            return False

    # Start real-time continuous updates via ThreadCoordinator
    thread_coordinator.start_realtime(
        update_function=realtime_update_cycle,
        update_interval_minutes=FCD_UPDATE_FREQUENCY,
    )

    # Run initial mapping update immediately after backfill
    realtime_update_cycle()

    # Keep main thread alive — real-time worker handles continuous updates
    # Service stays alive until SIGTERM triggers handle_shutdown()
    try:
        while True:
            import time

            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")

    return True


def main():
    """
    Initializes and runs the continuous FCD synchronization service.

    Uses ThreadCoordinator with configurable worker count (FCD_BACKFILL_WORKER_COUNT):
    1. Initial backfill using worker threads to process historical data.
    2. Continuous real-time update cycle that fetches and processes recent data.
    """
    global health_server, update_cycle_check, pipeline_check

    # Initialize feature flags early in startup
    logger.info("Initializing feature flags...")
    init_feature_flags(data_dir=DATA_DIR, service_name="fcd-manager")

    # Setup signal handlers for graceful shutdown
    from idea_shared.lifecycle.signals import setup_sync_signal_handlers

    setup_sync_signal_handlers(handle_shutdown)

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
        startup_grace_minutes=15,
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

    # =========================================================================
    # STARTUP-SPECIFIC HEALTH CHECKS
    # =========================================================================
    # These checks are used ONLY for the /startup endpoint during initial boot.
    # They verify external service connectivity without requiring data files
    # that are created during the initial sync process.
    #
    # This separation allows the pod to pass startup probes while the lengthy
    # initial FCD data sync is running (which can take 5-10+ minutes).
    # =========================================================================

    # Startup check: Azure Blob Storage connectivity
    azure_startup_check = AzureBlobStorageHealthCheck(
        name="azure_storage_startup",
        account_name=AZURE_ACCOUNT_NAME,
        container_name=AZURE_CONTAINER_NAME,
        sas_token=AZURE_SAS_TOKEN,
        timeout=10.0,
        critical=True,
        cache_ttl=HEALTH_CHECK_CACHE_TTL_SECONDS,
    )
    health_server.add_check("azure_storage", azure_startup_check, startup_only=True)

    # Startup check: InfluxDB connectivity
    influx_startup_check = InfluxDBHealthCheck(
        name="influxdb_startup",
        url=INFLUX_DB_URL,
        token=INFLUX_DB_FCD_TOKEN,
        org=INFLUX_DB_ORG,
        bucket=INFLUX_DB_FCD_BUCKET,
        timeout=5.0,
        critical=True,
        cache_ttl=HEALTH_CHECK_CACHE_TTL_SECONDS,
    )
    health_server.add_check("influxdb", influx_startup_check, startup_only=True)

    # Start health server in background thread
    health_server.start_background()
    logger.info(f"Health server started on http://0.0.0.0:{HEALTH_CHECK_PORT}")
    logger.info(f"  - Liveness:  http://0.0.0.0:{HEALTH_CHECK_PORT}/healthz")
    logger.info(f"  - Readiness: http://0.0.0.0:{HEALTH_CHECK_PORT}/ready")
    logger.info(
        f"  - Startup:   http://0.0.0.0:{HEALTH_CHECK_PORT}/startup (connectivity only)"
    )
    logger.info(f"  - Details:   http://0.0.0.0:{HEALTH_CHECK_PORT}/health/detail")

    # Initialize segment repository for data access
    segment_repo = JsonSegmentRepository(
        mapping_path=FCD_MAP_DATA_FILE_LOCATION,
        changelog_path=MASTER_SEGMENT_HISTORY_FILE_LOCATION,
        archive_path=ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION,
    )

    # Initialize Azure manager
    azure_manager = AzureBlobContainerManager(
        AZURE_ACCOUNT_NAME, AZURE_CONTAINER_NAME, AZURE_SAS_TOKEN
    )

    # Run FCD synchronization
    try:
        success = run(azure_manager, segment_repo=segment_repo)
        if not success:
            logger.error("FCD synchronization failed, exiting...")
            if health_server:
                health_server.stop()
            sys.exit(1)
    except Exception as e:
        logger.error(f"FCD synchronization error: {e}")
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
    from idea_shared.observability.sentry import configure_sentry

    configure_sentry("fcd-manager")

    logger.info("Starting program!.")
    main()
