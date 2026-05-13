"""Tests for Traffic Monitor health checks."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from idea_shared.health.checks import ExternalAPIHealthCheck
from idea_shared.health.models import HealthCheckResult

from src.health_checks import (
    DetectorHealthCheck,  # ty: ignore[unresolved-import]
    FCDMappingHealthCheck,  # ty: ignore[unresolved-import]
    OutputFileHealthCheck,  # ty: ignore[unresolved-import]
    UpdateFreshnessHealthCheck,  # ty: ignore[unresolved-import]
    WFSAPIHealthCheck,  # ty: ignore[unresolved-import]
)
from src.service_state import ServiceState


class TestWFSAPIHealthCheck:
    """Test WFS API health check."""

    @staticmethod
    def _build_mock_session(response_mock):
        """Build an aiohttp.ClientSession mock that returns response_mock.

        Returns a callable suitable for use as the ``aiohttp.ClientSession``
        constructor replacement; the returned object behaves as an
        ``async with`` context manager that yields a session whose ``get()``
        returns the supplied response (itself an ``async with`` mock).
        """
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=response_mock)
        mock_session.closed = False
        mock_session.close = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        return mock_session

    @pytest.mark.asyncio
    async def test_wfs_healthy(self):
        """Test WFS API health check when service is healthy."""
        check = WFSAPIHealthCheck(cache_ttl=0)  # Disable cache for testing

        # Mock the response as async context manager
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='<wfs:FeatureCollection numberOfFeatures="42">'
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = self._build_mock_session(mock_response)

        # Mock the base class check to avoid real HTTP calls to kartta.hel.fi
        with (
            patch.object(
                ExternalAPIHealthCheck,
                "check",
                new_callable=AsyncMock,
                return_value=HealthCheckResult(
                    name="wfs_api", status="healthy", message="OK"
                ),
            ),
            patch("src.health_checks.aiohttp.ClientSession", return_value=mock_session),
        ):
            result = await check.check()

            assert result.message is not None
            assert result.metadata is not None
            assert result.status == "healthy"
            assert "feature type" in result.message
            assert result.metadata["feature_count"] == 42

    @pytest.mark.asyncio
    async def test_wfs_unhealthy(self):
        """Test WFS API health check when service is unavailable."""
        check = WFSAPIHealthCheck(cache_ttl=0)

        # session.get() raises, simulating a transport failure on the
        # feature-type probe (after super().check() has already passed).
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=Exception("Connection failed"))
        mock_session.closed = False
        mock_session.close = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock the base class check to avoid real HTTP calls to kartta.hel.fi
        with (
            patch.object(
                ExternalAPIHealthCheck,
                "check",
                new_callable=AsyncMock,
                return_value=HealthCheckResult(
                    name="wfs_api", status="healthy", message="OK"
                ),
            ),
            patch("src.health_checks.aiohttp.ClientSession", return_value=mock_session),
        ):
            result = await check.check()

            assert result.message is not None
            assert result.status == "unhealthy"
            assert "Connection failed" in result.message

    @pytest.mark.asyncio
    async def test_wfs_session_closed_on_success(self):
        """Regression for issue #460: per-call session is closed on the
        success path so aiohttp does not emit ``Unclosed client session``."""
        check = WFSAPIHealthCheck(cache_ttl=0)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='<wfs:FeatureCollection numberOfFeatures="1">'
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = self._build_mock_session(mock_response)

        with (
            patch.object(
                ExternalAPIHealthCheck,
                "check",
                new_callable=AsyncMock,
                return_value=HealthCheckResult(
                    name="wfs_api", status="healthy", message="OK"
                ),
            ),
            patch("src.health_checks.aiohttp.ClientSession", return_value=mock_session),
        ):
            await check.check()

        # ``async with aiohttp.ClientSession()`` must invoke __aexit__,
        # which is what closes the session and its TCPConnector.
        assert mock_session.__aexit__.await_count == 1

    @pytest.mark.asyncio
    async def test_wfs_session_closed_on_failure(self):
        """Regression for issue #460: per-call session is closed even when
        the feature-type probe raises an exception."""
        check = WFSAPIHealthCheck(cache_ttl=0)

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=Exception("Connection failed"))
        mock_session.closed = False
        mock_session.close = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(
                ExternalAPIHealthCheck,
                "check",
                new_callable=AsyncMock,
                return_value=HealthCheckResult(
                    name="wfs_api", status="healthy", message="OK"
                ),
            ),
            patch("src.health_checks.aiohttp.ClientSession", return_value=mock_session),
        ):
            await check.check()

        assert mock_session.__aexit__.await_count == 1

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Circuit breaker feature not yet implemented")
    async def test_wfs_circuit_breaker(self):
        """Test WFS API circuit breaker behavior."""
        check = WFSAPIHealthCheck(
            cache_ttl=0,
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=1.0,
        )

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=Exception("Connection failed"))
        mock_session.request = MagicMock(side_effect=Exception("Connection failed"))
        mock_session.closed = False
        mock_session.close = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.health_checks.aiohttp.ClientSession", return_value=mock_session
        ):
            # First failure
            result = await check.check()
            assert result.status == "unhealthy"

            # Second failure - should open circuit
            result = await check.check()
            assert result.status == "unhealthy"

            # Third call - circuit should be open
            result = await check.check()
            assert result.message is not None
            assert result.status == "degraded"
            assert "Circuit breaker is open" in result.message

            # Wait for circuit to transition to half-open
            await asyncio.sleep(1.1)

            # Mock a successful response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(
                return_value='<wfs:FeatureCollection numberOfFeatures="10">'
            )
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            mock_session.get.side_effect = None
            mock_session.get.return_value = mock_response
            mock_session.request.side_effect = None
            mock_session.request.return_value = mock_response

            # Should transition to closed on success
            result = await check.check()
            assert result.status == "healthy"


class TestFCDMappingHealthCheck:
    """Test FCD mapping health check."""

    @pytest.mark.asyncio
    async def test_fcd_mapping_healthy(self):
        """Test FCD mapping when file is valid and fresh."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            test_data = {"segment1": {"geometry": {}, "properties": {}}}
            json.dump(test_data, f)
            f.flush()

            try:
                check = FCDMappingHealthCheck(
                    file_path=f.name, max_age_minutes=60, cache_ttl=0
                )

                result = await check.check()

                assert result.message is not None
                assert result.metadata is not None
                assert result.status == "healthy"
                assert "valid and fresh" in result.message
                assert result.metadata["segment_count"] == 1
            finally:
                Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_fcd_mapping_stale(self):
        """Test FCD mapping when file is stale."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            test_data = {"segment1": {"geometry": {}, "properties": {}}}
            json.dump(test_data, f)
            f.flush()

            try:
                # Actually set file modification time to 30 minutes ago using os.utime
                old_time = datetime.now(UTC) - timedelta(minutes=30)
                os.utime(f.name, (old_time.timestamp(), old_time.timestamp()))

                check = FCDMappingHealthCheck(
                    file_path=f.name, max_age_minutes=15, cache_ttl=0
                )

                result = await check.check()

                assert result.message is not None
                assert result.status == "degraded"
                assert "stale" in result.message
            finally:
                Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_fcd_mapping_missing(self):
        """Test FCD mapping when file doesn't exist."""
        check = FCDMappingHealthCheck(file_path="/nonexistent/file.json", cache_ttl=0)

        result = await check.check()

        assert result.message is not None
        assert result.status == "unhealthy"
        assert "does not exist" in result.message

    @pytest.mark.asyncio
    async def test_fcd_mapping_invalid_json(self):
        """Test FCD mapping when file contains invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            f.flush()

            try:
                check = FCDMappingHealthCheck(file_path=f.name, cache_ttl=0)
                result = await check.check()

                assert result.message is not None
                assert result.status == "unhealthy"
                assert "Invalid JSON" in result.message
            finally:
                Path(f.name).unlink(missing_ok=True)


class TestOutputFileHealthCheck:
    """Test output file health check."""

    @pytest.mark.asyncio
    async def test_output_file_writable(self):
        """Test output file check when directory is writable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.json"
            check = OutputFileHealthCheck(file_path=str(output_path), cache_ttl=0)

            result = await check.check()

            assert result.message is not None
            assert result.metadata is not None
            assert result.status == "healthy"
            assert "writable" in result.message
            assert result.metadata["file_exists"] is False

    @pytest.mark.asyncio
    async def test_output_file_exists(self):
        """Test output file check when file already exists."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "data"}, f)
            f.flush()

            try:
                check = OutputFileHealthCheck(file_path=f.name, cache_ttl=0)
                result = await check.check()

                assert result.metadata is not None
                assert result.status == "healthy"
                assert result.metadata["file_exists"] is True
                assert "size_bytes" in result.metadata
            finally:
                Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_output_file_no_permission(self):
        """Test output file check when directory is not writable."""
        check = OutputFileHealthCheck(
            file_path="/root/cannot_write_here.json", cache_ttl=0
        )

        result = await check.check()

        # Should fail on either path not existing or permission denied
        assert result.status == "unhealthy"


class TestUpdateFreshnessHealthCheck:
    """Test update freshness health check."""

    @pytest.mark.asyncio
    async def test_freshness_healthy(self):
        """Test freshness when updates are recent."""
        state = ServiceState()
        state.update_wfs_fetch(success=True, disturbance_count=10)

        check = UpdateFreshnessHealthCheck(
            service_state=state, healthy_minutes=90, degraded_minutes=180, cache_ttl=0
        )

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "healthy"
        assert "fresh" in result.message
        assert result.metadata["current_disturbance_count"] == 10

    @pytest.mark.asyncio
    async def test_freshness_degraded(self):
        """Test freshness when updates are getting stale."""
        state = ServiceState()
        # Set last success to 100 minutes ago
        state.last_wfs_success = datetime.now(UTC) - timedelta(minutes=100)

        check = UpdateFreshnessHealthCheck(
            service_state=state, healthy_minutes=90, degraded_minutes=180, cache_ttl=0
        )

        result = await check.check()

        assert result.message is not None
        assert result.status == "degraded"
        assert "stale" in result.message

    @pytest.mark.asyncio
    async def test_freshness_unhealthy(self):
        """Test freshness when updates are too old."""
        state = ServiceState()
        # Set last success to 200 minutes ago
        state.last_wfs_success = datetime.now(UTC) - timedelta(minutes=200)

        check = UpdateFreshnessHealthCheck(
            service_state=state, healthy_minutes=90, degraded_minutes=180, cache_ttl=0
        )

        result = await check.check()

        assert result.message is not None
        assert result.status == "unhealthy"
        assert "too old" in result.message

    @pytest.mark.asyncio
    async def test_freshness_no_state(self):
        """Test freshness when service state is not available."""
        check = UpdateFreshnessHealthCheck(service_state=None, cache_ttl=0)

        result = await check.check()

        assert result.message is not None
        assert result.status == "unhealthy"
        assert "Service state not available" in result.message

    @pytest.mark.asyncio
    async def test_freshness_startup(self):
        """Test freshness when service just started."""
        state = ServiceState()
        # No fetches yet

        check = UpdateFreshnessHealthCheck(service_state=state, cache_ttl=0)

        result = await check.check()

        assert result.message is not None
        assert result.status == "healthy"
        assert "starting" in result.message.lower()


class TestDetectorHealthCheck:
    """Test detector health check."""

    @pytest.mark.asyncio
    async def test_detector_healthy(self):
        """Test detector when properly initialized."""
        mock_detector = Mock()
        mock_detector.load_wfs_geojson = Mock()
        mock_detector.load_fcd_segment_data = Mock()
        mock_detector.find_intersecting_features = Mock()
        mock_detector.process_intersections_to_new_model = Mock()
        mock_detector.write_json_records = Mock()

        check = DetectorHealthCheck(detector=mock_detector, cache_ttl=0)

        result = await check.check()

        assert result.message is not None
        assert result.status == "healthy"
        assert "operational" in result.message

    @pytest.mark.asyncio
    async def test_detector_missing_methods(self):
        """Test detector when required methods are missing."""
        # Create a mock with limited methods using spec
        # Only these two methods exist, missing the other three required methods
        mock_detector = Mock(spec=["load_wfs_geojson", "load_fcd_segment_data"])

        check = DetectorHealthCheck(detector=mock_detector, cache_ttl=0)

        result = await check.check()

        assert result.message is not None
        assert result.status == "unhealthy"
        assert "missing required methods" in result.message

    @pytest.mark.asyncio
    async def test_detector_not_initialized(self):
        """Test detector when not initialized."""
        check = DetectorHealthCheck(detector=None, cache_ttl=0)

        result = await check.check()

        assert result.message is not None
        assert result.status == "unhealthy"
        assert "not initialized" in result.message


class TestServiceState:
    """Test service state tracking."""

    def test_wfs_fetch_tracking(self):
        """Test WFS fetch state tracking."""
        state = ServiceState()

        # Test successful fetch
        state.update_wfs_fetch(success=True, disturbance_count=5)
        assert state.last_wfs_fetch is not None
        assert state.last_wfs_success is not None
        assert state.current_disturbance_count == 5
        assert state.last_error is None

        # Test failed fetch
        state.update_wfs_fetch(success=False, error="Connection error")
        assert state.last_wfs_fetch > state.last_wfs_success
        assert state.last_error == "Connection error"

    def test_intersection_tracking(self):
        """Test intersection calculation tracking."""
        state = ServiceState()

        state.update_intersection(intersection_count=20)
        assert state.last_intersection_calc is not None
        assert state.current_intersection_count == 20

    def test_file_write_tracking(self):
        """Test file write tracking."""
        state = ServiceState()

        # Test successful write
        state.update_file_write(success=True)
        assert state.last_file_write is not None

        # Test failed write
        state.update_file_write(success=False, error="Permission denied")
        assert state.last_error == "Permission denied"

    def test_processing_flag(self):
        """Test processing flag management."""
        state = ServiceState()

        assert not state.is_processing
        state.set_processing(True)
        assert state.is_processing
        state.set_processing(False)
        assert not state.is_processing

    def test_status_summary(self):
        """Test status summary generation."""
        state = ServiceState()
        state.update_wfs_fetch(success=True, disturbance_count=10)
        state.update_intersection(15)
        state.update_file_write(success=True)

        summary = state.get_status_summary()

        assert "startup_time" in summary
        assert "uptime_minutes" in summary
        assert summary["current_disturbance_count"] == 10
        assert summary["current_intersection_count"] == 15
        assert "last_wfs_success" in summary
        assert "last_intersection_calc" in summary
        assert "last_file_write" in summary

    def test_error_reset(self):
        """Test error reset functionality."""
        state = ServiceState()
        state.update_wfs_fetch(success=False, error="Test error")
        assert state.last_error == "Test error"

        state.reset_error()
        assert state.last_error is None
