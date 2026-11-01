"""HTTP Security Headers Middleware enforcing defense-in-depth browser protections."""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Appends standard OWASP and enterprise security headers to every response.
    Protects against MIME confusion, clickjacking, XSS, and unapproved device access.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # 1. Prevent MIME-type confusion / sniffing attacks
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. Block framing to prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # 3. Enable legacy XSS filter protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 4. Strict referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 5. Disable unused hardware permissions
        response.headers["Permissions-Policy"] = "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=()"

        # 6. Basic Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self' http://localhost:* http://127.0.0.1:*;"
        )

        return response

