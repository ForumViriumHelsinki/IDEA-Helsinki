"""Pydantic models for health check responses."""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    """Result from a single health check."""

    name: str = Field(..., description="Name of the health check")
    status: Literal["healthy", "unhealthy", "degraded"] = Field(
        ..., description="Current status of the check"
    )
    message: Optional[str] = Field(None, description="Optional status message")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Optional additional metadata"
    )


class ReadinessResponse(BaseModel):
    """Response model for the readiness endpoint."""

    ready: bool = Field(..., description="Whether the service is ready")
    checks: Dict[str, str] = Field(
        ..., description="Status of individual health checks"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of the check"
    )


class LivenessResponse(BaseModel):
    """Response model for the liveness endpoint."""

    status: Literal["ok"] = Field(default="ok", description="Liveness status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of the check"
    )


class MetricsResponse(BaseModel):
    """Response model for the metrics endpoint (placeholder for future use)."""

    metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Service metrics"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of the metrics"
    )