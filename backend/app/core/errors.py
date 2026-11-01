"""Standardized error responses and exceptions for NEXUS."""

from typing import Optional, Any, Dict
from fastapi import Request, status
from fastapi.responses import JSONResponse


class NexusException(Exception):
    """Base exception for all NEXUS application errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(NexusException):
    """Raised when authentication fails or is missing."""

    def __init__(self, message: str = "Invalid credentials or expired session.", code: str = "AUTHENTICATION_FAILED"):
        super().__init__(code=code, message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class TenantAccessDeniedError(NexusException):
    """Raised when user is not authorized for the requested tenant context."""

    def __init__(
        self,
        message: str = "You are not authorised to access this tenant or resource.",
        code: str = "TENANT_ACCESS_DENIED",
    ):
        super().__init__(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN)


class ResourceNotFoundError(NexusException):
    """Raised when a resource does not exist within the authorized tenant scope."""

    def __init__(
        self,
        message: str = "The requested resource was not found.",
        code: str = "RESOURCE_NOT_FOUND",
    ):
        # Do not leak tenant existence; return 404
        super().__init__(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


class InsufficientRoleError(NexusException):
    """Raised when the user's role in the tenant does not allow the requested action."""

    def __init__(
        self,
        message: str = "Insufficient permissions to perform this operation.",
        code: str = "INSUFFICIENT_ROLE",
    ):
        super().__init__(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN)


class ValidationPayloadError(NexusException):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        code: str = "INVALID_REQUEST_PAYLOAD",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, details=details)


class DocumentProcessingError(NexusException):
    """Raised when document extraction, validation, or processing fails."""

    def __init__(
        self,
        message: str,
        code: str = "DOCUMENT_PROCESSING_FAILED",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        super().__init__(code=code, message=message, status_code=status_code)


def create_error_response(code: str, message: str, status_code: int, request_id: str = "unknown") -> JSONResponse:
    """Format an error into the standard NEXUS envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
    )

