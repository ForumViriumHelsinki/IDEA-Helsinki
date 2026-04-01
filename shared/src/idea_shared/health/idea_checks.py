"""IDEA-Helsinki specific health check implementations."""

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from influxdb_client.client.influxdb_client import InfluxDBClient

from idea_shared.threading.file_locks import read_json_with_retry

from .checks import (
    DatabaseHealthCheck,
    ExternalAPIHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
)
from .models import HealthCheckResult
from .utils import check_backfill_mode


class AzureBlobStorageHealthCheck(HealthCheck):
    """Health check for Azure Blob Storage connectivity."""

    def __init__(
        self,
        name: str,
        account_name: str,
        container_name: str,
        sas_token: str,
        timeout: float = 10.0,
        critical: bool = True,
        cache_ttl: float = 30.0,
    ):
        """Initialize Azure Blob Storage health check.

        Args:
            name: Name of the health check
            account_name: Azure storage account name
            container_name: Container name to check
            sas_token: SAS token for authentication
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.account_name = account_name
        self.container_name = container_name
        self.sas_token = sas_token
        self.account_url = f"https://{account_name}.blob.core.windows.net"

    async def check(self) -> HealthCheckResult:
        """Check Azure Blob Storage connectivity.

        Returns:
            HealthCheckResult indicating storage status
        """
        try:
            # Run sync operations in executor to avoid blocking
            loop = asyncio.get_running_loop()

            def check_blob_storage():
                """Synchronous blob storage check."""
                blob_service_client = BlobServiceClient(
                    account_url=self.account_url, credential=self.sas_token
                )
                container_client = blob_service_client.get_container_client(
                    self.container_name
                )

                # Verify connectivity by fetching a single blob listing
                for _blob in container_client.list_blobs(results_per_page=1):
                    break
                return True

            result = await loop.run_in_executor(None, check_blob_storage)

            if result:
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message=f"Connected to Azure container '{self.container_name}'",
                    metadata={
                        "account": self.account_name,
                        "container": self.container_name,
                    },
                )
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="Azure Blob Storage connectivity check returned no result",
                metadata={
                    "account": self.account_name,
                    "container": self.container_name,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Azure Blob Storage check failed: {str(e)}",
                metadata={
                    "account": self.account_name,
                    "container": self.container_name,
                    "error": str(e),
                },
            )


class WFSServiceHealthCheck(ExternalAPIHealthCheck):
    """Health check for Helsinki WFS service availability."""

    def __init__(
        self,
        name: str = "wfs_service",
        url: str = "https://kartta.hel.fi/ws/geoserver/avoindata/wfs",
        timeout: float = 10.0,
        critical: bool = True,
        cache_ttl: float = 60.0,
    ):
        """Initialize WFS service health check.

        Args:
            name: Name of the health check
            url: WFS service URL
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        # Build a GetCapabilities request URL
        capabilities_url = f"{url}?service=WFS&request=GetCapabilities"

        super().__init__(
            name=name,
            url=capabilities_url,
            method="GET",
            expected_status=200,
            timeout=timeout,
            critical=critical,
            cache_ttl=cache_ttl,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=120.0,
        )
        self.base_url = url

    async def check(self) -> HealthCheckResult:
        """Check WFS service availability.

        Returns:
            HealthCheckResult indicating WFS service status
        """
        result = await super().check()

        # Add WFS-specific metadata
        if result.status == "healthy":
            result.message = f"WFS service is available at {self.base_url}"
            if result.metadata is not None:
                result.metadata["service"] = "WFS"
                result.metadata["base_url"] = self.base_url

        return result


class InfluxDBHealthCheck(DatabaseHealthCheck):
    """Health check for InfluxDB connectivity."""

    def __init__(
        self,
        name: str,
        url: str,
        token: str,
        org: str,
        bucket: str,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 10.0,
    ):
        """Initialize InfluxDB health check.

        Args:
            name: Name of the health check
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: Organization name
            bucket: Bucket name to check
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        # Pass a dummy connection string to base class
        super().__init__(name, f"{url}/{org}/{bucket}", timeout, critical, cache_ttl)
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket

    async def check(self) -> HealthCheckResult:
        """Check InfluxDB connectivity.

        Returns:
            HealthCheckResult indicating database status
        """
        try:
            # Run sync operations in executor
            loop = asyncio.get_running_loop()

            def check_influx():
                """Synchronous InfluxDB check."""
                client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
                try:
                    # Ping the server
                    result = client.ping()
                    return result
                finally:
                    client.close()

            ping_result = await loop.run_in_executor(None, check_influx)

            if ping_result:
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message=f"InfluxDB is accessible at {self.url}",
                    metadata={
                        "url": self.url,
                        "org": self.org,
                        "bucket": self.bucket,
                    },
                )
            else:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="InfluxDB ping failed",
                    metadata={
                        "url": self.url,
                        "org": self.org,
                        "bucket": self.bucket,
                    },
                )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"InfluxDB check failed: {str(e)}",
                metadata={
                    "url": self.url,
                    "org": self.org,
                    "bucket": self.bucket,
                    "error": str(e),
                },
            )


class FCDDataFreshnessHealthCheck(DatabaseHealthCheck):
    """Health check for FCD data freshness in InfluxDB."""

    def __init__(
        self,
        name: str,
        url: str,
        token: str,
        org: str,
        bucket: str,
        max_age_minutes: int = 30,
        backfill_lookback_days: int = 7,
        measurement: str = "fcd_data",
        timeout: float = 10.0,
        critical: bool = False,
        cache_ttl: float = 60.0,
    ):
        """Initialize FCD data freshness health check.

        Args:
            name: Name of the health check
            url: InfluxDB URL
            token: InfluxDB authentication token
            org: Organization name
            bucket: Bucket name to check
            max_age_minutes: Maximum age of data in minutes before considered stale
            backfill_lookback_days: Number of days to look back for backfill mode detection (default: 7)
            measurement: Measurement name to check
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
        """
        super().__init__(name, f"{url}/{org}/{bucket}", timeout, critical, cache_ttl)
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.max_age_minutes = max_age_minutes
        self.backfill_lookback_days = backfill_lookback_days
        self.measurement = measurement

    async def check(self) -> HealthCheckResult:
        """Check FCD data freshness.

        Returns:
            HealthCheckResult indicating data freshness status
        """
        try:
            loop = asyncio.get_running_loop()

            def check_freshness():
                """Check data freshness synchronously."""
                client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
                try:
                    query_api = client.query_api()
                    return check_backfill_mode(
                        query_api=query_api,
                        org=self.org,
                        bucket=self.bucket,
                        measurement=self.measurement,
                        freshness_threshold_minutes=self.max_age_minutes,
                        backfill_lookback_days=self.backfill_lookback_days,
                    )
                finally:
                    client.close()

            (
                has_recent_data,
                age_minutes,
                backfill_timestamp,
            ) = await loop.run_in_executor(None, check_freshness)

            if has_recent_data:
                if backfill_timestamp and age_minutes is not None:
                    # Backfill mode - data exists but is historical
                    backfill_msg = f"FCD data is healthy (backfilling from {backfill_timestamp.strftime('%Y-%m-%d %H:%M')})"
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message=backfill_msg,
                        metadata={
                            "bucket": self.bucket,
                            "measurement": self.measurement,
                            "mode": "backfill",
                            "latest_data_timestamp": backfill_timestamp.isoformat(),
                            "data_age_minutes": round(age_minutes, 2),
                            "backfill_progress": f"Processing data from {backfill_timestamp.strftime('%Y-%m-%d')}",
                        },
                    )
                else:
                    # Real-time mode - recent data exists
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message=f"FCD data is fresh (age: {age_minutes:.1f} minutes)",
                        metadata={
                            "bucket": self.bucket,
                            "measurement": self.measurement,
                            "mode": "real_time",
                            "data_age_minutes": age_minutes,
                            "max_age_minutes": self.max_age_minutes,
                        },
                    )
            else:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message=f"No recent FCD data found (max age: {self.max_age_minutes} minutes)",
                    metadata={
                        "bucket": self.bucket,
                        "measurement": self.measurement,
                        "max_age_minutes": self.max_age_minutes,
                    },
                )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"FCD freshness check failed: {str(e)}",
                metadata={
                    "bucket": self.bucket,
                    "measurement": self.measurement,
                    "error": str(e),
                },
            )


class SegmentMappingIntegrityHealthCheck(FileSystemHealthCheck):
    """Health check for segment mapping file integrity."""

    def __init__(
        self,
        name: str,
        mapping_file_path: str = "data/segments_mapping.json",
        history_file_path: str = "data/master_segment_history.json",
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 300.0,
        startup_grace_minutes: int = 15,
    ):
        """Initialize segment mapping integrity health check.

        Args:
            name: Name of the health check
            mapping_file_path: Path to segments mapping file
            history_file_path: Path to segment history file
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
            startup_grace_minutes: Grace period in minutes during initial backfill
        """
        super().__init__(
            name=name,
            path=mapping_file_path,
            check_write=False,
            timeout=timeout,
            critical=critical,
            cache_ttl=cache_ttl,
        )
        self.mapping_file_path = Path(mapping_file_path)
        self.history_file_path = Path(history_file_path)
        self._startup_time = datetime.now(UTC)
        self._startup_grace_period = timedelta(minutes=startup_grace_minutes)

    async def check(self) -> HealthCheckResult:
        """Check segment mapping file integrity.

        Returns healthy during startup grace period to allow initial backfill
        to create the mapping file before enforcing validation.

        Returns:
            HealthCheckResult indicating mapping file status
        """
        elapsed = datetime.now(UTC) - self._startup_time
        if elapsed < self._startup_grace_period:
            remaining = (self._startup_grace_period - elapsed).total_seconds()
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Startup grace period - initial backfill in progress",
                metadata={
                    "grace_period_remaining_seconds": round(remaining),
                },
            )

        try:
            loop = asyncio.get_running_loop()

            def validate_files():
                """Validate segment mapping files synchronously."""
                issues = []
                metadata = {}

                # Check mapping file
                if not self.mapping_file_path.exists():
                    issues.append(f"Mapping file not found: {self.mapping_file_path}")
                else:
                    mapping_data = read_json_with_retry(self.mapping_file_path)

                    if mapping_data is None:
                        issues.append("Mapping file is empty or unreadable")
                    elif not isinstance(mapping_data, dict):
                        issues.append("Mapping file is not a valid JSON object")
                    else:
                        segment_count = len(mapping_data)
                        metadata["segment_count"] = segment_count

                        if segment_count == 0:
                            issues.append("No segments found in mapping file")

                        # Validate structure of a few segments
                        for segment_id, segment_data in list(mapping_data.items())[:5]:
                            if not isinstance(segment_data, dict):
                                issues.append(f"Invalid segment data for {segment_id}")
                                break

                            # Check for required fields
                            required_fields = ["geometry", "properties"]
                            for field in required_fields:
                                if field not in segment_data:
                                    issues.append(
                                        f"Segment {segment_id} missing '{field}' field"
                                    )
                                    break

                # Check history file
                history_data = read_json_with_retry(self.history_file_path)
                if isinstance(history_data, dict):
                    metadata["history_entries"] = len(history_data)
                elif history_data is None:
                    metadata["history_entries"] = 0
                else:
                    issues.append("Error reading history file: unexpected type")
                    metadata["history_entries"] = 0

                return issues, metadata

            issues, metadata = await loop.run_in_executor(None, validate_files)

            if not issues:
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message="Segment mapping files are valid",
                    metadata=metadata,
                )
            else:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded" if len(issues) < 3 else "unhealthy",
                    message=f"Segment mapping issues: {'; '.join(issues[:2])}",
                    metadata={**metadata, "issues": issues},
                )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Segment mapping check failed: {str(e)}",
                metadata={"error": str(e)},
            )


class SqliteHealthCheck(HealthCheck):
    """Health check for SQLite database integrity.

    Verifies that the database file exists, expected tables are present,
    and optional minimum row counts are met.
    """

    def __init__(
        self,
        name: str,
        db_path: str | Path,
        expected_tables: list[str],
        *,
        min_row_counts: dict[str, int] | None = None,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 30.0,
        startup_grace_minutes: float = 0,
    ):
        """Initialize SQLite health check.

        Args:
            name: Name of the health check.
            db_path: Path to the SQLite database file.
            expected_tables: Table names that must exist.
            min_row_counts: Optional mapping of table name to minimum row count.
            timeout: Timeout in seconds for the check.
            critical: Whether this check is critical for readiness.
            cache_ttl: Cache time-to-live in seconds.
            startup_grace_minutes: Grace period in minutes during initial data population.
        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.db_path = Path(db_path)
        self.expected_tables = expected_tables
        self.min_row_counts = min_row_counts or {}
        self._startup_time = datetime.now(UTC)
        self._startup_grace_period = timedelta(minutes=startup_grace_minutes)

    async def check(self) -> HealthCheckResult:
        """Check SQLite database integrity.

        Returns:
            HealthCheckResult indicating database status.
        """
        # Grace period for initial data population
        elapsed = datetime.now(UTC) - self._startup_time
        if elapsed < self._startup_grace_period:
            remaining = (self._startup_grace_period - elapsed).total_seconds()
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Startup grace period - initial data population in progress",
                metadata={
                    "grace_period_remaining_seconds": round(remaining),
                },
            )

        # Verify database file exists
        if not self.db_path.exists():
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"SQLite database file not found: {self.db_path}",
            )

        try:
            loop = asyncio.get_running_loop()

            def check_db():
                """Synchronous SQLite integrity check."""
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                try:
                    cursor = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    existing_tables = {row[0] for row in cursor.fetchall()}

                    missing = [
                        t for t in self.expected_tables if t not in existing_tables
                    ]
                    if missing:
                        return HealthCheckResult(
                            name=self.name,
                            status="unhealthy",
                            message=f"Missing expected tables: {', '.join(missing)}",
                            metadata={
                                "missing_tables": missing,
                                "existing_tables": sorted(existing_tables),
                            },
                        )

                    # Check minimum row counts
                    row_counts: dict[str, int] = {}
                    below_threshold: list[str] = []
                    for table, min_count in self.min_row_counts.items():
                        cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")  # noqa: S608
                        count = cursor.fetchone()[0]
                        row_counts[table] = count
                        if count < min_count:
                            below_threshold.append(f"{table}: {count}/{min_count}")

                    if below_threshold:
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=f"Row counts below threshold: {', '.join(below_threshold)}",
                            metadata={
                                "table_count": len(existing_tables),
                                "row_counts": row_counts,
                            },
                        )

                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="SQLite database is healthy",
                        metadata={
                            "table_count": len(existing_tables),
                            "row_counts": row_counts,
                        },
                    )
                finally:
                    conn.close()

            return await loop.run_in_executor(None, check_db)

        except sqlite3.Error as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"SQLite check failed: {e}",
                metadata={"error": str(e)},
            )
