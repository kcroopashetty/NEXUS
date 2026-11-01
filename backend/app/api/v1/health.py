"""Health and readiness check endpoints."""

import os
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
import httpx

from app.core.config import settings
from app.db.session import get_db
from app.schemas.health import HealthResponse, ServiceStatus
from app.services.llm.gateway import inference_gateway

router = APIRouter(tags=["Health & System"])


@router.get("/healthz", response_model=HealthResponse)
def liveness_probe():
    """Basic liveness probe for container orchestrators."""
    return HealthResponse(
        status="healthy",
        environment=settings.NEXUS_ENV,
        services={
            "api": ServiceStatus(status="healthy", details="FastAPI gateway online")
        },
    )


@router.get("/api/v1/health", response_model=HealthResponse)
def readiness_probe(db: Session = Depends(get_db)):
    """Comprehensive readiness probe verifying database, storage, and inference connectivity."""
    services = {}
    overall_healthy = True

    # 1. Database check
    try:
        db.execute(text("SELECT 1"))
        services["database"] = ServiceStatus(status="healthy", details="Connected and responsive")
    except Exception as exc:
        overall_healthy = False
        services["database"] = ServiceStatus(status="unhealthy", details=str(exc))

    # 2. Local storage check
    try:
        os.makedirs(settings.NEXUS_STORAGE_DIR, exist_ok=True)
        test_file = os.path.join(settings.NEXUS_STORAGE_DIR, ".health_check")
        with open(test_file, "w") as f:
            f.write("ok")
        if os.path.exists(test_file):
            os.remove(test_file)
        services["storage"] = ServiceStatus(status="healthy", details=f"Storage directory writable at {settings.NEXUS_STORAGE_DIR}")
    except Exception as exc:
        overall_healthy = False
        services["storage"] = ServiceStatus(status="unhealthy", details=str(exc))

    # 3. Ollama probe (advisory, does not block startup if running offline/mock mode)
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                services["ollama"] = ServiceStatus(status="healthy", details=f"Ollama reachable at {settings.OLLAMA_BASE_URL}")
            else:
                services["ollama"] = ServiceStatus(status="degraded", details=f"Ollama returned HTTP {resp.status_code}")
    except Exception:
        services["ollama"] = ServiceStatus(status="degraded", details="Ollama instance offline or unreachable (mock fallback available)")

    return JSONResponse(
        status_code=status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=HealthResponse(
            status="healthy" if overall_healthy else "degraded",
            environment=settings.NEXUS_ENV,
            services=services,
        ).model_dump(),
    )


@router.get("/api/health")
def api_health_alias():
    """Compatibility endpoint for tools/extensions polling /api/health."""
    return {
        "status": "healthy",
        "service": "NEXUS Platform Gateway",
        "environment": settings.NEXUS_ENV,
        "version": "1.0.0",
    }


@router.get("/api/health/inference")
@router.get("/api/v1/health/inference")
def get_inference_gateway_health():
    """Real-time GPU hardware stats, queue depth, active requests, and scheduler metrics."""
    return inference_gateway.get_status_summary()

