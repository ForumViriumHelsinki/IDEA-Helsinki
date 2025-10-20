"""Utility functions for health checks."""

from datetime import UTC, datetime

from influxdb_client import InfluxDBClient


def check_backfill_mode(
    query_api,
    org: str,
    bucket: str,
    measurement: str,
    freshness_threshold_minutes: int,
    backfill_lookback_days: int,
) -> tuple[bool, float | None, datetime | None]:
    """
    Check if InfluxDB data is in backfill mode or real-time mode.

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
    """
    # Query for recent data (normal operation mode)
    recent_query = f"""
    from(bucket: "{bucket}")
        |> range(start: -{freshness_threshold_minutes}m)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> last()
        |> limit(n: 1)
    """

    # Query for the most recent data point (bounded lookback for performance)
    latest_query = f"""
    from(bucket: "{bucket}")
        |> range(start: -{backfill_lookback_days}d)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> last()
        |> limit(n: 1)
    """

    # Check for recent data first
    recent_tables = query_api.query(query=recent_query, org=org)
    has_recent_data = any(len(table.records) > 0 for table in recent_tables)

    if has_recent_data:
        # Found recent data - extract timestamp and calculate age
        for table in recent_tables:
            if len(table.records) > 0:
                last_record_time = table.records[0].get_time()
                age_minutes = (datetime.now(UTC) - last_record_time).total_seconds() / 60
                return True, age_minutes, None  # Real-time mode

    # No recent data - check if we're in backfill mode
    latest_tables = query_api.query(query=latest_query, org=org)
    has_any_data = any(len(table.records) > 0 for table in latest_tables)

    if has_any_data:
        # Get the timestamp of the latest data
        for table in latest_tables:
            if len(table.records) > 0:
                latest_record = table.records[0]
                if hasattr(latest_record, "get_time"):
                    latest_data_time = latest_record.get_time()
                    age_minutes = (
                        datetime.now(UTC) - latest_data_time
                    ).total_seconds() / 60

                    # If data is significantly old, we're in backfill mode
                    if age_minutes > freshness_threshold_minutes:
                        return True, age_minutes, latest_data_time  # Backfill mode

    # No data found in lookback window
    return False, None, None
