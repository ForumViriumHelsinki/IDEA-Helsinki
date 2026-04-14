"""Service-specific health checks for Traffic Monitor service."""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from idea_shared.health.checks import (
    ExternalAPIHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
)
from idea_shared.health.models import HealthCheckResult

logger = logging.getLogger(__name__)


class WFSAPIHealthCheck(ExternalAPIHealthCheck):
    """Check Helsinki WFS API accessibility for traffic disturbances."""

    # Class-level session for connection pooling
    _session = None
    _session_lock = asyncio.Lock()

    def __init__(
        self,
        name: str = "wfs_api",
        wfs_url: str = "https://kartta.hel.fi/ws/geoserver/avoindata/wfs",
        test_feature_type: str = "avoindata:Alueet_ja_kadut_works_alue_aktiivinen",
        timeout: float = 10.0,
        critical: bool = True,
        cache_ttl: float = 30.0,
    ):
        """Initialize WFS API health check.

        Args:
            name: Name of the health check
            wfs_url: Base URL for the WFS service
            test_feature_type: Feature type to test availability
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds

        """
        # Use GetCapabilities for base health check
        super().__init__(
            name=name,
            url=f"{wfs_url}?service=WFS&request=GetCapabilities",
            method="GET",
            expected_status=200,
            timeout=timeout,
            critical=critical,
            cache_ttl=cache_ttl,
            circuit_breaker_threshold=5,
            circuit_breaker_timeout=180.0,
        )
        self.wfs_url = wfs_url
        self.test_feature_type = test_feature_type

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """Get or create the shared session with connection pooling.

        Returns:
            The shared ClientSession instance

        """
        async with cls._session_lock:
            if cls._session is None or cls._session.closed:
                # Configure connection pooling
                connector = aiohttp.TCPConnector(
                    limit=10,  # Total connection pool limit
                    limit_per_host=5,  # Per-host connection limit
                    ttl_dns_cache=300,  # DNS cache TTL
                )
                cls._session = aiohttp.ClientSession(connector=connector)
            return cls._session

    @classmethod
    async def close_session(cls):
        """Close the shared session if it exists."""
        async with cls._session_lock:
            if cls._session and not cls._session.closed:
                await cls._session.close()
                cls._session = None

    @classmethod
    def close_session_sync(cls):
        """Close the shared session from a synchronous context."""
        if cls._session and not cls._session.closed:
            try:
                asyncio.run(cls.close_session())
            except Exception as e:
                logger.error(f"Error closing WFS session: {e}")

    async def check(self) -> HealthCheckResult:
        """Check WFS API accessibility and feature type availability.

        Returns:
            HealthCheckResult indicating API status

        """
        # First do the base URL check
        base_result = await super().check()

        if base_result.status != "healthy":
            return base_result

        # Additionally verify specific feature type is available with a count query
        start_time = time.time()
        try:
            # Build a minimal GetFeature request that just counts features
            test_url = (
                f"{self.wfs_url}?"
                f"service=WFS&"
                f"version=1.1.0&"
                f"request=GetFeature&"
                f"typename={self.test_feature_type}&"
                f"resultType=hits"  # This only returns count, not actual features
            )

            session = await self.get_session()
            try:
                async with session.get(
                    test_url, timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_time = (time.time() - start_time) * 1000  # Convert to ms

                    if response.status == 200:
                        # Try to extract the number of features from the response
                        text = await response.text()
                        feature_count = None
                        if 'numberOfFeatures="' in text:
                            try:
                                feature_count = int(
                                    text.split('numberOfFeatures="')[1].split('"')[0]
                                )
                            except (IndexError, ValueError):
                                pass

                        return HealthCheckResult(
                            name=self.name,
                            status="healthy",
                            message=f"WFS API is accessible and feature type '{self.test_feature_type}' is available",
                            metadata={
                                "wfs_url": self.wfs_url,
                                "feature_type": self.test_feature_type,
                                "response_time_ms": response_time,
                                "feature_count": feature_count,
                            },
                        )
                    else:
                        return HealthCheckResult(
                            name=self.name,
                            status="degraded",
                            message=f"WFS API returned status {response.status} for feature type test",
                            metadata={
                                "wfs_url": self.wfs_url,
                                "feature_type": self.test_feature_type,
                                "status_code": response.status,
                                "response_time_ms": response_time,
                            },
                        )
            except Exception:
                # Re-raise the exception after ensuring session handling
                raise

        except TimeoutError:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"WFS feature type test timed out after {self.timeout} seconds",
                metadata={
                    "wfs_url": self.wfs_url,
                    "feature_type": self.test_feature_type,
                    "timeout_seconds": self.timeout,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"WFS feature type test failed: {str(e)}",
                metadata={
                    "wfs_url": self.wfs_url,
                    "feature_type": self.test_feature_type,
                    "error": str(e),
                },
            )


class FCDMappingHealthCheck(FileSystemHealthCheck):
    """Verify FCD segment mapping file availability and freshness."""

    def __init__(
        self,
        name: str = "fcd_mapping",
        file_path: str | None = None,
        max_age_minutes: int = 15,
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 5.0,
    ):
        """Initialize FCD mapping health check.

        Args:
            name: Name of the health check
            file_path: Path to the FCD mapping file
            max_age_minutes: Maximum age of file in minutes before considered stale
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds

        """
        # Import here to avoid circular dependencies
        from idea_shared.lib.Constants.Constants import FCD_MAP_DATA_FILE_LOCATION

        file_path = file_path or FCD_MAP_DATA_FILE_LOCATION
        super().__init__(
            name=name,
            path=file_path,
            check_write=False,
            timeout=timeout,
            critical=critical,
            cache_ttl=cache_ttl,
        )
        self.max_age_minutes = max_age_minutes

    async def check(self) -> HealthCheckResult:
        """Check FCD mapping file existence, validity, and freshness.

        Returns:
            HealthCheckResult indicating file status

        """
        # First do the base file existence check
        base_result = await super().check()

        if base_result.status != "healthy":
            return base_result

        try:
            loop = asyncio.get_running_loop()

            def check_file():
                """Synchronous file validation."""
                file_path = Path(self.path)

                # Check file size
                file_size = file_path.stat().st_size
                if file_size == 0:
                    return {
                        "status": "unhealthy",
                        "message": "FCD mapping file is empty",
                        "metadata": {"path": str(self.path), "size_bytes": 0},
                    }

                # Check modification time
                mod_time = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
                age_minutes = (datetime.now(UTC) - mod_time).total_seconds() / 60

                # Validate JSON structure
                try:
                    with open(file_path) as f:
                        data = json.load(f)

                    if not isinstance(data, dict):
                        return {
                            "status": "unhealthy",
                            "message": "FCD mapping file is not a valid JSON object",
                            "metadata": {
                                "path": str(self.path),
                                "age_minutes": age_minutes,
                            },
                        }

                    segment_count = len(data)
                    if segment_count == 0:
                        return {
                            "status": "unhealthy",
                            "message": "FCD mapping file contains no segments",
                            "metadata": {
                                "path": str(self.path),
                                "age_minutes": age_minutes,
                            },
                        }

                    # Check freshness
                    if age_minutes > self.max_age_minutes:
                        status = "degraded"
                        message = f"FCD mapping file is stale (age: {age_minutes:.1f} minutes)"
                    else:
                        status = "healthy"
                        message = f"FCD mapping file is valid and fresh (age: {age_minutes:.1f} minutes)"

                    return {
                        "status": status,
                        "message": message,
                        "metadata": {
                            "path": str(self.path),
                            "segment_count": segment_count,
                            "age_minutes": age_minutes,
                            "max_age_minutes": self.max_age_minutes,
                            "size_bytes": file_size,
                        },
                    }

                except json.JSONDecodeError as e:
                    return {
                        "status": "unhealthy",
                        "message": f"Invalid JSON in FCD mapping file: {e}",
                        "metadata": {"path": str(self.path), "error": str(e)},
                    }

            result_data = await loop.run_in_executor(None, check_file)

            return HealthCheckResult(
                name=self.name,
                status=result_data["status"],
                message=result_data["message"],
                metadata=result_data["metadata"],
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"FCD mapping check failed: {str(e)}",
                metadata={"path": str(self.path), "error": str(e)},
            )


class OutputFileHealthCheck(FileSystemHealthCheck):
    """Check traffic disturbance intersection output file writability."""

    def __init__(
        self,
        name: str = "output_file",
        file_path: str | None = None,
        timeout: float = 5.0,
        critical: bool = False,
        cache_ttl: float = 5.0,
    ):
        """Initialize output file health check.

        Args:
            name: Name of the health check
            file_path: Path to the output file
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds

        """
        # Import here to avoid circular dependencies
        from idea_shared.lib.Constants.Constants import (
            TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION,
        )

        file_path = file_path or TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION

        # Use parent directory for write check since file may not exist yet
        parent_dir = Path(file_path).parent
        super().__init__(
            name=name,
            path=str(parent_dir),
            check_write=True,
            timeout=timeout,
            critical=critical,
            cache_ttl=cache_ttl,
        )
        self.output_file_path = Path(file_path)

    async def check(self) -> HealthCheckResult:
        """Check output file writability and disk space.

        Returns:
            HealthCheckResult indicating output file status

        """
        # First do the base directory writability check
        base_result = await super().check()

        if base_result.status != "healthy":
            return base_result

        try:
            loop = asyncio.get_running_loop()

            def check_output():
                """Check output file specific conditions."""
                metadata: dict[str, Any] = {
                    "output_path": str(self.output_file_path),
                    "writable": True,
                }

                # If file exists, check its properties
                if self.output_file_path.exists():
                    mod_time = datetime.fromtimestamp(
                        self.output_file_path.stat().st_mtime, tz=UTC
                    )
                    age_minutes = (datetime.now(UTC) - mod_time).total_seconds() / 60
                    file_size = self.output_file_path.stat().st_size

                    metadata.update(
                        {
                            "file_exists": True,
                            "last_modified_minutes_ago": age_minutes,
                            "size_bytes": file_size,
                        }
                    )
                else:
                    metadata["file_exists"] = False

                # Check disk space (simplified - actual implementation may vary)
                import shutil

                total, used, free = shutil.disk_usage(self.output_file_path.parent)
                free_gb = free / (1024**3)

                metadata.update(
                    {
                        "disk_free_gb": free_gb,
                        "disk_used_percent": (used / total) * 100 if total > 0 else 0,
                    }
                )

                if free_gb < 0.1:  # Less than 100MB free
                    return {
                        "status": "unhealthy",
                        "message": "Insufficient disk space for output file",
                        "metadata": metadata,
                    }

                return {
                    "status": "healthy",
                    "message": "Output file location is writable with sufficient space",
                    "metadata": metadata,
                }

            result_data = await loop.run_in_executor(None, check_output)

            return HealthCheckResult(
                name=self.name,
                status=result_data["status"],
                message=result_data["message"],
                metadata=result_data["metadata"],
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Output file check failed: {str(e)}",
                metadata={"output_path": str(self.output_file_path), "error": str(e)},
            )


class UpdateFreshnessHealthCheck(HealthCheck):
    """Verify the service is actively processing updates."""

    def __init__(
        self,
        name: str = "update_freshness",
        service_state=None,  # ServiceState instance
        healthy_minutes: int = 90,
        degraded_minutes: int = 180,
        timeout: float = 2.0,
        critical: bool = True,
        cache_ttl: float = 5.0,
    ):
        """Initialize update freshness health check.

        Args:
            name: Name of the health check
            service_state: ServiceState instance for tracking timestamps
            healthy_minutes: Minutes before considering service degraded
            degraded_minutes: Minutes before considering service unhealthy
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds

        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.service_state = service_state
        self.healthy_minutes = healthy_minutes
        self.degraded_minutes = degraded_minutes

    async def check(self) -> HealthCheckResult:
        """Check if the service is actively processing updates.

        Returns:
            HealthCheckResult indicating update freshness status

        """
        if not self.service_state:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="Service state not available",
            )

        now = datetime.now(UTC)
        metadata = {
            "healthy_threshold_minutes": self.healthy_minutes,
            "degraded_threshold_minutes": self.degraded_minutes,
            "is_processing": self.service_state.is_processing,
        }

        # Check last successful WFS fetch
        wfs_age_minutes = None  # Initialize the variable
        if self.service_state.last_wfs_success:
            wfs_age_minutes = (
                now - self.service_state.last_wfs_success
            ).total_seconds() / 60
            metadata["last_wfs_success_minutes_ago"] = wfs_age_minutes
        else:
            # Service hasn't successfully fetched WFS data yet
            if self.service_state.last_wfs_fetch:
                # There was an attempt but it failed
                attempt_age = (
                    now - self.service_state.last_wfs_fetch
                ).total_seconds() / 60
                metadata["last_wfs_attempt_minutes_ago"] = attempt_age
                return HealthCheckResult(
                    name=self.name,
                    status="degraded"
                    if attempt_age < self.healthy_minutes
                    else "unhealthy",
                    message="No successful WFS fetches yet",
                    metadata=metadata,
                )
            else:
                # Service just started, no attempts yet
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",  # Give it time to start
                    message="Service starting, no update cycles completed yet",
                    metadata=metadata,
                )

        # Check last intersection calculation
        if self.service_state.last_intersection_calc:
            calc_age_minutes = (
                now - self.service_state.last_intersection_calc
            ).total_seconds() / 60
            metadata["last_intersection_calc_minutes_ago"] = calc_age_minutes

        # Add current counts to metadata
        metadata.update(
            {
                "current_disturbance_count": self.service_state.current_disturbance_count,
                "current_intersection_count": self.service_state.current_intersection_count,
            }
        )

        # Determine status based on age (wfs_age_minutes is guaranteed to be set here)
        if wfs_age_minutes < self.healthy_minutes:
            status = "healthy"
            message = (
                f"Updates are fresh (last success {wfs_age_minutes:.1f} minutes ago)"
            )
        elif wfs_age_minutes < self.degraded_minutes:
            status = "degraded"
            message = f"Updates are getting stale (last success {wfs_age_minutes:.1f} minutes ago)"
        else:
            status = "unhealthy"
            message = (
                f"Updates are too old (last success {wfs_age_minutes:.1f} minutes ago)"
            )

        # If currently processing, add that to the message
        if self.service_state.is_processing:
            message += " - currently processing"

        return HealthCheckResult(
            name=self.name, status=status, message=message, metadata=metadata
        )


class DetectorHealthCheck(HealthCheck):
    """Monitor IntersectionDetector operational status."""

    def __init__(
        self,
        name: str = "detector_status",
        detector=None,  # IntersectionDetector instance
        timeout: float = 5.0,
        critical: bool = True,
        cache_ttl: float = 10.0,
    ):
        """Initialize detector health check.

        Args:
            name: Name of the health check
            detector: IntersectionDetector instance
            timeout: Timeout in seconds for the check
            critical: Whether this check is critical for readiness
            cache_ttl: Cache time-to-live in seconds

        """
        super().__init__(name, timeout, critical, cache_ttl)
        self.detector = detector

    async def check(self) -> HealthCheckResult:
        """Check IntersectionDetector operational status.

        Returns:
            HealthCheckResult indicating detector status

        """
        if not self.detector:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="IntersectionDetector not initialized",
            )

        try:
            loop = asyncio.get_running_loop()

            def check_detector():
                """Check detector capabilities."""
                metadata = {}

                # Check if detector can access required methods
                required_methods = [
                    "load_wfs_geojson",
                    "load_fcd_segment_data",
                    "find_intersecting_features",
                    "process_intersections_to_new_model",
                    "write_json_records",
                ]

                missing_methods = []
                for method in required_methods:
                    if not hasattr(self.detector, method):
                        missing_methods.append(method)

                if missing_methods:
                    return {
                        "status": "unhealthy",
                        "message": f"Detector missing required methods: {', '.join(missing_methods)}",
                        "metadata": metadata,
                    }

                # Simple test to verify detector can perform basic operations
                # This is a minimal check - just verify the object is properly initialized
                metadata["detector_type"] = type(self.detector).__name__
                metadata["has_required_methods"] = True

                return {
                    "status": "healthy",
                    "message": "IntersectionDetector is operational",
                    "metadata": metadata,
                }

            result_data = await loop.run_in_executor(None, check_detector)

            return HealthCheckResult(
                name=self.name,
                status=result_data["status"],
                message=result_data["message"],
                metadata=result_data["metadata"],
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Detector check failed: {str(e)}",
                metadata={"error": str(e)},
            )
