"""Unit tests for health check models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from idea_shared.health.models import (
    HealthCheckResult,
    LivenessResponse,
    MetricsResponse,
    ReadinessResponse,
)


class TestHealthCheckResult:
    """Tests for HealthCheckResult model."""

    def test_valid_health_check_result(self):
        """Test creating a valid health check result."""
        result = HealthCheckResult(
            name="test_check",
            status="healthy",
            message="All good",
            metadata={"key": "value"},
        )
        assert result.name == "test_check"
        assert result.status == "healthy"
        assert result.message == "All good"
        assert result.metadata == {"key": "value"}

    def test_minimal_health_check_result(self):
        """Test creating a minimal health check result."""
        result = HealthCheckResult(name="test", status="unhealthy")
        assert result.name == "test"
        assert result.status == "unhealthy"
        assert result.message is None
        assert result.metadata is None

    def test_invalid_status(self):
        """Test that invalid status values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HealthCheckResult(name="test", status="invalid")

        errors = exc_info.value.errors()
        assert any(
            error["type"] == "literal_error" and "status" in str(error["loc"])
            for error in errors
        )

    def test_all_valid_statuses(self):
        """Test all valid status values."""
        valid_statuses = ["healthy", "unhealthy", "degraded"]
        for status in valid_statuses:
            result = HealthCheckResult(name="test", status=status)
            assert result.status == status


class TestReadinessResponse:
    """Tests for ReadinessResponse model."""

    def test_valid_readiness_response(self):
        """Test creating a valid readiness response."""
        response = ReadinessResponse(
            ready=True,
            checks={"database": "healthy", "api": "healthy"},
            timestamp=datetime(2025, 1, 25, 10, 0, 0),
        )
        assert response.ready is True
        assert response.checks == {"database": "healthy", "api": "healthy"}
        assert response.timestamp == datetime(2025, 1, 25, 10, 0, 0)

    def test_readiness_with_default_timestamp(self):
        """Test that timestamp is auto-generated if not provided."""
        response = ReadinessResponse(
            ready=False,
            checks={"database": "unhealthy"},
        )
        assert response.ready is False
        assert response.checks == {"database": "unhealthy"}
        assert isinstance(response.timestamp, datetime)
        assert (datetime.utcnow() - response.timestamp).total_seconds() < 1

    def test_empty_checks(self):
        """Test readiness response with empty checks."""
        response = ReadinessResponse(ready=True, checks={})
        assert response.ready is True
        assert response.checks == {}


class TestLivenessResponse:
    """Tests for LivenessResponse model."""

    def test_default_liveness_response(self):
        """Test creating a default liveness response."""
        response = LivenessResponse()
        assert response.status == "ok"
        assert isinstance(response.timestamp, datetime)
        assert (datetime.utcnow() - response.timestamp).total_seconds() < 1

    def test_liveness_with_explicit_timestamp(self):
        """Test liveness response with explicit timestamp."""
        timestamp = datetime(2025, 1, 25, 12, 0, 0)
        response = LivenessResponse(timestamp=timestamp)
        assert response.status == "ok"
        assert response.timestamp == timestamp


class TestMetricsResponse:
    """Tests for MetricsResponse model."""

    def test_default_metrics_response(self):
        """Test creating a default metrics response."""
        response = MetricsResponse()
        assert response.metrics == {}
        assert isinstance(response.timestamp, datetime)

    def test_metrics_with_data(self):
        """Test metrics response with actual metrics."""
        metrics_data = {
            "requests_total": 100,
            "errors_total": 5,
            "response_time_ms": 250.5,
        }
        response = MetricsResponse(metrics=metrics_data)
        assert response.metrics == metrics_data

    def test_metrics_with_nested_data(self):
        """Test metrics response with nested data structures."""
        nested_metrics = {
            "health_checks": {
                "database": {"success": 100, "failure": 2},
                "api": {"success": 50, "failure": 0},
            },
            "system": {"cpu": 45.2, "memory": 78.5},
        }
        response = MetricsResponse(metrics=nested_metrics)
        assert response.metrics == nested_metrics
