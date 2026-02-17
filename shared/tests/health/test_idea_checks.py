"""Tests for IDEA-Helsinki specific health checks."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from idea_shared.health.idea_checks import (
    AzureBlobStorageHealthCheck,
    FCDDataFreshnessHealthCheck,
    InfluxDBHealthCheck,
    SegmentMappingIntegrityHealthCheck,
    WFSServiceHealthCheck,
)


class TestAzureBlobStorageHealthCheck:
    """Tests for Azure Blob Storage health check."""

    @pytest.mark.asyncio
    async def test_healthy_connection(self):
        """Test successful Azure connection.

        Verifies that the Azure Blob Storage health check correctly validates
        connectivity to Azure storage accounts. This ensures the FCD data
        synchronization can access TomTom floating car data from blob storage.
        """
        check = AzureBlobStorageHealthCheck(
            name="azure_check",
            account_name="testaccount",
            container_name="testcontainer",
            sas_token="test_token",
        )

        with patch("idea_shared.health.idea_checks.BlobServiceClient") as mock_client:
            # Mock successful connection
            mock_container = MagicMock()
            mock_container.list_blobs.return_value = ["blob1", "blob2"]
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container
            mock_client.return_value = mock_service

            result = await check.check()

            assert result.status == "healthy"
            assert "testcontainer" in result.message
            assert result.metadata["account"] == "testaccount"
            assert result.metadata["container"] == "testcontainer"

    @pytest.mark.asyncio
    async def test_failed_connection(self):
        """Test failed Azure connection.

        Verifies that authentication failures and connection errors to Azure
        Blob Storage are properly detected and reported as unhealthy. This
        prevents silent failures in FCD data ingestion pipeline.
        """
        check = AzureBlobStorageHealthCheck(
            name="azure_check",
            account_name="testaccount",
            container_name="testcontainer",
            sas_token="invalid_token",
        )

        with patch("idea_shared.health.idea_checks.BlobServiceClient") as mock_client:
            # Mock connection failure
            mock_client.side_effect = Exception("Authentication failed")

            result = await check.check()

            assert result.status == "unhealthy"
            assert "Authentication failed" in result.message
            assert result.metadata["error"] == "Authentication failed"


class TestWFSServiceHealthCheck:
    """Tests for WFS service health check."""

    @pytest.mark.asyncio
    async def test_healthy_wfs_service(self):
        """Test successful WFS service check.

        Verifies that the WFS (Web Feature Service) health check correctly
        validates connectivity to Helsinki's traffic disturbance API. This
        ensures the system can fetch planned roadworks data for validation.
        """
        check = WFSServiceHealthCheck(
            name="wfs_check",
            url="https://test.wfs.service",
        )

        # Mock the parent class check method to return a healthy result
        from idea_shared.health.models import HealthCheckResult

        mock_result = HealthCheckResult(
            name="wfs_check",
            status="healthy",
            message="API responded with status 200",
            metadata={
                "url": "https://test.wfs.service?service=WFS&request=GetCapabilities",
                "status_code": 200,
                "circuit_state": "closed",
            },
        )

        with patch(
            "idea_shared.health.idea_checks.ExternalAPIHealthCheck.check",
            new=AsyncMock(),
        ) as mock_super:
            mock_super.return_value = mock_result
            result = await check.check()

            assert result.status == "healthy"
            assert "WFS service is available" in result.message
            assert result.metadata["service"] == "WFS"

    @pytest.mark.asyncio
    async def test_wfs_circuit_breaker(self):
        """Test WFS service with circuit breaker.

        Verifies that the WFS health check includes circuit breaker configuration
        with appropriate thresholds (3 failures) and timeout (120s). This protects
        the system from repeatedly calling a failing WFS service.
        """
        check = WFSServiceHealthCheck(
            name="wfs_check",
            url="https://test.wfs.service",
        )

        # Test that it inherits circuit breaker functionality
        assert check.circuit_breaker_threshold == 3
        assert check.circuit_breaker_timeout == 120.0


class TestInfluxDBHealthCheck:
    """Tests for InfluxDB health check."""

    @pytest.mark.asyncio
    async def test_healthy_influxdb(self):
        """Test successful InfluxDB connection.

        Verifies that the InfluxDB health check successfully validates database
        connectivity using the ping API. This ensures timeseries storage for
        FCD data and validation results is accessible.
        """
        check = InfluxDBHealthCheck(
            name="influx_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock successful ping
            mock_instance = MagicMock()
            mock_instance.ping.return_value = True
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "healthy"
            assert "InfluxDB is accessible" in result.message
            assert result.metadata["org"] == "test_org"
            assert result.metadata["bucket"] == "test_bucket"

    @pytest.mark.asyncio
    async def test_influxdb_ping_failure(self):
        """Test InfluxDB ping failure.

        Verifies that failed InfluxDB ping attempts (due to invalid credentials
        or unreachable database) are detected and reported as unhealthy. This
        prevents data writes to inaccessible storage.
        """
        check = InfluxDBHealthCheck(
            name="influx_check",
            url="http://localhost:8086",
            token="invalid_token",
            org="test_org",
            bucket="test_bucket",
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock ping failure
            mock_instance = MagicMock()
            mock_instance.ping.return_value = False
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "unhealthy"
            assert "InfluxDB ping failed" in result.message


class TestFCDDataFreshnessHealthCheck:
    """Tests for FCD data freshness health check."""

    @pytest.mark.asyncio
    async def test_fresh_data(self):
        """Test with fresh data.

        Verifies that the FCD freshness check correctly identifies recent data
        within the configured time window. This ensures the IDEA validation
        system has up-to-date traffic data for accurate analysis.
        """
        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock recent data
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime.now(UTC)
            mock_table = MagicMock()
            mock_table.records = [mock_record]

            mock_instance = MagicMock()
            mock_query = MagicMock()
            mock_query.query.return_value = [mock_table]
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "healthy"
            assert "FCD data is fresh" in result.message
            assert result.metadata["max_age_minutes"] == 30

    @pytest.mark.asyncio
    async def test_no_recent_data(self):
        """Test with no recent data.

        Verifies that the freshness check returns degraded status when no data
        is found within the time window. This indicates potential issues with
        the FCD synchronization pipeline without marking the service as completely down.
        """
        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock no data
            mock_instance = MagicMock()
            mock_query = MagicMock()
            mock_query.query.return_value = []
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "degraded"
            assert "No recent FCD data found" in result.message

    @pytest.mark.asyncio
    async def test_backfill_mode_with_historical_data(self):
        """Test backfill mode detection with historical data.

        Verifies that the freshness check correctly identifies backfill mode
        when data exists but is older than the max_age_minutes threshold.
        This prevents false alarms during historical data ingestion.
        """
        from datetime import timedelta

        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock recent query returning empty (no recent data)
            # Mock latest query returning old data (backfill mode)
            mock_old_record = MagicMock()
            old_timestamp = datetime.now(UTC) - timedelta(hours=5)
            mock_old_record.get_time.return_value = old_timestamp
            mock_old_table = MagicMock()
            mock_old_table.records = [mock_old_record]

            mock_instance = MagicMock()
            mock_query = MagicMock()
            # First call returns empty (recent), second returns old data (latest)
            mock_query.query.side_effect = [[], [mock_old_table]]
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "healthy"
            assert "backfilling" in result.message.lower()
            assert result.metadata["mode"] == "backfill"
            assert "latest_data_timestamp" in result.metadata
            assert "backfill_progress" in result.metadata

    @pytest.mark.asyncio
    async def test_backfill_mode_at_threshold(self):
        """Test edge case: data exactly at freshness threshold.

        Verifies that data at exactly the max_age_minutes threshold triggers
        backfill mode detection. This ensures proper handling of boundary conditions.
        """
        from datetime import timedelta

        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock data exactly at threshold (31 minutes old)
            mock_threshold_record = MagicMock()
            threshold_timestamp = datetime.now(UTC) - timedelta(minutes=31)
            mock_threshold_record.get_time.return_value = threshold_timestamp
            mock_threshold_table = MagicMock()
            mock_threshold_table.records = [mock_threshold_record]

            mock_instance = MagicMock()
            mock_query = MagicMock()
            mock_query.query.side_effect = [[], [mock_threshold_table]]
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            # Should be in backfill mode since data_age > max_age_minutes
            assert result.status == "healthy"
            assert result.metadata["mode"] == "backfill"

    @pytest.mark.asyncio
    async def test_backfill_progress_metadata(self):
        """Test backfill progress metadata population.

        Verifies that backfill mode includes detailed progress information
        in the metadata, including timestamp and human-readable progress string.
        """

        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock with specific timestamp for verification
            specific_timestamp = datetime(2025, 10, 15, 14, 30, 0, tzinfo=UTC)
            mock_old_record = MagicMock()
            mock_old_record.get_time.return_value = specific_timestamp
            mock_old_table = MagicMock()
            mock_old_table.records = [mock_old_record]

            mock_instance = MagicMock()
            mock_query = MagicMock()
            mock_query.query.side_effect = [[], [mock_old_table]]
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "healthy"
            assert result.metadata["mode"] == "backfill"
            assert (
                result.metadata["latest_data_timestamp"]
                == specific_timestamp.isoformat()
            )
            assert "2025-10-15" in result.metadata["backfill_progress"]
            assert "data_age_minutes" in result.metadata

    @pytest.mark.asyncio
    async def test_real_time_mode_with_recent_data(self):
        """Test real-time mode with recent data.

        Verifies that when data is within the max_age_minutes threshold,
        the check reports real-time mode with appropriate metadata.
        """
        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
        )

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            # Mock recent data
            mock_recent_record = MagicMock()
            mock_recent_record.get_time.return_value = datetime.now(UTC)
            mock_recent_table = MagicMock()
            mock_recent_table.records = [mock_recent_record]

            mock_instance = MagicMock()
            mock_query = MagicMock()
            mock_query.query.return_value = [mock_recent_table]
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            result = await check.check()

            assert result.status == "healthy"
            assert "fresh" in result.message.lower()
            assert result.metadata["mode"] == "real_time"
            assert result.metadata["data_age_minutes"] < 30

    @pytest.mark.asyncio
    async def test_configurable_backfill_lookback(self):
        """Test configurable backfill lookback period.

        Verifies that the backfill_lookback_days parameter can be configured
        to control how far back the health check searches for data during
        backfill mode detection.
        """
        check = FCDDataFreshnessHealthCheck(
            name="freshness_check",
            url="http://localhost:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
            max_age_minutes=30,
            backfill_lookback_days=14,  # Custom 14-day lookback
        )

        # Verify parameter is stored
        assert check.backfill_lookback_days == 14

        with patch("idea_shared.health.idea_checks.InfluxDBClient") as mock_client:
            mock_instance = MagicMock()
            mock_query = MagicMock()
            mock_query.query.return_value = []
            mock_instance.query_api.return_value = mock_query
            mock_instance.close = MagicMock()
            mock_client.return_value = mock_instance

            await check.check()

            # Verify the query was called with 14-day range
            query_calls = mock_query.query.call_args_list
            # Second call should be the latest_query with custom lookback
            if len(query_calls) > 1:
                latest_query = query_calls[1][1]["query"]
                assert "-14d" in latest_query


class TestSegmentMappingIntegrityHealthCheck:
    """Tests for segment mapping integrity health check."""

    @pytest.mark.asyncio
    async def test_valid_mapping_files(self, tmp_path):
        """Test with valid mapping files.

        Verifies that the segment mapping integrity check correctly validates
        properly formatted mapping and history JSON files. This ensures the
        system can track road segment geometries and their changes over time.
        """
        # Create test files
        mapping_file = tmp_path / "segments_mapping.json"
        history_file = tmp_path / "master_segment_history.json"

        mapping_data = {
            "segment1": {
                "geometry": {"type": "LineString", "coordinates": []},
                "properties": {"name": "Test Segment"},
            }
        }
        history_data = {"segment1": {"updates": []}}

        mapping_file.write_text(json.dumps(mapping_data))
        history_file.write_text(json.dumps(history_data))

        check = SegmentMappingIntegrityHealthCheck(
            name="mapping_check",
            mapping_file_path=str(mapping_file),
            history_file_path=str(history_file),
            startup_grace_minutes=0,
        )

        result = await check.check()

        assert result.status == "healthy"
        assert "valid" in result.message
        assert result.metadata["segment_count"] == 1
        assert result.metadata["history_entries"] == 1

    @pytest.mark.asyncio
    async def test_missing_mapping_file(self, tmp_path):
        """Test with missing mapping file.

        Verifies that the integrity check detects missing segment mapping files
        and returns degraded status. This prevents the system from attempting
        to process segments without valid geometry data.
        """
        missing_file = tmp_path / "nonexistent.json"

        check = SegmentMappingIntegrityHealthCheck(
            name="mapping_check",
            mapping_file_path=str(missing_file),
            history_file_path=str(tmp_path / "history.json"),
            startup_grace_minutes=0,
        )

        result = await check.check()

        assert result.status == "degraded"
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_invalid_json(self, tmp_path):
        """Test with invalid JSON in mapping file.

        Verifies that the integrity check detects corrupted or malformed JSON
        in segment mapping files. This prevents parsing errors during segment
        processing and ensures data integrity.
        """
        mapping_file = tmp_path / "segments_mapping.json"
        mapping_file.write_text("invalid json {")

        check = SegmentMappingIntegrityHealthCheck(
            name="mapping_check",
            mapping_file_path=str(mapping_file),
            history_file_path=str(tmp_path / "history.json"),
            startup_grace_minutes=0,
        )

        result = await check.check()

        assert result.status in ["degraded", "unhealthy"]
        assert "empty or unreadable" in result.message

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, tmp_path):
        """Test with missing required fields in segments.

        Verifies that the integrity check detects segments missing required
        fields like geometry. This ensures all segments have the necessary
        data for spatial intersection detection and validation processing.
        """
        mapping_file = tmp_path / "segments_mapping.json"

        # Missing geometry field
        invalid_data = {
            "segment1": {
                "properties": {"name": "Test"},
            }
        }

        mapping_file.write_text(json.dumps(invalid_data))

        check = SegmentMappingIntegrityHealthCheck(
            name="mapping_check",
            mapping_file_path=str(mapping_file),
            history_file_path=str(tmp_path / "history.json"),
            startup_grace_minutes=0,
        )

        result = await check.check()

        assert result.status in ["degraded", "unhealthy"]
        assert "geometry" in str(result.metadata.get("issues", []))
