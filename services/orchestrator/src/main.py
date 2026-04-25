# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import asyncio
import signal
import sys

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.IdeaHelsinkiManager import IdeaHelsinkiManager
from idea_shared.classes.Logger import Logger
from idea_shared.data.json_backend import JsonDisturbanceRepository
from idea_shared.feature_flags import init_feature_flags
from idea_shared.health.idea_checks import InfluxDBHealthCheck
from idea_shared.health.server import HealthServer

# ------------------------------------------------------#
# ------------------ CONSTANTS -------------------------#
# ------------------------------------------------------#
from idea_shared.lib.Constants.Constants import (
    DISTURBANCE_DATA_MAX_AGE_MINUTES,
    FCD_DATA_FRESHNESS_HOURS,
    HEALTH_CHECK_PORT,
    ORCHESTRATOR_DEADLOCK_THRESHOLD_MINUTES,
    ORCHESTRATOR_MAX_CYCLE_TIME_MINUTES,
    PROFILE_END_LEAD_TIME_HOURS,
    PROFILE_TIME_FRAME_WEEKS,
    TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
    TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY,
    VALIDATION_HISTORY_WEEKS,
    VALIDATION_UPDATE_FREQUENCY,
    WORKER_HEALTH_THRESHOLD_PERCENT,
)
from idea_shared.lib.Constants.PrivateConstants import (
    INFLUX_DB_FCD_BUCKET,
    INFLUX_DB_FCD_TOKEN,
    INFLUX_DB_ORG,
    INFLUX_DB_URL,
    INFLUX_DB_VALIDATION_BUCKET,
    INFLUX_DB_VALIDATION_TOKEN,
)

from health_checks import (
    DisturbanceDataHealthCheck,
    FCDDatabaseHealthCheck,
    InfluxDBConnectionManager,
    OrchestratorHealthCheck,
    ValidationDatabaseHealthCheck,
    WorkerStatusHealthCheck,
)

# for testing, based on intersected segments.
# target_fcd_segments = ["1195756141337706497","1195756141314637825"]

logger = Logger(__name__)
health_server = None


async def shutdown(signal_received, loop):
    """Handle graceful shutdown."""
    global health_server

    logger.info(f"Received exit signal {signal_received.name}...")

    if health_server:
        # Stop the health server gracefully
        await health_server.stop_async()

    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    for task in tasks:
        task.cancel()

    # Wait for all tasks to complete cancellation
    await asyncio.gather(*tasks, return_exceptions=True)

    # Clean up InfluxDB connections
    logger.info("Cleaning up InfluxDB connections...")
    await InfluxDBConnectionManager.cleanup_all()

    loop.stop()


async def main():
    """Initializes and runs the main IdeaHelsinkiManager orchestration task with health checks."""
    global health_server

    # Setup signal handlers early for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(s, loop))
        )

    logger.info("Initializing IDEA Helsinki Manager...")

    # Initialize feature flags early in startup
    logger.info("Initializing feature flags...")
    init_feature_flags(data_dir="/app/data", service_name="orchestrator")

    # Initialize health server
    health_server = HealthServer(
        port=HEALTH_CHECK_PORT, app_name="IDEA Helsinki Service"
    )

    # Create repositories for data access
    from idea_shared.feature_flags import FeatureFlag, get_feature_flags

    flags = get_feature_flags()
    use_sqlite = flags.is_enabled(FeatureFlag.USE_SQLITE_STORAGE)

    if use_sqlite:
        from pathlib import Path

        from idea_shared.data.object_storage import create_object_storage_sync
        from idea_shared.data.sqlite_backend import create_sqlite_repositories
        from idea_shared.health.idea_checks import SqliteHealthCheck
        from idea_shared.lib.Constants.Constants import (
            SQLITE_DIR,
            SQLITE_DISTURBANCES_DB,
            SQLITE_PROFILES_DB,
            SQLITE_SEGMENTS_DB,
        )

        # Ensure SQLite directory exists
        sqlite_dir = Path(SQLITE_DIR)
        sqlite_dir.mkdir(parents=True, exist_ok=True)

        # Initialize object storage sync
        storage_sync = create_object_storage_sync()

        # Download databases from object storage (written by other services)
        segments_db_path = sqlite_dir / SQLITE_SEGMENTS_DB
        disturbances_db_path = sqlite_dir / SQLITE_DISTURBANCES_DB
        profiles_db_path = sqlite_dir / SQLITE_PROFILES_DB

        logger.info("Downloading databases from object storage...")
        storage_sync.download_if_changed(SQLITE_SEGMENTS_DB, segments_db_path)
        storage_sync.download_if_changed(SQLITE_DISTURBANCES_DB, disturbances_db_path)

        # Create repos from downloaded databases
        seg_repos = create_sqlite_repositories(segments_db_path)
        _segment_repo = seg_repos[0]  # Available for future use

        dist_repos = create_sqlite_repositories(disturbances_db_path)
        disturbance_repo = dist_repos[1]  # SqliteDisturbanceRepository

        # Create local profiles database (not shared via GCS)
        profile_repos = create_sqlite_repositories(profiles_db_path)
        profile_repo = profile_repos[2]  # SqliteProfileRepository

        # Add SQLite health checks
        health_server.add_check(
            "sqlite_disturbances",
            SqliteHealthCheck(
                name="sqlite_disturbances",
                db_path=disturbances_db_path,
                expected_tables=["disturbances"],
                critical=False,
                cache_ttl=60.0,
                startup_grace_minutes=10,
            ),
        )
        health_server.add_check(
            "sqlite_profiles",
            SqliteHealthCheck(
                name="sqlite_profiles",
                db_path=profiles_db_path,
                expected_tables=["profiles"],
                critical=False,
                cache_ttl=60.0,
                startup_grace_minutes=15,
            ),
        )

        logger.info(
            f"Using SQLite storage backend: disturbances={disturbances_db_path}, profiles={profiles_db_path}"
        )
    else:
        disturbance_repo = JsonDisturbanceRepository(
            data_path=TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION
        )
        profile_repo = None
        logger.info("Using JSON file storage backend")

    # Create an instance of the manager with the required configuration.
    # The target_fcd_segments argument is omitted to process all segments by default.
    manager = IdeaHelsinkiManager(
        validation_frequency=VALIDATION_UPDATE_FREQUENCY,
        validation_history_weeks=VALIDATION_HISTORY_WEEKS,
        profile_time_frame_weeks=PROFILE_TIME_FRAME_WEEKS,
        profile_end_lead_time_hours=PROFILE_END_LEAD_TIME_HOURS,
        traffic_disturbance_data_file_location=TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
        traffic_disturbance_update_frequency=TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY,
        target_fcd_segments=None,
        disturbance_repository=disturbance_repo,
        profile_repository=profile_repo,
        db_org=INFLUX_DB_ORG,
        db_url=INFLUX_DB_URL,
        db_fcd_bucket=INFLUX_DB_FCD_BUCKET,
        db_fcd_token=INFLUX_DB_FCD_TOKEN,
        db_validation_bucket=INFLUX_DB_VALIDATION_BUCKET,
        db_validation_token=INFLUX_DB_VALIDATION_TOKEN,
    )

    # =========================================================================
    # STARTUP-SPECIFIC HEALTH CHECKS
    # =========================================================================
    # These checks are used ONLY for the /startup endpoint during initial boot.
    # They verify InfluxDB connectivity without requiring the orchestrator loop
    # or workers to be initialized.
    #
    # This separation allows the pod to pass startup probes while the lengthy
    # orchestrator initialization completes (which may take time to discover
    # segments and start workers).
    # =========================================================================
    logger.info("Registering startup-only health checks (connectivity only)...")

    # Startup check: InfluxDB FCD bucket connectivity
    influx_fcd_startup = InfluxDBHealthCheck(
        name="influxdb_fcd_startup",
        url=INFLUX_DB_URL,
        token=INFLUX_DB_FCD_TOKEN,
        org=INFLUX_DB_ORG,
        bucket=INFLUX_DB_FCD_BUCKET,
        critical=True,
    )
    health_server.add_check("influxdb_fcd", influx_fcd_startup, startup_only=True)

    # Startup check: InfluxDB Validation bucket connectivity
    influx_validation_startup = InfluxDBHealthCheck(
        name="influxdb_validation_startup",
        url=INFLUX_DB_URL,
        token=INFLUX_DB_VALIDATION_TOKEN,
        org=INFLUX_DB_ORG,
        bucket=INFLUX_DB_VALIDATION_BUCKET,
        critical=True,
    )
    health_server.add_check(
        "influxdb_validation", influx_validation_startup, startup_only=True
    )

    # =========================================================================
    # REGULAR HEALTH CHECKS (for /ready and /health/detail endpoints)
    # =========================================================================
    logger.info("Registering regular health checks...")

    # Database health checks (with data freshness verification)
    health_server.add_check(
        "influxdb_fcd",
        FCDDatabaseHealthCheck(
            url=INFLUX_DB_URL,
            token=INFLUX_DB_FCD_TOKEN,
            org=INFLUX_DB_ORG,
            bucket=INFLUX_DB_FCD_BUCKET,
            data_freshness_hours=FCD_DATA_FRESHNESS_HOURS,
        ),
    )

    health_server.add_check(
        "influxdb_validation",
        ValidationDatabaseHealthCheck(
            url=INFLUX_DB_URL,
            token=INFLUX_DB_VALIDATION_TOKEN,
            org=INFLUX_DB_ORG,
            bucket=INFLUX_DB_VALIDATION_BUCKET,
        ),
    )

    # Disturbance data health check
    health_server.add_check(
        "disturbance_data",
        DisturbanceDataHealthCheck(
            file_path=TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
            max_age_minutes=DISTURBANCE_DATA_MAX_AGE_MINUTES,
            critical=False,  # Service can start without disturbance data
        ),
    )

    # Worker and orchestrator health checks
    health_server.add_check(
        "worker_status",
        WorkerStatusHealthCheck(
            manager=manager,
            health_threshold_percent=WORKER_HEALTH_THRESHOLD_PERCENT,
        ),
    )

    health_server.add_check(
        "orchestrator_loop",
        OrchestratorHealthCheck(
            manager=manager,
            max_cycle_time_minutes=ORCHESTRATOR_MAX_CYCLE_TIME_MINUTES,
            deadlock_threshold_minutes=ORCHESTRATOR_DEADLOCK_THRESHOLD_MINUTES,
        ),
    )

    # Start health server with async integration
    logger.info(f"Starting health server on port {HEALTH_CHECK_PORT}...")
    # Run health server as background task to avoid blocking; store reference
    # so exceptions are not silently swallowed and the task can be cancelled on shutdown.
    health_task = asyncio.create_task(health_server.start_async())
    await asyncio.sleep(0.1)  # Give server time to start

    try:
        # Start the manager's main loop and let it run forever.
        # This loop will discover and manage all the individual road segment tasks.
        logger.info("Starting orchestration loop...")
        await manager.run_main_loop()
    except asyncio.CancelledError:
        logger.info("###########################################")
        logger.info("Main manager task was cancelled. Shutting down.")
        logger.info("###########################################")
    except Exception as e:
        logger.error(
            f"A critical error occurred in the IdeaHelsinkiManager: {e}", exc_info=True
        )
        sys.exit(1)  # Exit with an error code
    finally:
        # stop_async() sets should_exit=True and waits for uvicorn to complete
        # its ASGI lifespan shutdown sequence before returning.  This prevents
        # asyncio.CancelledError from propagating through starlette's lifespan
        # receive queue (see https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/371).
        await health_server.stop_async()
        # By the time stop_async() returns, health_task should already be done.
        # Cancel only as a fallback in case of a timeout or unexpected state.
        if not health_task.done():
            logger.debug(
                "Health task still running after stop_async(); cancelling as fallback"
            )
            health_task.cancel()
        await asyncio.gather(health_task, return_exceptions=True)


if __name__ == "__main__":
    from idea_shared.observability.sentry import configure_sentry

    configure_sentry("orchestrator")

    logger.info("###########################################")
    logger.info("## Starting IDEA Helsinki Service Runner ##")
    logger.info("###########################################")

    try:
        # Start the main function - signal handlers are now set up inside main()
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program stopped by user (Ctrl+C).")
    finally:
        logger.info("Event loop closed.")
