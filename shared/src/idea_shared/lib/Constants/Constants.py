# ------------------------------------------------------#
# ------------------ CONSTANTS -------------------------#
# ------------------------------------------------------#
import os

# IDEA CLASS DEFAULTS
PROFILE_TIME_FRAME_WEEKS = 26
PROFILE_END_LEAD_TIME_HOURS = 48
VALIDATION_UPDATE_FREQUENCY = 5  # In minutes
VALIDATION_MAX_AGE_DAYS = 7  # If the validation process is interrupted (system crash & restart etc.), how old can the last validation be for restart reference (running mean)

# TRAFFIC DISTURBANCE PROVIDER DEFAULTS
TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY = 60  # In minutes
## File I/O
DATA_DIR = os.getenv("DATA_DIR", "data")
TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION = os.path.join(
    DATA_DIR, "traffic_disturbance_data.json"
)
# What disturbances to monitor
TRAFFIC_DISTURBANCES_TO_MONITOR = ["Kaivuilmoitus_alue", "Aluevuokraus_alue"]

# TOMTOM PROVIDER DEFAULTS
FCD_UPDATE_FREQUENCY = 5  # In minutes

# FCD database update max downtime. How old can the last database update be to be acceptable in the FCD_UPDATE_FREQUENCY update cycle?
MAX_FCD_DATA_BASE_UPDATE_DOWNTIME = 2  # In days

# FCD segment id and geometry info = segment ids and their location
FCD_MAP_DATA_FILE_LOCATION = os.path.join(DATA_DIR, "segments_mapping.json")
FCD_MAP_UPDATE_FREQUENCY = 30  # in minutes
MASTER_SEGMENT_HISTORY_FILE_LOCATION = os.path.join(
    DATA_DIR, "master_segment_history.json"
)
ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION = os.path.join(
    DATA_DIR, "archived_segment_history.json"
)

# FCD HISTORY DEFAULTS
## Start date for the FCD history, or the defined start date for it. format YYYY-MM-DD
FCD_HISTORY_START_DATE = "2024-12-05"

# FCD MULTI-THREADING CONFIGURATION
## Enable/disable multi-threaded processing for FCD Manager
FCD_ENABLE_MULTITHREADING = (
    os.getenv("FCD_ENABLE_MULTITHREADING", "true").lower() == "true"
)

## Number of parallel backfill worker threads for historical data processing
## Default: 4 (recommended for systems with 1500m CPU allocation)
## Set to 0 to auto-detect based on CPU cores
FCD_BACKFILL_WORKER_COUNT = int(os.getenv("FCD_BACKFILL_WORKER_COUNT", "4"))

## Number of days per chunk for parallel backfill processing
## Smaller chunks = more parallelism but more overhead
## Larger chunks = less parallelism but more efficient per chunk
## Default: 1 day prevents memory exhaustion (7 days can use 8-16 GB per worker)
## With 4 workers: 1-day chunks use ~2-3 GB total vs 8-16 GB with 7-day chunks
FCD_BACKFILL_CHUNK_DAYS = int(os.getenv("FCD_BACKFILL_CHUNK_DAYS", "1"))

## Maximum size of the InfluxDB write queue (number of pending write requests)
## This provides backpressure if workers produce faster than InfluxDB can consume
## Default: 100 provides good buffering without excessive memory usage
FCD_WRITE_QUEUE_MAX_SIZE = int(os.getenv("FCD_WRITE_QUEUE_MAX_SIZE", "100"))

## Timeout for write queue operations (seconds)
## How long to wait when queue is full before raising an error
FCD_WRITE_QUEUE_TIMEOUT = int(os.getenv("FCD_WRITE_QUEUE_TIMEOUT", "30"))

## Maximum number of retries for failed date range chunks
## After this many retries, the chunk is moved to dead-letter queue
FCD_MAX_CHUNK_RETRIES = int(os.getenv("FCD_MAX_CHUNK_RETRIES", "3"))

## Delay in seconds before retrying a failed chunk
## Uses exponential backoff: delay * (2 ** retry_count)
FCD_RETRY_DELAY_SECONDS = int(os.getenv("FCD_RETRY_DELAY_SECONDS", "10"))

## Timeout in seconds for graceful shutdown
## Workers will attempt to finish current tasks within this timeframe
FCD_SHUTDOWN_TIMEOUT_SECONDS = int(os.getenv("FCD_SHUTDOWN_TIMEOUT_SECONDS", "300"))

# HEALTH CHECK DEFAULTS
HEALTH_CHECK_PORT = 8080
HEALTH_CHECK_TIMEOUT_SECONDS = 10
HEALTH_CHECK_CACHE_TTL_SECONDS = 5

# InfluxDB connection pool settings
INFLUXDB_MAX_CONNECTIONS = 10
INFLUXDB_CONNECTION_TTL_SECONDS = 3600
INFLUXDB_PING_CACHE_TTL_SECONDS = 5

# Worker and orchestrator health thresholds
WORKER_HEALTH_THRESHOLD_PERCENT = 80
DISTURBANCE_DATA_MAX_AGE_MINUTES = 120

# Health check request and orchestrator settings
HEALTH_CHECK_REQUEST_TIMEOUT_SECONDS = 5  # Timeout for individual health check requests
ORCHESTRATOR_MAX_CYCLE_TIME_MINUTES = (
    90  # Maximum expected time for an orchestrator management cycle
)
ORCHESTRATOR_DEADLOCK_THRESHOLD_MINUTES = (
    180  # Time after which orchestrator is considered deadlocked
)
FCD_DATA_FRESHNESS_HOURS = 1  # Maximum age of FCD data in hours to consider fresh

# Health check names
HEALTH_CHECK_FCD_DATABASE = "fcd_database"
HEALTH_CHECK_VALIDATION_DATABASE = "validation_database"

# Update freshness thresholds for Traffic Monitor
UPDATE_FRESHNESS_HEALTHY_MINUTES = 90  # Consider healthy if last update < 90 minutes
UPDATE_FRESHNESS_DEGRADED_MINUTES = (
    180  # Consider degraded if < 180 minutes, unhealthy if > 180
)

# FCD mapping freshness threshold
FCD_MAPPING_MAX_AGE_MINUTES = (
    15  # FCD mapping file should be updated at least every 15 minutes
)

# WFS API health check settings
WFS_HEALTH_CHECK_TIMEOUT = 10  # Timeout for WFS health check in seconds
WFS_HEALTH_CHECK_MAX_FEATURES = 1  # Max features to request in health check
WFS_HEALTH_CHECK_CACHE_TTL = 30  # Cache WFS health check results for 30 seconds
