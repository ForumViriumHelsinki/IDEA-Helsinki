"""FCD Manager specific health check implementations."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from idea_shared.health.checks import HealthCheck
from idea_shared.health.models import HealthCheckResult


class UpdateCycleHealthCheck(HealthCheck):
    """Health check for monitoring FCD Manager update cycle freshness.

    This check monitors when the last successful update cycle was completed,
    which is critical for ensuring the service is actively processing data.
    """

    def __init__(
        self,
        name: str = "update_cycle",
        healthy_threshold_minutes: int = 10,
        degraded_threshold_minutes: int = 30,
        timeout: float = 1.0,
        critical: bool = False,  # Not critical for liveness, but useful for monitoring
        cache_ttl: float = 5.0,
    ):
        """Initialize update cycle health check.

        Args:
            name: Name of the health check
            healthy_threshold_minutes: Max minutes since last update for healthy status
            degraded_threshold_minutes: Max minutes since last update before unhealthy
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.healthy_threshold = timedelta(minutes=healthy_threshold_minutes)
        self.degraded_threshold = timedelta(minutes=degraded_threshold_minutes)
        self.last_update_time: datetime | None = None
        self.startup_time = datetime.now(UTC)
        self.startup_grace_period = timedelta(minutes=healthy_threshold_minutes)

    def update_timestamp(self) -> None:
        """Update the last successful update timestamp.

        This should be called by the main loop after each successful update cycle.
        """
        self.last_update_time = datetime.now(UTC)

    async def check(self) -> HealthCheckResult:
        """Check if the update cycle is running within expected timeframes.

        Returns:
            HealthCheckResult indicating update cycle health
        """
        now = datetime.now(UTC)

        # During startup grace period, always return healthy
        if (now - self.startup_time) < self.startup_grace_period:
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Service is starting up (grace period active)",
                metadata={
                    "startup_time": self.startup_time.isoformat(),
                    "grace_period_minutes": self.startup_grace_period.total_seconds()
                    / 60,
                },
            )

        # If no updates have been recorded yet after grace period
        if self.last_update_time is None:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="No update cycles completed since startup",
                metadata={
                    "startup_time": self.startup_time.isoformat(),
                    "time_since_startup_minutes": (
                        now - self.startup_time
                    ).total_seconds()
                    / 60,
                },
            )

        # Calculate time since last update
        time_since_update = now - self.last_update_time
        minutes_since_update = time_since_update.total_seconds() / 60

        # Determine health status
        if time_since_update < self.healthy_threshold:
            status = "healthy"
            message = f"Update cycle is running normally ({minutes_since_update:.1f} minutes ago)"
        elif time_since_update < self.degraded_threshold:
            status = "degraded"
            message = (
                f"Update cycle is delayed ({minutes_since_update:.1f} minutes ago)"
            )
        else:
            status = "unhealthy"
            message = f"Update cycle has not run for {minutes_since_update:.1f} minutes"

        return HealthCheckResult(
            name=self.name,
            status=status,
            message=message,
            metadata={
                "last_update": self.last_update_time.isoformat(),
                "minutes_since_update": minutes_since_update,
                "healthy_threshold_minutes": self.healthy_threshold.total_seconds()
                / 60,
                "degraded_threshold_minutes": self.degraded_threshold.total_seconds()
                / 60,
            },
        )


class SegmentMappingFreshnessHealthCheck(HealthCheck):
    """Health check for segment mapping file freshness.

    This check monitors the modification time of the segment mapping file
    to ensure it's being updated regularly by the FCD Manager.
    """

    def __init__(
        self,
        name: str = "mapping_freshness",
        mapping_file_path: str = "data/segments_mapping.json",
        max_age_minutes: int = 15,
        timeout: float = 2.0,
        critical: bool = True,
        cache_ttl: float = 30.0,
    ):
        """Initialize segment mapping freshness health check.

        Args:
            name: Name of the health check
            mapping_file_path: Path to the segment mapping file
            max_age_minutes: Maximum age in minutes before considered stale
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.mapping_file = Path(mapping_file_path)
        self.max_age = timedelta(minutes=max_age_minutes)

    async def check(self) -> HealthCheckResult:
        """Check if the segment mapping file is fresh.

        Returns:
            HealthCheckResult indicating file freshness
        """
        try:
            if not self.mapping_file.exists():
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message=f"Segment mapping file not found: {self.mapping_file}",
                    metadata={
                        "file_path": str(self.mapping_file),
                        "exists": False,
                    },
                )

            # Get file modification time
            mtime = self.mapping_file.stat().st_mtime
            file_modified_time = datetime.fromtimestamp(mtime, UTC)
            file_age = datetime.now(UTC) - file_modified_time
            age_minutes = file_age.total_seconds() / 60

            if file_age <= self.max_age:
                status = "healthy"
                message = (
                    f"Segment mapping file is fresh ({age_minutes:.1f} minutes old)"
                )
            else:
                status = "degraded"
                message = (
                    f"Segment mapping file is stale ({age_minutes:.1f} minutes old)"
                )

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                metadata={
                    "file_path": str(self.mapping_file),
                    "last_modified": file_modified_time.isoformat(),
                    "age_minutes": age_minutes,
                    "max_age_minutes": self.max_age.total_seconds() / 60,
                    "file_size_bytes": self.mapping_file.stat().st_size,
                },
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Failed to check segment mapping file: {str(e)}",
                metadata={
                    "file_path": str(self.mapping_file),
                    "error": str(e),
                },
            )


class ProcessingPipelineHealthCheck(HealthCheck):
    """Health check for monitoring the overall processing pipeline status.

    This check aggregates multiple indicators to determine if the processing
    pipeline is functioning correctly.
    """

    def __init__(
        self,
        name: str = "processing_pipeline",
        timeout: float = 2.0,
        critical: bool = False,
        cache_ttl: float = 10.0,
    ):
        """Initialize processing pipeline health check.

        Args:
            name: Name of the health check
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.blobs_processed = 0
        self.last_error: str | None = None
        self.last_error_time: datetime | None = None
        self.processing_start_time: datetime | None = None
        self.processing_end_time: datetime | None = None

    def record_processing_start(self) -> None:
        """Record the start of a processing cycle."""
        self.processing_start_time = datetime.now(UTC)

    def record_processing_complete(self, blobs_count: int) -> None:
        """Record successful completion of a processing cycle.

        Args:
            blobs_count: Number of blobs processed in this cycle
        """
        self.processing_end_time = datetime.now(UTC)
        self.blobs_processed += blobs_count

    def record_error(self, error: str) -> None:
        """Record a processing error.

        Args:
            error: Error message
        """
        self.last_error = error
        self.last_error_time = datetime.now(UTC)

    async def check(self) -> HealthCheckResult:
        """Check the overall processing pipeline health.

        Returns:
            HealthCheckResult indicating pipeline status
        """
        metadata: dict[str, Any] = {
            "total_blobs_processed": self.blobs_processed,
        }

        # Check if there was a recent error
        if self.last_error_time:
            time_since_error = datetime.now(UTC) - self.last_error_time
            minutes_since_error = time_since_error.total_seconds() / 60
            metadata["last_error"] = self.last_error
            metadata["minutes_since_error"] = minutes_since_error

            # If error was very recent, mark as degraded
            if minutes_since_error < 5:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message=f"Recent processing error: {self.last_error}",
                    metadata=metadata,
                )

        # Check if processing has started
        if self.processing_start_time is None:
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Processing pipeline not yet started",
                metadata=metadata,
            )

        # Check if processing is currently running
        if self.processing_end_time is None or (
            self.processing_start_time > self.processing_end_time
        ):
            processing_duration = datetime.now(UTC) - self.processing_start_time
            duration_minutes = processing_duration.total_seconds() / 60
            metadata["processing_duration_minutes"] = duration_minutes

            # If processing is taking too long, mark as degraded
            if duration_minutes > 10:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message=f"Processing taking longer than expected ({duration_minutes:.1f} minutes)",
                    metadata=metadata,
                )

            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Processing pipeline is currently running",
                metadata=metadata,
            )

        # Pipeline has completed at least one cycle
        if self.processing_end_time:
            metadata["last_processing_complete"] = self.processing_end_time.isoformat()

        return HealthCheckResult(
            name=self.name,
            status="healthy",
            message=f"Processing pipeline is healthy ({self.blobs_processed} total blobs processed)",
            metadata=metadata,
        )
