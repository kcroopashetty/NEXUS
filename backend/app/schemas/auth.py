"""Pydantic schemas for authentication and tokens."""

import uuid
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """User login credential payload."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="Plaintext password")


class MembershipSummary(BaseModel):
    """Concise representation of an active tenant membership."""

    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    role: str
    status: str

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    """User profile response with authorized memberships."""

    id: uuid.UUID
    email: str
    display_name: str
    platform_role: str
    status: str
    memberships: List[MembershipSummary] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserProfileResponse

