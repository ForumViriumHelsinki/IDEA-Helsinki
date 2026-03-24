"""Unit tests for FCD Manager health checks."""

import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from health_checks import (  # ty: ignore[unresolved-import]
    ProcessingPipelineHealthCheck,
    SegmentMappingFreshnessHealthCheck,
    UpdateCycleHealthCheck,
)


class TestUpdateCycleHealthCheck:
    """Test suite for UpdateCycleHealthCheck."""

    @pytest.mark.asyncio
    async def test_initial_startup_grace_period(self):
        """Test that health check returns healthy during startup grace period."""
        check = UpdateCycleHealthCheck(
            healthy_threshold_minutes=10,
            degraded_threshold_minutes=30,
        )

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "healthy"
        assert "grace period" in result.message.lower()
        assert "startup_time" in result.metadata

    @pytest.mark.asyncio
    async def test_no_updates_after_grace_period(self):
        """Test that health check returns unhealthy when no updates after grace period."""
        check = UpdateCycleHealthCheck(
            healthy_threshold_minutes=10,
            degraded_threshold_minutes=30,
        )
        # Simulate grace period has passed
        check.startup_time = datetime.now(UTC) - timedelta(minutes=15)

        result = await check.check()

        assert result.message is not None
        assert result.status == "unhealthy"
        assert "no update cycles completed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_healthy_update_cycle(self):
        """Test that health check returns healthy when updates are recent."""
        check = UpdateCycleHealthCheck(
            healthy_threshold_minutes=10,
            degraded_threshold_minutes=30,
        )
        # Simulate recent update
        check.update_timestamp()

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "healthy"
        # During startup, grace period message is expected
        assert (
            "running normally" in result.message.lower()
            or "grace period" in result.message.lower()
        )
        # If not in grace period, check minutes_since_update
        if "grace period" not in result.message.lower():
            assert result.metadata["minutes_since_update"] < 1

    @pytest.mark.asyncio
    async def test_degraded_update_cycle(self):
        """Test that health check returns degraded when updates are delayed."""
        check = UpdateCycleHealthCheck(
            healthy_threshold_minutes=10,
            degraded_threshold_minutes=30,
        )
        # Simulate delayed update (15 minutes ago)
        check.last_update_time = datetime.now(UTC) - timedelta(minutes=15)
        check.startup_time = datetime.now(UTC) - timedelta(hours=1)

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "degraded"
        assert "delayed" in result.message.lower()
        assert 14 < result.metadata["minutes_since_update"] < 16

    @pytest.mark.asyncio
    async def test_unhealthy_update_cycle(self):
        """Test that health check returns unhealthy when updates are very late."""
        check = UpdateCycleHealthCheck(
            healthy_threshold_minutes=10,
            degraded_threshold_minutes=30,
        )
        # Simulate very late update (45 minutes ago)
        check.last_update_time = datetime.now(UTC) - timedelta(minutes=45)
        check.startup_time = datetime.now(UTC) - timedelta(hours=2)

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "unhealthy"
        assert "has not run" in result.message.lower()
        assert result.metadata["minutes_since_update"] > 40


class TestSegmentMappingFreshnessHealthCheck:
    """Test suite for SegmentMappingFreshnessHealthCheck."""

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """Test that health check returns unhealthy when file doesn't exist."""
        check = SegmentMappingFreshnessHealthCheck(
            mapping_file_path="/nonexistent/file.json",
            max_age_minutes=15,
        )

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "unhealthy"
        assert "not found" in result.message.lower()
        assert result.metadata["exists"] is False

    @pytest.mark.asyncio
    async def test_fresh_file(self):
        """Test that health check returns healthy for a fresh file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
            tmp_file.write(b'{"test": "data"}')
            tmp_path = tmp_file.name

        try:
            check = SegmentMappingFreshnessHealthCheck(
                mapping_file_path=tmp_path,
                max_age_minutes=15,
            )

            result = await check.check()

            assert result.message is not None
            assert result.metadata is not None
            assert result.status == "healthy"
            assert "fresh" in result.message.lower()
            assert result.metadata["age_minutes"] < 1
            assert result.metadata["file_size_bytes"] > 0
        finally:
            Path(tmp_path).unlink()

    @pytest.mark.asyncio
    async def test_stale_file(self):
        """Test that health check returns degraded for a stale file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
            tmp_file.write(b'{"test": "data"}')
            tmp_path = tmp_file.name

        try:
            # Modify the file's timestamp to make it appear old
            import os

            old_time = datetime.now(UTC) - timedelta(minutes=30)
            os.utime(tmp_path, (old_time.timestamp(), old_time.timestamp()))

            check = SegmentMappingFreshnessHealthCheck(
                mapping_file_path=tmp_path,
                max_age_minutes=15,
            )

            result = await check.check()

            assert result.message is not None
            assert result.metadata is not None
            assert result.status == "degraded"
            assert "stale" in result.message.lower()
            assert result.metadata["age_minutes"] > 25
        finally:
            Path(tmp_path).unlink()


class TestProcessingPipelineHealthCheck:
    """Test suite for ProcessingPipelineHealthCheck."""

    @pytest.mark.asyncio
    async def test_pipeline_not_started(self):
        """Test health check when pipeline hasn't started."""
        check = ProcessingPipelineHealthCheck()

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "healthy"
        assert "not yet started" in result.message.lower()
        assert result.metadata["total_blobs_processed"] == 0

    @pytest.mark.asyncio
    async def test_pipeline_processing(self):
        """Test health check when pipeline is currently processing."""
        check = ProcessingPipelineHealthCheck()
        check.record_processing_start()

        result = await check.check()

        assert result.message is not None
        assert result.status == "healthy"
        assert "currently running" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pipeline_processing_too_long(self):
        """Test health check when pipeline processing takes too long."""
        check = ProcessingPipelineHealthCheck()
        check.processing_start_time = datetime.now(UTC) - timedelta(minutes=15)

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "degraded"
        assert "taking longer than expected" in result.message.lower()
        assert result.metadata["processing_duration_minutes"] > 10

    @pytest.mark.asyncio
    async def test_pipeline_completed_successfully(self):
        """Test health check after successful pipeline completion."""
        check = ProcessingPipelineHealthCheck()
        check.record_processing_start()
        check.record_processing_complete(10)

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "healthy"
        assert "healthy" in result.message.lower()
        assert result.metadata["total_blobs_processed"] == 10
        assert "last_processing_complete" in result.metadata

    @pytest.mark.asyncio
    async def test_pipeline_with_recent_error(self):
        """Test health check with recent error."""
        check = ProcessingPipelineHealthCheck()
        check.record_error("Connection timeout")

        result = await check.check()

        assert result.message is not None
        assert result.metadata is not None
        assert result.status == "degraded"
        assert "Connection timeout" in result.message
        assert result.metadata["last_error"] == "Connection timeout"
        assert result.metadata["minutes_since_error"] < 1

    @pytest.mark.asyncio
    async def test_pipeline_with_old_error(self):
        """Test health check with old error (should be healthy)."""
        check = ProcessingPipelineHealthCheck()
        check.last_error = "Old error"
        check.last_error_time = datetime.now(UTC) - timedelta(minutes=10)
        check.processing_end_time = datetime.now(UTC) - timedelta(minutes=1)
        check.blobs_processed = 5

        result = await check.check()

        assert result.metadata is not None
        assert result.status == "healthy"
        assert result.metadata["minutes_since_error"] > 9

    @pytest.mark.asyncio
    async def test_pipeline_multiple_cycles(self):
        """Test health check after multiple processing cycles."""
        check = ProcessingPipelineHealthCheck()

        # First cycle
        check.record_processing_start()
        check.record_processing_complete(5)

        # Second cycle
        check.record_processing_start()
        check.record_processing_complete(7)

        result = await check.check()

        assert result.metadata is not None
        assert result.status == "healthy"
        assert result.metadata["total_blobs_processed"] == 12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
