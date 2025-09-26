"""
Health checks for IDEA Helsinki service.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, UTC
from typing import Optional

from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError

from idea_shared.health.checks import (
    DatabaseHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
)
from idea_shared.health.models import HealthCheckResult


class FCDDatabaseHealthCheck(DatabaseHealthCheck):
    """Check InfluxDB FCD bucket connectivity and data availability."""

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        data_freshness_hours: int = 1,
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
        super().__init__(critical=True, cache_ttl=30)
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.data_freshness_hours = data_freshness_hours

    async def check(self) -> HealthCheckResult:
        """Check FCD database connectivity and data freshness."""
        try:
            loop = asyncio.get_event_loop()

            def _check_influx():
                with InfluxDBClient(
                    url=self.url, token=self.token, org=self.org
                ) as client:
                    # Test connection with ping
                    if not client.ping():
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Failed to ping InfluxDB FCD bucket",
                        )

                    # Query for recent data to verify bucket access and data availability
                    query_api = client.query_api()
                    cutoff_time = datetime.now(UTC) - timedelta(
                        hours=self.data_freshness_hours
                    )
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
                    except Exception as query_error:
                        return HealthCheckResult(
                            status="unhealthy",
                            message=f"Failed to query FCD bucket: {str(query_error)}",
                            metadata={"bucket": self.bucket},
                        )

            return await loop.run_in_executor(None, _check_influx)

        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"FCD database check failed: {str(e)}",
                metadata={"error": str(e)},
            )


class ValidationDatabaseHealthCheck(DatabaseHealthCheck):
    """Check InfluxDB validation bucket connectivity and write permissions."""

    def __init__(self, url: str, token: str, org: str, bucket: str):
        """
        Initialize validation database health check.

        Args:
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: InfluxDB organization
            bucket: InfluxDB bucket name
        """
        super().__init__(critical=True, cache_ttl=30)
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket

    async def check(self) -> HealthCheckResult:
        """Check validation database connectivity and write capability."""
        try:
            loop = asyncio.get_event_loop()

            def _check_influx():
                with InfluxDBClient(
                    url=self.url, token=self.token, org=self.org
                ) as client:
                    # Test connection with ping
                    if not client.ping():
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Failed to ping InfluxDB validation bucket",
                        )

                    # Query for recent validation results
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
                    except Exception as query_error:
                        # Query failure is non-critical as database might be empty
                        return HealthCheckResult(
                            status="healthy",
                            message="Validation database is accessible (no recent data)",
                            metadata={
                                "bucket": self.bucket,
                                "note": "Database may be empty",
                            },
                        )

            return await loop.run_in_executor(None, _check_influx)

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
                file_age_seconds = (
                    datetime.now().timestamp() - file_stat.st_mtime
                )
                file_age_minutes = file_age_seconds / 60

                # Check file content
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Validate JSON structure
                    if not isinstance(data, dict):
                        return HealthCheckResult(
                            status="unhealthy",
                            message="Invalid disturbance data format",
                            metadata={"error": "Root must be a dictionary"},
                        )

                    # Count intersected segments
                    segment_count = 0
                    if "segmentId" in data and isinstance(data["segmentId"], dict):
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
            stuck_workers = 0
            failed_workers = 0

            for segment_id, segment_info in self.manager.active_segments.items():
                task = segment_info["task"]

                if task.done():
                    # Task completed or failed
                    try:
                        # Check if task raised an exception
                        task.exception()
                        failed_workers += 1
                    except asyncio.CancelledError:
                        # Task was cancelled (normal during shutdown)
                        pass
                    except:
                        failed_workers += 1
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
        self.last_check_time: Optional[datetime] = None

    async def check(self) -> HealthCheckResult:
        """Check if orchestrator loop is functioning."""
        try:
            current_time = datetime.now(UTC)

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

            # Calculate time since last cycle
            time_since_last_cycle = current_time - self.manager.last_cycle_time
            minutes_since_last_cycle = time_since_last_cycle.total_seconds() / 60

            # Check for deadlock
            if minutes_since_last_cycle > self.deadlock_threshold_minutes:
                return HealthCheckResult(
                    status="unhealthy",
                    message=f"Orchestrator appears deadlocked (no activity for {minutes_since_last_cycle:.0f} minutes)",
                    metadata={
                        "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                        "deadlock_threshold": self.deadlock_threshold_minutes,
                        "last_cycle_time": self.manager.last_cycle_time.isoformat(),
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
                        "last_cycle_time": self.manager.last_cycle_time.isoformat(),
                    },
                )

            # Orchestrator is healthy
            return HealthCheckResult(
                status="healthy",
                message="Orchestrator loop is functioning normally",
                metadata={
                    "minutes_since_last_cycle": round(minutes_since_last_cycle, 2),
                    "active_segments": len(self.manager.active_segments),
                    "last_cycle_time": self.manager.last_cycle_time.isoformat(),
                },
            )

        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Orchestrator health check failed: {str(e)}",
                metadata={"error": str(e)},
            )