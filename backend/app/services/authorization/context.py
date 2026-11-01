"""AuthorizedTenantContext and Permission Change Guard service."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, Header, Path, Request, status
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthenticationError,
    TenantAccessDeniedError,
    InsufficientRoleError,
)
from app.core.security import decode_access_token
from app.db.session import get_db
from app.db.rls import TenantRLSManager
from app.models import User, Tenant, TenantMembership


@dataclass(frozen=True)
class AuthorizedTenantContext:
    """Immutable server-derived context containing verified tenant and role permissions."""

    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    user_id: uuid.UUID
    user_email: str
    user_display_name: str
    membership_role: str  # 'CLIENT_ADMIN' or 'EMPLOYEE'
    platform_role: str  # 'PLATFORM_ADMIN' or 'USER'
    last_permission_change_at: datetime

    def is_client_admin(self) -> bool:
        """Check if user has client administrator privileges in this tenant."""
        return self.membership_role == "CLIENT_ADMIN" or self.platform_role == "PLATFORM_ADMIN"

    def is_platform_admin(self) -> bool:
        """Check if user is a global platform administrator."""
        return self.platform_role == "PLATFORM_ADMIN"

    def require_client_admin(self) -> None:
        """Raise error if not a client admin or platform admin."""
        if not self.is_client_admin():
            raise InsufficientRoleError("Client administrator privileges required for this operation.")


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate caller via either:
    1. HttpOnly Server-Side Session Cookie ('nexus_session') - Invigilator recommended, immune to XSS token theft
    2. Bearer Authorization header (for automated testing / CLI tools)
    """
    token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif "nexus_session" in request.cookies:
        token = request.cookies.get("nexus_session")

    if not token:
        raise AuthenticationError("Authorization required. Missing session cookie or Bearer token.")

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise AuthenticationError("Session token is invalid or has expired.")

    user_id_str = payload["sub"]
    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid user identity in token.")

    user = db.query(User).filter(User.id == user_uuid, User.status == "ACTIVE").first()
    if not user:
        raise AuthenticationError("User account is inactive or no longer exists.")

    return user


def require_platform_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Dependency ensuring caller has PLATFORM_ADMIN role."""
    if current_user.platform_role != "PLATFORM_ADMIN":
        raise InsufficientRoleError("Platform administrator privileges required.")
    TenantRLSManager.set_bypass_rls(db)
    return current_user


def get_authorized_tenant_context(
    tenant_id: uuid.UUID = Path(..., description="Target tenant workspace UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthorizedTenantContext:
    """
    Permission Change Guard: Live PostgreSQL verification of tenant membership & role.
    
    Non-negotiable rules enforced:
    1. Tenant must exist and have status 'ACTIVE'.
    2. User must have an active membership in this tenant (unless PLATFORM_ADMIN in emergency).
    3. Re-checks live membership status on every single request to prevent stale permissions.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.status == "ACTIVE").first()
    if not tenant:
        # Deny-by-default; do not leak whether tenant exists
        raise TenantAccessDeniedError("Access to this tenant workspace is denied.")

    membership = (
        db.query(TenantMembership)
        .filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == current_user.id,
            TenantMembership.status == "ACTIVE",
        )
        .first()
    )

    if not membership:
        # Platform admin bypass for explicit administrative oversight if needed
        if current_user.platform_role == "PLATFORM_ADMIN":
            TenantRLSManager.set_bypass_rls(db)
            return AuthorizedTenantContext(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                tenant_name=tenant.name,
                user_id=current_user.id,
                user_email=current_user.email,
                user_display_name=current_user.display_name,
                membership_role="CLIENT_ADMIN",
                platform_role="PLATFORM_ADMIN",
                last_permission_change_at=datetime.now(timezone.utc),
            )
        raise TenantAccessDeniedError("You are not an active member of this tenant workspace.")

    # Configure PostgreSQL transaction-scoped RLS context
    TenantRLSManager.set_tenant_context(db, tenant.id)

    return AuthorizedTenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        user_id=current_user.id,
        user_email=current_user.email,
        user_display_name=current_user.display_name,
        membership_role=membership.role,
        platform_role=current_user.platform_role,
        last_permission_change_at=membership.last_permission_change_at,
    )


def require_client_admin_context(
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
) -> AuthorizedTenantContext:
    """Dependency enforcing that caller has CLIENT_ADMIN privileges in the tenant."""
    ctx.require_client_admin()
    return ctx

