"""IDEA-Helsinki specific health check implementations."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from influxdb_client import InfluxDBClient

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
            loop = asyncio.get_event_loop()

            def check_blob_storage():
                """Synchronous blob storage check."""
                blob_service_client = BlobServiceClient(
                    account_url=self.account_url, credential=self.sas_token
                )
                container_client = blob_service_client.get_container_client(
                    self.container_name
                )

                # Try to list blobs (limited to 1 for efficiency)
                blobs = list(container_client.list_blobs(max_results=1))
                return len(blobs) >= 0  # Will be >= 0 even if empty

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
            loop = asyncio.get_event_loop()

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
            loop = asyncio.get_event_loop()

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
                if backfill_timestamp:
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
    ):
        """Initialize segment mapping integrity health check.

        Args:
            name: Name of the health check
            mapping_file_path: Path to segments mapping file
            history_file_path: Path to segment history file
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds
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

    async def check(self) -> HealthCheckResult:
        """Check segment mapping file integrity.

        Returns:
            HealthCheckResult indicating mapping file status
        """
        try:
            loop = asyncio.get_event_loop()

            def validate_files():
                """Validate segment mapping files synchronously."""
                issues = []
                metadata = {}

                # Check mapping file
                if not self.mapping_file_path.exists():
                    issues.append(f"Mapping file not found: {self.mapping_file_path}")
                else:
                    try:
                        with open(self.mapping_file_path) as f:
                            mapping_data = json.load(f)

                        if not isinstance(mapping_data, dict):
                            issues.append("Mapping file is not a valid JSON object")
                        else:
                            segment_count = len(mapping_data)
                            metadata["segment_count"] = segment_count

                            if segment_count == 0:
                                issues.append("No segments found in mapping file")

                            # Validate structure of a few segments
                            for segment_id, segment_data in list(mapping_data.items())[
                                :5
                            ]:
                                if not isinstance(segment_data, dict):
                                    issues.append(
                                        f"Invalid segment data for {segment_id}"
                                    )
                                    break

                                # Check for required fields
                                required_fields = ["geometry", "properties"]
                                for field in required_fields:
                                    if field not in segment_data:
                                        issues.append(
                                            f"Segment {segment_id} missing '{field}' field"
                                        )
                                        break
                    except json.JSONDecodeError as e:
                        issues.append(f"Invalid JSON in mapping file: {e}")
                    except Exception as e:
                        issues.append(f"Error reading mapping file: {e}")

                # Check history file if it exists
                if self.history_file_path.exists():
                    try:
                        with open(self.history_file_path) as f:
                            history_data = json.load(f)

                        if isinstance(history_data, dict):
                            metadata["history_entries"] = len(history_data)
                    except Exception as e:
                        issues.append(f"Error reading history file: {e}")
                else:
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
