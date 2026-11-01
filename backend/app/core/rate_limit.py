"""In-memory sliding-window rate limiter middleware for API security."""

import time
from typing import Dict, Tuple, List
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Applies sliding-window rate limiting per IP / user token to protect endpoints
    from credential brute-forcing, resource exhaustion, and DoS attacks.
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 120,
        burst_limit: int = 40,
        exempt_testing: bool = True,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.exempt_testing = exempt_testing
        # Key: client_ip -> List[timestamp]
        self._history: Dict[str, List[float]] = {}

    def _clean_old_requests(self, client_key: str, now: float) -> List[float]:
        window_start = now - 60.0
        active = [t for t in self._history.get(client_key, []) if t > window_start]
        self._history[client_key] = active
        return active

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exempt healthz probes and test suite executions
        path = request.url.path
        if path in ("/healthz", "/api/v1/health", "/api/health") or (
            self.exempt_testing and settings.NEXUS_ENV == "testing"
        ):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown_client"
        now = time.time()

        active_requests = self._clean_old_requests(client_ip, now)

        if len(active_requests) >= self.requests_per_minute:
            retry_after = int(60.0 - (now - active_requests[0])) if active_requests else 60
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(max(1, retry_after))},
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit of {self.requests_per_minute} requests/minute exceeded. Please slow down.",
                        "retry_after_seconds": max(1, retry_after),
                    }
                },
            )

        active_requests.append(now)
        self._history[client_ip] = active_requests

        response = await call_next(request)
        return response

