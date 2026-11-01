"""Pydantic schemas for health and system readiness."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    """Individual service readiness status."""

    status: str = Field(..., description="'healthy', 'degraded', or 'unhealthy'")
    details: Optional[str] = Field(None, description="Optional diagnostic details")


class HealthResponse(BaseModel):
    """System health check response."""

    status: str = Field(..., description="Overall system health status")
    environment: str = Field(..., description="Active runtime environment")
    version: str = Field(default="1.0.0", description="Application version")
    services: Dict[str, ServiceStatus] = Field(default_factory=dict, description="Component status map")

