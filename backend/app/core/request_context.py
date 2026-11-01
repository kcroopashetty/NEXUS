"""Request correlation context and utilities."""

import uuid
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

# Context variable for holding request ID across async tasks
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_current_request_id() -> str:
    """Retrieve the current request's unique ID."""
    req_id = request_id_ctx.get()
    return req_id if req_id else str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to inject or preserve request correlation IDs."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        request.state.request_id = req_id

        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)

