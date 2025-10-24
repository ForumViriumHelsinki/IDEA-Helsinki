# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import asyncio
import os
import signal
import sys

import sentry_sdk

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.IdeaHelsinkiManager import IdeaHelsinkiManager
from idea_shared.classes.Logger import Logger
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
    VALIDATION_MAX_AGE_DAYS,
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
    """
    Initializes and runs the main IdeaHelsinkiManager orchestration task with health checks.
    """
    global health_server

    # Setup signal handlers early for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(s, loop))
        )

    logger.info("Initializing IDEA Helsinki Manager...")

    # Initialize health server
    health_server = HealthServer(
        port=HEALTH_CHECK_PORT, app_name="IDEA Helsinki Service"
    )

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
        db_validation_token=INFLUX_DB_VALIDATION_TOKEN,
    )

    # Add service-specific health checks
    logger.info("Registering health checks...")

    # Database health checks
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
    # Run health server as background task to avoid blocking
    asyncio.create_task(health_server.start_async())
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
        if health_server:
            await health_server.stop_async()
        sys.exit(1)  # Exit with an error code


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
