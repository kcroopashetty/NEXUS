"""NEXUS Enterprise Knowledge Intelligence & Assurance Platform — FastAPI Application Entrypoint."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import NexusException, create_error_response
from app.core.request_context import RequestIdMiddleware, get_current_request_id
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.rate_limit import RateLimiterMiddleware
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.documents import router as documents_router
from app.api.v1.versions import router as versions_router
from app.api.v1.chat import router as chat_router
from app.api.v1.security import router as security_router
from app.db.base import Base
from app.db.session import engine
import app.models  # Ensure all models are registered with Base.metadata

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("nexus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hooks: initialize storage and database tables."""
    logger.info("Initializing NEXUS platform services...")
    # Create tables if using SQLite or for dev setup (Alembic handles prod migrations)
    Base.metadata.create_all(bind=engine)

    # Auto-migrate SQLite schema if missing columns (e.g. pgvector embedding column added during consolidation)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                res = conn.execute(text("PRAGMA table_info(document_chunks)")).fetchall()
                col_names = [r[1] for r in res]
                if "embedding" not in col_names:
                    logger.info("Auto-migrating SQLite: Adding 'embedding' column to document_chunks...")
                    conn.execute(text("ALTER TABLE document_chunks ADD COLUMN embedding TEXT;"))
                    conn.commit()
    except Exception as exc:
        logger.warning("Could not auto-check SQLite schema: %s", exc)

    logger.info("Database schema initialized.")
    yield
    logger.info("Shutting down NEXUS platform services...")


app = FastAPI(
    title="NEXUS API",
    description="Enterprise Knowledge Intelligence & Assurance Platform",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG or settings.NEXUS_ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# 1. Security Headers middleware (defense-in-depth HTTP headers)
app.add_middleware(SecurityHeadersMiddleware)

# 2. Sliding window Rate Limiter middleware
app.add_middleware(
    RateLimiterMiddleware,
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    burst_limit=settings.RATE_LIMIT_BURST,
)

# 3. Request correlation ID middleware
app.add_middleware(RequestIdMiddleware)

# 4. Strict CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# 3. Standardized Error Handlers
@app.exception_handler(NexusException)
async def nexus_exception_handler(request: Request, exc: NexusException):
    req_id = getattr(request.state, "request_id", get_current_request_id())
    logger.warning("NexusException: [%s] %s (request_id=%s)", exc.code, exc.message, req_id)
    return create_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=req_id,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", get_current_request_id())
    code_map = {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    logger.warning("HTTPException: %s status=%d (request_id=%s)", exc.detail, exc.status_code, req_id)
    return create_error_response(
        code=code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=req_id,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", get_current_request_id())
    logger.warning("RequestValidationError: %s (request_id=%s)", exc.errors(), req_id)
    # Avoid leaking sensitive input structure; return clean message
    return create_error_response(
        code="INVALID_REQUEST_PAYLOAD",
        message="Request payload failed schema validation.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request_id=req_id,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", get_current_request_id())
    logger.exception("Unhandled server exception: %s (request_id=%s)", str(exc), req_id)
    return create_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=req_id,
    )


# 4. Include Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(documents_router)
app.include_router(versions_router)
app.include_router(chat_router)
app.include_router(security_router)
