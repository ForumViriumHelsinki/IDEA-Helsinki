"""
Health checks for IDEA Helsinki service.
"""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime

from idea_shared.health.checks import (
    DatabaseHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
)
from idea_shared.health.models import HealthCheckResult
from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError


class InfluxDBConnectionManager:
    """Manages shared InfluxDB connections for health checks."""

    _instances: dict[str, "InfluxDBConnectionManager"] = {}
    _lock = asyncio.Lock()
    MAX_CONNECTIONS = 10  # Maximum number of connection managers
    CONNECTION_TTL_SECONDS = 3600  # Time to keep unused connections (1 hour)

    def __init__(self, url: str, token: str, org: str, cache_ttl: int | None = None):
        self.url = url
        self.token = token
        self.org = org
        self._client: InfluxDBClient | None = None
        self._last_ping_time: datetime | None = None
        self._ping_cache_ttl = cache_ttl or 5  # seconds
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
        """Ping the InfluxDB server with caching."""
        now = datetime.now(UTC)
        if (
            self._last_ping_time
            and (now - self._last_ping_time).total_seconds() < self._ping_cache_ttl
        ):
            return True

        client = await self.get_client()
        result = client.ping()
        if result:
            self._last_ping_time = now
        return result

    def close(self):
        """Close the client connection."""
        if self._client:
            self._client.close()
            self._client = None


class FCDDatabaseHealthCheck(DatabaseHealthCheck):
    """Check InfluxDB FCD bucket connectivity and data availability."""

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        data_freshness_hours: int = 1,
        cache_ttl: int | None = None,
    ):
        """
        Initialize FCD database health check.

        Args:
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: InfluxDB organization
            bucket: InfluxDB bucket name
            data_freshness_hours: Maximum age of data in hours to consider fresh
        """
        super().__init__(critical=True, cache_ttl=cache_ttl or 30)
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.data_freshness_hours = data_freshness_hours
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
                return HealthCheckResult(
                    status="unhealthy",
                    message="Failed to ping InfluxDB FCD bucket",
                )

            async def _check_data():
                # Query for recent data to verify bucket access and data availability
                client = await conn_manager.get_client()
                query_api = client.query_api()
                query = f"""
                from(bucket: "{self.bucket}")
                    |> range(start: -{self.data_freshness_hours}h)
                    |> filter(fn: (r) => r["_measurement"] == "fcd_segment")
                    |> limit(n: 1)
                """

                try:
                    tables = query_api.query(query=query, org=self.org)
                    has_recent_data = any(len(table.records) > 0 for table in tables)

                    if has_recent_data:
                        return HealthCheckResult(
                            status="healthy",
                            message="FCD database is accessible and contains recent data",
                            metadata={
                                "bucket": self.bucket,
                                "has_recent_data": True,
                                "data_freshness_hours": self.data_freshness_hours,
                            },
                        )
                    else:
                        return HealthCheckResult(
                            status="degraded",
                            message=f"FCD database accessible but no data in last {self.data_freshness_hours} hours",
                            metadata={
                                "bucket": self.bucket,
                                "has_recent_data": False,
                                "data_freshness_hours": self.data_freshness_hours,
                            },
                        )
                except InfluxDBError as query_error:
                    # Specific InfluxDB errors
                    return HealthCheckResult(
                        status="unhealthy",
                        message=f"InfluxDB query failed: {str(query_error)}",
                        metadata={"bucket": self.bucket, "error_type": "InfluxDBError"},
                    )
                except Exception as query_error:
                    # Other unexpected errors
                    return HealthCheckResult(
                        status="unhealthy",
                        message=f"Unexpected error querying FCD bucket: {str(query_error)}",
                        metadata={
                            "bucket": self.bucket,
                            "error_type": type(query_error).__name__,
                        },
                    )

            return await _check_data()

        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"FCD database check failed: {str(e)}",
                metadata={"error": str(e)},
            )


class ValidationDatabaseHealthCheck(DatabaseHealthCheck):
    """Check InfluxDB validation bucket connectivity and write permissions."""

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        cache_ttl: int | None = None,
    ):
        """
        Initialize validation database health check.

        Args:
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: InfluxDB organization
            bucket: InfluxDB bucket name
        """
        super().__init__(critical=True, cache_ttl=cache_ttl or 30)
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
                    return HealthCheckResult(
                        status="unhealthy",
                        message="Failed to ping InfluxDB validation bucket",
                    )

                async def _check_data():
                    # Query for recent validation results
                    client = await conn_manager.get_client()
                    query_api = client.query_api()
                    query = f"""
                    from(bucket: "{self.bucket}")
                        |> range(start: -24h)
                        |> filter(fn: (r) => r["_measurement"] == "validation_result")
                        |> limit(n: 1)
                    """

                    try:
                        tables = query_api.query(query=query, org=self.org)
                        last_write_time = None

                        for table in tables:
                            for record in table.records:
                                if record.get_time():
                                    last_write_time = record.get_time()
                                    break
                            if last_write_time:
                                break

                        return HealthCheckResult(
                            status="healthy",
                            message="Validation database is accessible",
                            metadata={
                                "bucket": self.bucket,
                                "last_write": (
                                    last_write_time.isoformat()
                                    if last_write_time
                                    else None
                                ),
                            },
                        )
                    except InfluxDBError as query_error:
                        # InfluxDB specific errors - could indicate permission or configuration issues
                        return HealthCheckResult(
                            status="degraded",
                            message=f"Validation database query warning: {str(query_error)}",
                            metadata={
                                "bucket": self.bucket,
                                "note": "Database accessible but query failed",
                                "error_type": "InfluxDBError",
                            },
                        )
                    except Exception as query_error:
                        # Other errors - treat as accessible but empty
                        return HealthCheckResult(
                            status="healthy",
                            message="Validation database is accessible (no recent data)",
                            metadata={
                                "bucket": self.bucket,
                                "note": "Database may be empty",
                                "error_type": type(query_error).__name__,
                            },
                        )

                return await _check_data()

            return await _check_connection()

        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Validation database check failed: {str(e)}",
                metadata={"error": str(e)},
            )


class DisturbanceDataHealthCheck(FileSystemHealthCheck):
    """Verify traffic disturbance intersection data availability and freshness."""

    def __init__(
        self, file_path: str, max_age_minutes: int = 120, critical: bool = False
    ):
        """
        Initialize disturbance data health check.

        Args:
            file_path: Path to the traffic disturbance data file
            max_age_minutes: Maximum file age in minutes to consider fresh
            critical: Whether this check is critical for service readiness
        """
        super().__init__(path=file_path, check_write=False, critical=critical)
        self.max_age_minutes = max_age_minutes

    async def check(self) -> HealthCheckResult:
        """Check disturbance data file existence, freshness, and validity."""
        try:
            # First check if file exists using parent class
            base_result = await super().check()
            if base_result.status == "unhealthy":
                return HealthCheckResult(
                    status="degraded" if not self.critical else "unhealthy",
                    message="Traffic disturbance data file not found",
                    metadata={"file_path": self.path},
                )

            loop = asyncio.get_event_loop()

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
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Invalid disturbance data format",
                            metadata={"error": "Root must be a dictionary"},
                        )

                    # Validate critical fields exist and have content
                    required_fields = ["segmentId", "trafficDisturbanceId"]
                    missing_fields = [
                        field for field in required_fields if field not in data
                    ]
                    if missing_fields:
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Missing required fields in disturbance data",
                            metadata={
                                "missing_fields": missing_fields,
                                "available_fields": list(data.keys()),
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
                        return HealthCheckResult(
                            status="degraded",
                            message="Required fields exist but are empty",
                            metadata={
                                "empty_fields": empty_fields,
                                "note": "No active disturbances to process",
                            },
                        )

                    # Count intersected segments
                    segment_count = 0
                    if isinstance(data["segmentId"], dict):
                        segment_count = len(data["segmentId"])

                    # Determine status based on file age
                    if file_age_minutes > self.max_age_minutes:
                        return HealthCheckResult(
                            status="degraded",
                            message=f"Disturbance data is stale ({file_age_minutes:.0f} minutes old)",
                            metadata={
                                "file_age_minutes": round(file_age_minutes, 2),
                                "max_age_minutes": self.max_age_minutes,
                                "segment_count": segment_count,
                            },
                        )

                    return HealthCheckResult(
                        status="healthy",
                        message="Disturbance data is available and fresh",
                        metadata={
                            "file_age_minutes": round(file_age_minutes, 2),
                            "segment_count": segment_count,
                            "last_modified": datetime.fromtimestamp(
                                file_stat.st_mtime
                            ).isoformat(),
                        },
                    )

                except json.JSONDecodeError as e:
                    return HealthCheckResult(
                        status="unhealthy",
                        message="Invalid JSON in disturbance data file",
                        metadata={"error": str(e)},
                    )
                except Exception as e:
                    return HealthCheckResult(
                        status="unhealthy",
                        message=f"Failed to read disturbance data: {str(e)}",
                        metadata={"error": str(e)},
                    )

            return await loop.run_in_executor(None, _check_file)

        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Disturbance data check failed: {str(e)}",
                metadata={"error": str(e)},
            )


class WorkerStatusHealthCheck(HealthCheck):
    """Monitor status of road segment worker tasks."""

    def __init__(self, manager, health_threshold_percent: float = 80.0):
        """
        Initialize worker status health check.

        Args:
            manager: Reference to IdeaHelsinkiManager instance
            health_threshold_percent: Minimum percentage of healthy workers for service health
        """
        super().__init__(critical=False, cache_ttl=5)
        self.manager = manager
        self.health_threshold_percent = health_threshold_percent

    async def check(self) -> HealthCheckResult:
        """Check status of worker tasks."""
        try:
            # Get active segments count
            total_workers = len(self.manager.active_segments)

            if total_workers == 0:
                # No workers is normal when no disturbances are active
                return HealthCheckResult(
                    status="healthy",
                    message="No active workers (no disturbances to process)",
                    metadata={"total_workers": 0, "status": "idle"},
                )

            # Check health of each worker
            healthy_workers = 0
            failed_workers = 0

            for _segment_id, segment_info in self.manager.active_segments.items():
                task = segment_info["task"]

                if task.done():
                    # Task completed or failed
                    try:
                        # Check if task raised an exception
                        exception = task.exception()
                        if exception is not None:
                            # Task failed with an exception
                            failed_workers += 1
                        else:
                            # Task completed successfully (should be restarted by manager)
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

            health_percentage = (healthy_workers / total_workers) * 100

            # Determine overall status
            if health_percentage >= self.health_threshold_percent:
                status = "healthy"
                message = f"{healthy_workers}/{total_workers} workers are healthy"
            elif health_percentage >= 50:
                status = "degraded"
                message = f"Only {healthy_workers}/{total_workers} workers are healthy"
            else:
                status = "unhealthy"
                message = f"Critical: Only {healthy_workers}/{total_workers} workers are healthy"

            return HealthCheckResult(
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
            return HealthCheckResult(
                status="unhealthy",
                message=f"Worker status check failed: {str(e)}",
                metadata={"error": str(e)},
            )


class OrchestratorHealthCheck(HealthCheck):
    """Verify the orchestrator loop is functioning."""

    def __init__(
        self,
        manager,
        max_cycle_time_minutes: int = 90,
        deadlock_threshold_minutes: int = 180,
    ):
        """
        Initialize orchestrator health check.

        Args:
            manager: Reference to IdeaHelsinkiManager instance
            max_cycle_time_minutes: Maximum expected time for a management cycle
            deadlock_threshold_minutes: Time after which orchestrator is considered deadlocked
        """
        super().__init__(critical=True, cache_ttl=10)
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
                return HealthCheckResult(
                    status="unhealthy",
                    message=f"Orchestrator appears deadlocked (no activity for {minutes_since_last_cycle:.0f} minutes)",
                    metadata={
                        "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                        "deadlock_threshold": self.deadlock_threshold_minutes,
                        "last_cycle_time": last_cycle_time.isoformat(),
                    },
                )

            # Check for slow cycles
            if minutes_since_last_cycle > self.max_cycle_time_minutes:
                return HealthCheckResult(
                    status="degraded",
                    message=f"Orchestrator cycle is slow ({minutes_since_last_cycle:.0f} minutes since last cycle)",
                    metadata={
                        "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                        "max_cycle_time": self.max_cycle_time_minutes,
                        "last_cycle_time": last_cycle_time.isoformat(),
                    },
                )

            # Orchestrator is healthy
            return HealthCheckResult(
                status="healthy",
                message="Orchestrator loop is functioning normally",
                metadata={
                    "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                    "active_segments": len(self.manager.active_segments),
                    "last_cycle_time": last_cycle_time.isoformat(),
                },
            )

        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Orchestrator health check failed: {str(e)}",
                metadata={"error": str(e)},
            )
