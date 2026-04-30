"""Health checks for IDEA Helsinki service."""

import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime

from idea_shared.classes.Logger import Logger
from idea_shared.health.checks import (
    DatabaseHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
)
from idea_shared.health.models import HealthCheckResult
from idea_shared.health.utils import check_backfill_mode
from idea_shared.lib.Constants.Constants import (
    DISTURBANCE_DATA_MAX_AGE_MINUTES,
    HEALTH_CHECK_FCD_DATABASE,
    HEALTH_CHECK_VALIDATION_DATABASE,
    INFLUX_FCD_MEASUREMENT,
    INFLUX_VALIDATION_MEASUREMENT,
    INFLUXDB_CONNECTION_TTL_SECONDS,
    INFLUXDB_MAX_CONNECTIONS,
    INFLUXDB_PING_CACHE_TTL_SECONDS,
    WORKER_HEALTH_THRESHOLD_PERCENT,
)
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.influxdb_client import InfluxDBClient

# Initialize logger for health checks
logger = Logger(__name__, level=logging.INFO)


def _format_time_range(hours: float) -> dict:
    """Format time range for queries and error messages.

    Args:
        hours: Number of hours back from current time

    Returns:
        Dictionary with 'start' and 'end' ISO format timestamps

    """
    now = datetime.now(UTC)
    start_time = now.timestamp() - (hours * 3600)
    return {
        "start": datetime.fromtimestamp(start_time, UTC).isoformat(),
        "end": now.isoformat(),
    }


class InfluxDBConnectionManager:
    """Manages shared InfluxDB connections for health checks."""

    _instances: dict[str, "InfluxDBConnectionManager"] = {}
    _lock = asyncio.Lock()
    MAX_CONNECTIONS = INFLUXDB_MAX_CONNECTIONS
    CONNECTION_TTL_SECONDS = INFLUXDB_CONNECTION_TTL_SECONDS

    def __init__(self, url: str, token: str, org: str, cache_ttl: int | None = None):
        self.url = url
        self.token = token
        self.org = org
        self._client: InfluxDBClient | None = None
        self._last_ping_time: datetime | None = None
        self._ping_cache_ttl = cache_ttl or INFLUXDB_PING_CACHE_TTL_SECONDS
        self._last_access_time = datetime.now(UTC)
        self._client_lock = asyncio.Lock()

    @classmethod
    async def get_instance(
        cls, url: str, token: str, org: str, cache_ttl: int | None = None
    ) -> "InfluxDBConnectionManager":
        """Get or create a shared connection manager instance."""
        # Use SHA-256 hash of token for security instead of substring
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        key = f"{url}:{org}:{token_hash}"

        async with cls._lock:
            # Clean up stale connections before checking for existing ones
            await cls._cleanup_stale_connections()

            if key not in cls._instances:
                # Check if we've reached the connection limit
                if len(cls._instances) >= cls.MAX_CONNECTIONS:
                    # Remove the oldest connection
                    oldest_key = min(
                        cls._instances.keys(),
                        key=lambda k: cls._instances[k]._last_access_time,
                    )
                    cls._instances[oldest_key].close()
                    del cls._instances[oldest_key]

                cls._instances[key] = cls(url, token, org, cache_ttl)

            # Update last access time
            cls._instances[key]._last_access_time = datetime.now(UTC)
            return cls._instances[key]

    @classmethod
    async def _cleanup_stale_connections(cls):
        """Remove connections that haven't been used recently."""
        now = datetime.now(UTC)
        stale_keys = [
            key
            for key, instance in cls._instances.items()
            if (now - instance._last_access_time).total_seconds()
            > cls.CONNECTION_TTL_SECONDS
        ]

        for key in stale_keys:
            cls._instances[key].close()
            del cls._instances[key]

    @classmethod
    async def cleanup_all(cls):
        """Close all connections and clear the instance cache."""
        async with cls._lock:
            for instance in cls._instances.values():
                instance.close()
            cls._instances.clear()

    @classmethod
    def cleanup_all_sync(cls):
        """Close all connections without taking the asyncio lock.

        Used during process shutdown when the health-server thread (which owns
        the loop ``cls._lock`` is bound to) has already been joined and no
        concurrent access is possible.  Calling the async ``cleanup_all`` from
        the worker loop after the lock has bound to the health-server loop
        raises ``RuntimeError: ... is bound to a different event loop``.
        """
        for instance in cls._instances.values():
            instance.close()
        cls._instances.clear()

    async def get_client(self) -> InfluxDBClient:
        """Get or create a client instance (thread-safe)."""
        async with self._client_lock:
            if self._client is None:
                self._client = InfluxDBClient(
                    url=self.url, token=self.token, org=self.org
                )
            self._last_access_time = datetime.now(UTC)
            return self._client

    async def ping(self) -> bool:
        """Ping the InfluxDB server with caching.

        ``client.ping()`` is a blocking urllib3 call. Run it on a worker
        thread so ``asyncio.wait_for`` (in :class:`HealthCheck`) can
        actually deliver cancellation when InfluxDB is slow — without
        this hop, the event loop is held until the underlying HTTP read
        timeout (~10 s) regardless of the configured probe timeout
        (issue #426).
        """
        now = datetime.now(UTC)
        if (
            self._last_ping_time
            and (now - self._last_ping_time).total_seconds() < self._ping_cache_ttl
        ):
            return True

        client = await self.get_client()
        result = await asyncio.to_thread(client.ping)
        if result:
            self._last_ping_time = now
        return result

    def close(self):
        """Close the client connection."""
        if self._client:
            self._client.close()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup even on exceptions."""
        self.close()
        return False  # Don't suppress exceptions


class FCDDatabaseHealthCheck(DatabaseHealthCheck):
    """Check InfluxDB FCD bucket connectivity and data availability."""

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        data_freshness_hours: int = 1,
        backfill_lookback_days: int = 7,
        name: str | None = None,
        cache_ttl: int | None = None,
    ):
        """Initialize FCD database health check.

        Args:
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: InfluxDB organization
            bucket: InfluxDB bucket name
            data_freshness_hours: Maximum age of data in hours to consider fresh
            backfill_lookback_days: Number of days to look back for backfill mode detection (default: 7)
            name: Name of the health check (defaults to HEALTH_CHECK_FCD_DATABASE constant)
            cache_ttl: Cache time-to-live in seconds

        Raises:
            ValueError: If any required connection parameters are empty

        """
        # Validate required parameters
        if not url or not token or not org or not bucket:
            raise ValueError(
                "InfluxDB connection parameters (url, token, org, bucket) cannot be empty"
            )

        # Use constant for default name
        if name is None:
            name = HEALTH_CHECK_FCD_DATABASE

        # Use URL as connection string proxy for InfluxDB
        connection_string = f"{url}/api/v2/buckets/{bucket}"
        # critical=False: a slow or unavailable InfluxDB should NOT flip
        # /ready to 503 and trigger a pod restart. The orchestrator already
        # has a CircuitBreaker + retry layer (shared/idea_shared/resilience/)
        # for handling transient InfluxDB outages — that's the right place
        # to absorb them. Keeping the check informational (visible in
        # /health/detail as `degraded`/`unhealthy` without failing
        # readiness) prevents the deadlock observed in issue #426 where
        # InfluxDB load made every probe time out and the kubelet
        # restarted pods faster than the rollout could converge.
        super().__init__(
            name=name,
            connection_string=connection_string,
            critical=False,
            cache_ttl=cache_ttl or 30,
        )
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.data_freshness_hours = data_freshness_hours
        self.backfill_lookback_days = backfill_lookback_days
        self._cache_ttl = cache_ttl

    async def check(self) -> HealthCheckResult:
        """Check FCD database connectivity and data freshness."""
        try:
            # Get shared connection manager
            conn_manager = await InfluxDBConnectionManager.get_instance(
                self.url, self.token, self.org, self._cache_ttl
            )

            # Test connection with ping
            if not await conn_manager.ping():
                error_msg = f"Failed to ping InfluxDB FCD bucket at {self.url}"
                logger.error(
                    f"FCD database connection failure: {error_msg}",
                    exc_info=False,
                )
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message=error_msg,
                    metadata={
                        "url": self.url,
                        "bucket": self.bucket,
                        "org": self.org,
                        "error_type": "connection_failure",
                    },
                )

            async def _check_data():
                # Query for recent data to verify bucket access and data availability
                client = await conn_manager.get_client()
                query_api = client.query_api()

                # Calculate time range for better error messages
                time_range = _format_time_range(self.data_freshness_hours)

                # Convert hours to minutes for the shared utility function
                freshness_threshold_minutes = self.data_freshness_hours * 60

                try:
                    # Use shared backfill detection utility.
                    # The utility is now async and handles its own thread offloading
                    # for the blocking urllib3 calls to prevent event loop starvation.
                    (
                        has_data,
                        age_minutes,
                        backfill_timestamp,
                    ) = await check_backfill_mode(
                        query_api=query_api,
                        org=self.org,
                        bucket=self.bucket,
                        measurement=INFLUX_FCD_MEASUREMENT,
                        freshness_threshold_minutes=freshness_threshold_minutes,
                        backfill_lookback_days=self.backfill_lookback_days,
                    )

                    if has_data:
                        if backfill_timestamp and age_minutes is not None:
                            # Backfill mode - data exists but is historical
                            data_age_hours = age_minutes / 60
                            backfill_msg = f"FCD database is healthy (backfilling from {backfill_timestamp.strftime('%Y-%m-%d %H:%M')})"
                            logger.info(backfill_msg)
                            return HealthCheckResult(
                                name=self.name,
                                status="healthy",
                                message=backfill_msg,
                                metadata={
                                    "bucket": self.bucket,
                                    "mode": "backfill",
                                    "latest_data_timestamp": backfill_timestamp.isoformat(),
                                    "data_age_hours": round(data_age_hours, 2),
                                    "backfill_progress": f"Processing data from {backfill_timestamp.strftime('%Y-%m-%d')}",
                                },
                            )
                        else:
                            # Real-time mode - recent data exists
                            logger.debug(
                                f"FCD database health check passed: data found in time range {time_range['start']} to {time_range['end']}"
                            )
                            return HealthCheckResult(
                                name=self.name,
                                status="healthy",
                                message="FCD database is accessible and contains recent data",
                                metadata={
                                    "bucket": self.bucket,
                                    "has_recent_data": True,
                                    "data_freshness_hours": self.data_freshness_hours,
                                    "query_time_range": time_range,
                                    "mode": "real_time",
                                },
                            )
                    else:
                        # No data found
                        warning_msg = f"FCD database accessible but no data in last {self.data_freshness_hours} hours (queried from {time_range['start']} to {time_range['end']})"
                        logger.warning(warning_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=warning_msg,
                            metadata={
                                "bucket": self.bucket,
                                "has_recent_data": False,
                                "data_freshness_hours": self.data_freshness_hours,
                                "query_time_range": time_range,
                            },
                        )
                except InfluxDBError as query_error:
                    # Specific InfluxDB errors
                    error_msg = f"InfluxDB query failed for bucket '{self.bucket}' (time range: {time_range['start']} to {time_range['end']}): {str(query_error)}"
                    logger.error(error_msg, exc_info=True)
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=error_msg,
                        metadata={
                            "bucket": self.bucket,
                            "error_type": "InfluxDBError",
                            "query_time_range": time_range,
                            "error_details": str(query_error),
                        },
                    )
                except Exception as query_error:
                    # Other unexpected errors
                    error_msg = f"Unexpected error querying FCD bucket '{self.bucket}' (time range: {time_range['start']} to {time_range['end']}): {str(query_error)}"
                    logger.error(error_msg, exc_info=True)
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=error_msg,
                        metadata={
                            "bucket": self.bucket,
                            "error_type": type(query_error).__name__,
                            "query_time_range": time_range,
                            "error_details": str(query_error),
                        },
                    )

            return await _check_data()

        except Exception as e:
            error_msg = f"FCD database check failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=error_msg,
                metadata={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "url": self.url,
                    "bucket": self.bucket,
                },
            )


class ValidationDatabaseHealthCheck(DatabaseHealthCheck):
    """Check InfluxDB validation bucket connectivity and write permissions."""

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        name: str | None = None,
        cache_ttl: int | None = None,
    ):
        """Initialize validation database health check.

        Args:
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: InfluxDB organization
            bucket: InfluxDB bucket name
            name: Name of the health check (defaults to HEALTH_CHECK_VALIDATION_DATABASE constant)
            cache_ttl: Cache time-to-live in seconds

        Raises:
            ValueError: If any required connection parameters are empty

        """
        # Validate required parameters
        if not url or not token or not org or not bucket:
            raise ValueError(
                "InfluxDB connection parameters (url, token, org, bucket) cannot be empty"
            )

        # Use constant for default name
        if name is None:
            name = HEALTH_CHECK_VALIDATION_DATABASE

        # Use URL as connection string proxy for InfluxDB
        connection_string = f"{url}/api/v2/buckets/{bucket}"
        # critical=False — same rationale as FCDDatabaseHealthCheck (#426).
        # Resilience module owns the InfluxDB-down case; readiness should
        # not flap with InfluxDB latency.
        super().__init__(
            name=name,
            connection_string=connection_string,
            critical=False,
            cache_ttl=cache_ttl or 30,
        )
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._cache_ttl = cache_ttl

    async def check(self) -> HealthCheckResult:
        """Check validation database connectivity and write capability."""
        try:

            async def _check_connection():
                # Get shared connection manager
                conn_manager = await InfluxDBConnectionManager.get_instance(
                    self.url, self.token, self.org, self._cache_ttl
                )

                # Test connection with ping
                if not await conn_manager.ping():
                    error_msg = (
                        f"Failed to ping InfluxDB validation bucket at {self.url}"
                    )
                    logger.error(
                        f"Validation database connection failure: {error_msg}",
                        exc_info=False,
                    )
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=error_msg,
                        metadata={
                            "url": self.url,
                            "bucket": self.bucket,
                            "org": self.org,
                            "error_type": "connection_failure",
                        },
                    )

                async def _check_data():
                    # Query for recent validation results
                    client = await conn_manager.get_client()
                    query_api = client.query_api()

                    # Calculate time range for better error messages
                    time_range = _format_time_range(24)  # 24 hours

                    query = f"""
                    from(bucket: "{self.bucket}")
                        |> range(start: -24h)
                        |> filter(fn: (r) => r["_measurement"] == "{INFLUX_VALIDATION_MEASUREMENT}")
                        |> keep(columns: ["_time"])
                        |> limit(n: 1)
                    """

                    try:
                        # Run blocking urllib3 query on a worker thread so
                        # the asyncio probe timeout can actually fire (#426).
                        tables = await asyncio.to_thread(
                            query_api.query, query=query, org=self.org
                        )
                        last_write_time = None

                        for table in tables:
                            for record in table.records:
                                if record.get_time():
                                    last_write_time = record.get_time()
                                    break
                            if last_write_time:
                                break

                        if last_write_time is None:
                            # Bucket reachable but no validation rows in 24h.
                            # Treat as degraded so the gap is visible in /health/detail
                            # rather than masked behind a healthy ping.
                            warning_msg = (
                                f"Validation database accessible but no '{INFLUX_VALIDATION_MEASUREMENT}' "
                                f"data in last 24h (queried from {time_range['start']} to {time_range['end']})"
                            )
                            logger.warning(warning_msg)
                            return HealthCheckResult(
                                name=self.name,
                                status="degraded",
                                message=warning_msg,
                                metadata={
                                    "bucket": self.bucket,
                                    "measurement": INFLUX_VALIDATION_MEASUREMENT,
                                    "has_recent_data": False,
                                    "query_time_range": time_range,
                                },
                            )

                        logger.debug(
                            f"Validation database health check passed: bucket '{self.bucket}' accessible"
                        )
                        return HealthCheckResult(
                            name=self.name,
                            status="healthy",
                            message="Validation database is accessible",
                            metadata={
                                "bucket": self.bucket,
                                "measurement": INFLUX_VALIDATION_MEASUREMENT,
                                "last_write": last_write_time.isoformat(),
                                "query_time_range": time_range,
                            },
                        )
                    except InfluxDBError as query_error:
                        # InfluxDB specific errors - could indicate permission or configuration issues
                        error_msg = f"Validation database query warning for bucket '{self.bucket}' (time range: {time_range['start']} to {time_range['end']}): {str(query_error)}"
                        logger.warning(error_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=error_msg,
                            metadata={
                                "bucket": self.bucket,
                                "note": "Database accessible but query failed",
                                "error_type": "InfluxDBError",
                                "query_time_range": time_range,
                                "error_details": str(query_error),
                            },
                        )
                    except Exception as query_error:
                        # Unexpected exception — surface the failure rather
                        # than masking it as "healthy (empty bucket)". This
                        # branch previously hid SSL errors, network blips, and
                        # decode failures behind a healthy status.
                        error_msg = (
                            f"Validation database query failed for bucket "
                            f"'{self.bucket}' with unexpected {type(query_error).__name__}: "
                            f"{str(query_error)}"
                        )
                        logger.warning(error_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=error_msg,
                            metadata={
                                "bucket": self.bucket,
                                "error_type": type(query_error).__name__,
                                "error_details": str(query_error),
                                "query_time_range": time_range,
                            },
                        )

                return await _check_data()

            return await _check_connection()

        except Exception as e:
            error_msg = f"Validation database check failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=error_msg,
                metadata={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "url": self.url,
                    "bucket": self.bucket,
                },
            )


class DisturbanceDataHealthCheck(FileSystemHealthCheck):
    """Verify traffic disturbance intersection data availability and freshness."""

    def __init__(
        self,
        file_path: str,
        max_age_minutes: int = DISTURBANCE_DATA_MAX_AGE_MINUTES,
        critical: bool = False,
        name: str = "disturbance_data",
    ):
        """Initialize disturbance data health check.

        Args:
            file_path: Path to the traffic disturbance data file
            max_age_minutes: Maximum file age in minutes to consider fresh
            critical: Whether this check is critical for service readiness
            name: Name of the health check

        """
        super().__init__(
            name=name, path=file_path, check_write=False, critical=critical
        )
        self.max_age_minutes = max_age_minutes

    async def check(self) -> HealthCheckResult:
        """Check disturbance data file existence, freshness, and validity."""
        try:
            # First check if file exists using parent class
            base_result = await super().check()
            if base_result.status == "unhealthy":
                error_msg = f"Traffic disturbance data file not found at {self.path}"
                logger.warning(error_msg)
                return HealthCheckResult(
                    name=self.name,
                    status="degraded" if not self.critical else "unhealthy",
                    message=error_msg,
                    metadata={"file_path": str(self.path)},
                )

            loop = asyncio.get_running_loop()

            def _check_file():
                # Check file modification time
                file_stat = os.stat(self.path)
                file_age_seconds = datetime.now().timestamp() - file_stat.st_mtime
                file_age_minutes = file_age_seconds / 60

                # Check file content
                try:
                    with open(self.path, encoding="utf-8") as f:
                        data = json.load(f)

                    # Validate JSON structure
                    if not isinstance(data, dict):
                        error_msg = f"Invalid disturbance data format in {self.path}: root must be a dictionary"
                        logger.error(error_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="unhealthy",
                            message=error_msg,
                            metadata={
                                "error": "Root must be a dictionary",
                                "file_path": str(self.path),
                            },
                        )

                    # Validate critical fields exist and have content
                    required_fields = ["segmentId"]
                    missing_fields = [
                        field for field in required_fields if field not in data
                    ]
                    if missing_fields:
                        error_msg = f"Missing required fields in disturbance data at {self.path}: {missing_fields}"
                        logger.error(error_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="unhealthy",
                            message=error_msg,
                            metadata={
                                "missing_fields": missing_fields,
                                "available_fields": list(data.keys()),
                                "file_path": str(self.path),
                            },
                        )

                    # Validate fields have actual content (not just empty containers)
                    empty_fields = []
                    for field in required_fields:
                        if data[field] is None or (
                            isinstance(data[field], dict | list)
                            and len(data[field]) == 0
                        ):
                            empty_fields.append(field)

                    if empty_fields:
                        warning_msg = f"Required fields exist but are empty in {self.path}: {empty_fields}"
                        logger.info(warning_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=warning_msg,
                            metadata={
                                "empty_fields": empty_fields,
                                "note": "No active disturbances to process",
                                "file_path": str(self.path),
                            },
                        )

                    # Count intersected segments
                    segment_count = 0
                    if isinstance(data["segmentId"], dict):
                        segment_count = len(data["segmentId"])

                    # Determine status based on file age
                    if file_age_minutes > self.max_age_minutes:
                        warning_msg = f"Disturbance data at {self.path} is stale ({file_age_minutes:.0f} minutes old, max: {self.max_age_minutes} minutes)"
                        logger.warning(warning_msg)
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=warning_msg,
                            metadata={
                                "file_age_minutes": round(file_age_minutes, 2),
                                "max_age_minutes": self.max_age_minutes,
                                "segment_count": segment_count,
                                "file_path": str(self.path),
                            },
                        )

                    logger.debug(
                        f"Disturbance data health check passed: {self.path} is fresh ({file_age_minutes:.1f} minutes old)"
                    )
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="Disturbance data is available and fresh",
                        metadata={
                            "file_age_minutes": round(file_age_minutes, 2),
                            "segment_count": segment_count,
                            "last_modified": datetime.fromtimestamp(
                                file_stat.st_mtime
                            ).isoformat(),
                            "file_path": str(self.path),
                        },
                    )

                except json.JSONDecodeError as e:
                    error_msg = (
                        f"Invalid JSON in disturbance data file {self.path}: {str(e)}"
                    )
                    logger.error(error_msg)
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=error_msg,
                        metadata={
                            "error": str(e),
                            "error_type": "JSONDecodeError",
                            "file_path": str(self.path),
                        },
                    )
                except Exception as e:
                    error_msg = (
                        f"Failed to read disturbance data from {self.path}: {str(e)}"
                    )
                    logger.error(error_msg, exc_info=True)
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=error_msg,
                        metadata={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "file_path": str(self.path),
                        },
                    )

            return await loop.run_in_executor(None, _check_file)

        except Exception as e:
            error_msg = f"Disturbance data check failed for {self.path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=error_msg,
                metadata={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "file_path": str(self.path),
                },
            )


class WorkerStatusHealthCheck(HealthCheck):
    """Monitor status of road segment worker tasks."""

    def __init__(
        self,
        manager,
        health_threshold_percent: float | None = None,
        name: str = "worker_status",
    ):
        """Initialize worker status health check.

        Args:
            manager: Reference to IdeaHelsinkiManager instance
            health_threshold_percent: Minimum percentage of healthy workers for service health
            name: Name of the health check

        """
        super().__init__(name=name, critical=False, cache_ttl=5)
        self.manager = manager
        self.health_threshold_percent = (
            health_threshold_percent
            if health_threshold_percent is not None
            else WORKER_HEALTH_THRESHOLD_PERCENT
        )
        # Track tasks that have been checked to prevent memory leaks
        # Maps task_id to whether it failed (True) or succeeded (False)
        self._checked_tasks: dict[int, bool] = {}

    async def check(self) -> HealthCheckResult:
        """Check status of worker tasks."""
        try:
            # Snapshot active_segments before iterating: the worker loop runs on
            # a different OS thread (uvicorn now lives on its own thread/loop)
            # and may add/pop entries during iteration, which would raise
            # ``RuntimeError: dictionary changed size during iteration``.
            # ``dict(...)`` is a single C-level call and atomic under the GIL.
            active_segments_snapshot = dict(self.manager.active_segments)
            total_workers = len(active_segments_snapshot)

            if total_workers == 0:
                # No workers is normal when no disturbances are active
                # Clear checked tasks set when no workers
                self._checked_tasks.clear()
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message="No active workers (no disturbances to process)",
                    metadata={"total_workers": 0, "status": "idle"},
                )

            # Check health of each worker
            healthy_workers = 0
            failed_workers = 0
            current_task_ids = set()

            for _segment_id, segment_info in active_segments_snapshot.items():
                task = segment_info["task"]
                task_id = id(task)
                current_task_ids.add(task_id)

                if task.done():
                    # Task completed or failed
                    try:
                        # Check if task raised an exception
                        # Only retrieve exception once to prevent memory leak
                        if task_id not in self._checked_tasks:
                            exception = task.exception()
                            # Immediately discard the reference by not storing it
                            if exception is not None:
                                # Task failed with an exception
                                failed_workers += 1
                                self._checked_tasks[task_id] = True  # True = failed
                            else:
                                # Task completed successfully (should be restarted by manager)
                                healthy_workers += 1
                                self._checked_tasks[task_id] = (
                                    False  # False = succeeded
                                )
                        else:
                            # Task already checked, use stored result
                            if self._checked_tasks[task_id]:
                                failed_workers += 1
                            else:
                                healthy_workers += 1
                    except asyncio.CancelledError:
                        # Task was cancelled (normal during shutdown)
                        pass
                    except asyncio.InvalidStateError:
                        # Task is not done yet (shouldn't happen given the if condition)
                        healthy_workers += 1
                else:
                    # Task is still running
                    healthy_workers += 1

            # Clean up checked tasks that are no longer active
            # This prevents the dict from growing indefinitely
            self._checked_tasks = {
                task_id: failed
                for task_id, failed in self._checked_tasks.items()
                if task_id in current_task_ids
            }

            health_percentage = (healthy_workers / total_workers) * 100

            # Determine overall status
            if health_percentage >= self.health_threshold_percent:
                status = "healthy"
                message = f"{healthy_workers}/{total_workers} workers are healthy"
                logger.debug(message)
            elif health_percentage >= 50:
                status = "degraded"
                message = f"Only {healthy_workers}/{total_workers} workers are healthy"
                logger.warning(message)
            else:
                status = "unhealthy"
                message = f"Critical: Only {healthy_workers}/{total_workers} workers are healthy"
                logger.error(message)

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                metadata={
                    "total_workers": total_workers,
                    "healthy_workers": healthy_workers,
                    "failed_workers": failed_workers,
                    "health_percentage": round(health_percentage, 2),
                    "threshold_percent": self.health_threshold_percent,
                },
            )

        except Exception as e:
            error_msg = f"Worker status check failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=error_msg,
                metadata={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )


class OrchestratorHealthCheck(HealthCheck):
    """Verify the orchestrator loop is functioning."""

    def __init__(
        self,
        manager,
        max_cycle_time_minutes: int = 90,
        deadlock_threshold_minutes: int = 180,
        name: str = "orchestrator",
    ):
        """Initialize orchestrator health check.

        Args:
            manager: Reference to IdeaHelsinkiManager instance
            max_cycle_time_minutes: Maximum expected time for a management cycle
            deadlock_threshold_minutes: Time after which orchestrator is considered deadlocked
            name: Name of the health check

        """
        super().__init__(name=name, critical=True, cache_ttl=10)
        self.manager = manager
        self.max_cycle_time_minutes = max_cycle_time_minutes
        self.deadlock_threshold_minutes = deadlock_threshold_minutes
        self._access_lock = asyncio.Lock()

    async def check(self) -> HealthCheckResult:
        """Check if orchestrator loop is functioning."""
        try:
            current_time = datetime.now(UTC)

            # Thread-safe access to last_cycle_time
            async with self._access_lock:
                # Track orchestrator activity
                if not hasattr(self.manager, "last_cycle_time"):
                    # First check, assume orchestrator just started
                    self.manager.last_cycle_time = current_time
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="Orchestrator initialized",
                        metadata={
                            "status": "initializing",
                            "active_segments": len(self.manager.active_segments),
                        },
                    )

                # Get last cycle time safely
                last_cycle_time = self.manager.last_cycle_time

            # Calculate time since last cycle (outside the lock)
            time_since_last_cycle = current_time - last_cycle_time
            minutes_since_last_cycle = time_since_last_cycle.total_seconds() / 60

            # Check for deadlock
            if minutes_since_last_cycle > self.deadlock_threshold_minutes:
                error_msg = f"Orchestrator appears deadlocked (no activity for {minutes_since_last_cycle:.0f} minutes, threshold: {self.deadlock_threshold_minutes} minutes)"
                logger.error(error_msg)
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message=error_msg,
                    metadata={
                        "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                        "deadlock_threshold": self.deadlock_threshold_minutes,
                        "last_cycle_time": last_cycle_time.isoformat(),
                    },
                )

            # Check for slow cycles
            if minutes_since_last_cycle > self.max_cycle_time_minutes:
                warning_msg = f"Orchestrator cycle is slow ({minutes_since_last_cycle:.0f} minutes since last cycle, max expected: {self.max_cycle_time_minutes} minutes)"
                logger.warning(warning_msg)
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message=warning_msg,
                    metadata={
                        "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                        "max_cycle_time": self.max_cycle_time_minutes,
                        "last_cycle_time": last_cycle_time.isoformat(),
                    },
                )

            # Orchestrator is healthy
            logger.debug(
                f"Orchestrator health check passed: {minutes_since_last_cycle:.1f} minutes since last cycle"
            )
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Orchestrator loop is functioning normally",
                metadata={
                    "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                    "active_segments": len(self.manager.active_segments),
                    "last_cycle_time": last_cycle_time.isoformat(),
                },
            )

        except Exception as e:
            error_msg = f"Orchestrator health check failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=error_msg,
                metadata={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
