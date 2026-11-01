"""Pydantic schemas for tenant management and memberships."""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr


class TenantCreateRequest(BaseModel):
    """Payload to provision a new tenant workspace."""

    slug: str = Field(..., min_length=2, max_length=80, pattern="^[a-z0-9-]+$", description="Lowercase alphanumeric slug")
    name: str = Field(..., min_length=2, max_length=200, description="Workspace display name")


class TenantResponse(BaseModel):
    """Tenant workspace details."""

    id: uuid.UUID
    slug: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberAssignRequest(BaseModel):
    """Payload to assign or invite a user into a tenant workspace."""

    email: EmailStr = Field(..., description="Target user's email")
    display_name: Optional[str] = Field(None, description="Optional display name if inviting a new user")
    password: Optional[str] = Field(None, min_length=8, description="Initial password if creating user")
    role: str = Field("EMPLOYEE", pattern="^(CLIENT_ADMIN|EMPLOYEE)$", description="Role within the tenant")


class MemberUpdateRequest(BaseModel):
    """Payload to update an existing member's role or access status."""

    role: Optional[str] = Field(None, pattern="^(CLIENT_ADMIN|EMPLOYEE)$")
    status: Optional[str] = Field(None, pattern="^(ACTIVE|REVOKED|SUSPENDED)$")


class TenantMemberResponse(BaseModel):
    """Details of a member within a tenant."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_display_name: str
    role: str
    status: str
    last_permission_change_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}

