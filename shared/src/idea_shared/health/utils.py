"""Utility functions for health checks."""

from datetime import UTC, datetime

from influxdb_client.client.query_api import QueryApi


def _get_latest_record_time(tables) -> datetime | None:
    """Extract timestamp from first valid record in tables.

    Args:
        tables: List of InfluxDB table results

    Returns:
        Timestamp of the first valid record, or None if no valid records found

    """
    for table in tables:
        if len(table.records) > 0 and hasattr(table.records[0], "get_time"):
            return table.records[0].get_time()
    return None


def check_backfill_mode(
    query_api: QueryApi,
    org: str,
    bucket: str,
    measurement: str,
    freshness_threshold_minutes: int,
    backfill_lookback_days: int,
) -> tuple[bool, float | None, datetime | None]:
    """Check if InfluxDB data is in backfill mode or real-time mode.

    This function queries InfluxDB to determine if the system is processing
    real-time data or backfilling historical data. It does this by:
    1. Checking for recent data within the freshness threshold
    2. If no recent data, checking for any data within the backfill lookback window
    3. Determining mode based on the age of the latest data

    Args:
        query_api: InfluxDB query API instance
        org: InfluxDB organization name
        bucket: Bucket name to query
        measurement: Measurement name to filter
        freshness_threshold_minutes: Time window for "recent" data (minutes)
        backfill_lookback_days: Maximum lookback period for backfill detection (days)

    Returns:
        Tuple of (has_data, age_minutes, backfill_timestamp):
        - has_data: True if data exists, False otherwise
        - age_minutes: Age of the latest data in minutes (None if no data)
        - backfill_timestamp: Timestamp of latest data if in backfill mode (None if real-time or no data)

    Examples:
        Real-time mode: (True, 5.2, None) - data is 5.2 minutes old, within threshold
        Backfill mode: (True, 1440.0, datetime(...)) - data is 24 hours old, beyond threshold
        No data: (False, None, None) - no data found in lookback window

    Raises:
        ValueError: If bucket or measurement names contain invalid characters

    """
    # Validate bucket and measurement names to prevent query injection
    if not bucket.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"Invalid bucket name: {bucket}")
    if not measurement.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"Invalid measurement name: {measurement}")

    # Query for recent data (normal operation mode)
    # Use keep(columns: ["_time"]) to reduce data transfer since only timestamp is needed
    recent_query = f"""
    from(bucket: "{bucket}")
        |> range(start: -{freshness_threshold_minutes}m)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> last()
        |> keep(columns: ["_time"])
        |> limit(n: 1)
    """

    # Query for the most recent data point (bounded lookback for performance)
    latest_query = f"""
    from(bucket: "{bucket}")
        |> range(start: -{backfill_lookback_days}d)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> last()
        |> keep(columns: ["_time"])
        |> limit(n: 1)
    """

    # Check for recent data first
    recent_tables = query_api.query(query=recent_query, org=org)
    last_record_time = _get_latest_record_time(recent_tables)

    if last_record_time is not None:
        # Found recent data - calculate age and return real-time mode
        # Note: We return real-time mode for ANY data found within the freshness window,
        # even if it's approaching the threshold (e.g., 29 minutes old with 30-minute threshold).
        # This is intentional - if data exists in the recent query window, the system is
        # considered to be in real-time operation mode, not backfill mode.
        age_minutes = (datetime.now(UTC) - last_record_time).total_seconds() / 60
        return True, age_minutes, None  # Real-time mode

    # No recent data - check if we're in backfill mode
    latest_tables = query_api.query(query=latest_query, org=org)
    latest_data_time = _get_latest_record_time(latest_tables)

    if latest_data_time is not None:
        # Calculate age of the latest data
        age_minutes = (datetime.now(UTC) - latest_data_time).total_seconds() / 60

        # If data is significantly old, we're in backfill mode
        if age_minutes > freshness_threshold_minutes:
            return True, age_minutes, latest_data_time  # Backfill mode

    # No data found in lookback window
    return False, None, None
