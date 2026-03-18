"""Pydantic models for health check responses."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    """Result from a single health check."""

    name: str = Field(..., description="Name of the health check")
    status: Literal["healthy", "unhealthy", "degraded"] = Field(
        ..., description="Current status of the check"
    )
    message: str | None = None
    metadata: dict[str, Any] | None = None
    execution_time_ms: float | None = Field(
        None, description="Execution time in milliseconds"
    )


class ReadinessResponse(BaseModel):
    """Response model for the readiness endpoint."""

    ready: bool = Field(..., description="Whether the service is ready")
    checks: dict[str, str] = Field(
        ..., description="Status of individual health checks"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of the check"
    )


class LivenessResponse(BaseModel):
    """Response model for the liveness endpoint."""

    status: Literal["ok"] = Field(default="ok", description="Liveness status")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of the check"
    )


class MetricsResponse(BaseModel):
    """Response model for the metrics endpoint (placeholder for future use)."""

    metrics: dict[str, Any] = Field(default_factory=dict, description="Service metrics")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of the metrics",
    )
