"""Tenant workspace and membership management endpoints."""

import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.errors import NexusException, ResourceNotFoundError, InsufficientRoleError
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Tenant, TenantMembership, User, AuditEvent
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantResponse,
    MemberAssignRequest,
    MemberUpdateRequest,
    TenantMemberResponse,
)
from app.services.authorization.context import (
    get_current_user,
    require_platform_admin,
    get_authorized_tenant_context,
    require_client_admin_context,
    AuthorizedTenantContext,
)

router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants & Workspaces"])


@router.get("", response_model=List[TenantResponse])
def list_my_tenants(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all workspaces where the current user holds an active membership.
    Platform admins can see all active tenants.
    """
    if current_user.platform_role == "PLATFORM_ADMIN":
        tenants = db.query(Tenant).filter(Tenant.status == "ACTIVE").order_by(Tenant.name).all()
        return tenants

    memberships = (
        db.query(TenantMembership)
        .filter(TenantMembership.user_id == current_user.id, TenantMembership.status == "ACTIVE")
        .all()
    )
    tenant_ids = [m.tenant_id for m in memberships]
    tenants = db.query(Tenant).filter(Tenant.id.in_(tenant_ids), Tenant.status == "ACTIVE").order_by(Tenant.name).all()
    return tenants


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreateRequest,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Platform administrator endpoint to provision a new tenant workspace."""
    existing = db.query(Tenant).filter(Tenant.slug == payload.slug.lower().strip()).first()
    if existing:
        raise NexusException(
            code="TENANT_SLUG_CONFLICT",
            message=f"A tenant with slug '{payload.slug}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    tenant = Tenant(
        slug=payload.slug.lower().strip(),
        name=payload.name.strip(),
        status="ACTIVE",
    )
    db.add(tenant)
    db.flush()

    # Automatically grant platform admin a client admin membership for emergency oversight
    membership = TenantMembership(
        tenant_id=tenant.id,
        user_id=current_user.id,
        role="CLIENT_ADMIN",
        status="ACTIVE",
    )
    db.add(membership)

    audit = AuditEvent(
        tenant_id=tenant.id,
        actor_user_id=current_user.id,
        action="TENANT_CREATE",
        resource_type="TENANT",
        resource_id=tenant.id,
        outcome="SUCCESS",
        metadata_json={"slug": tenant.slug, "name": tenant.name},
    )
    db.add(audit)
    db.commit()
    db.refresh(tenant)

    return tenant


@router.get("/{tenant_id}/members", response_model=List[TenantMemberResponse])
def list_tenant_members(
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """Client admin endpoint to view all registered members of the tenant workspace."""
    memberships = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == ctx.tenant_id)
        .all()
    )

    result = []
    for m in memberships:
        result.append(
            TenantMemberResponse(
                id=m.id,
                tenant_id=m.tenant_id,
                user_id=m.user_id,
                user_email=m.user.email,
                user_display_name=m.user.display_name,
                role=m.role,
                status=m.status,
                last_permission_change_at=m.last_permission_change_at,
                created_at=m.created_at,
            )
        )
    return result


@router.post("/{tenant_id}/members", response_model=TenantMemberResponse, status_code=status.HTTP_201_CREATED)
def assign_tenant_member(
    payload: MemberAssignRequest,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client admin endpoint to assign or invite a user into their tenant workspace.
    Enforces Permission Change Guard: updates last_permission_change_at.
    """
    target_email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == target_email).first()

    # If user doesn't exist, create them with provided password or temporary default
    if not user:
        display_name = payload.display_name or target_email.split("@")[0].title()
        raw_password = payload.password or "NexusTempPass123!"
        user = User(
            email=target_email,
            display_name=display_name,
            password_hash=hash_password(raw_password),
            platform_role="USER",
            status="ACTIVE",
        )
        db.add(user)
        db.flush()

    # Check if membership already exists in this tenant
    membership = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.user_id == user.id)
        .first()
    )

    now = datetime.now(timezone.utc)
    if membership:
        membership.role = payload.role
        membership.status = "ACTIVE"
        membership.last_permission_change_at = now
        action = "MEMBER_ROLE_UPDATE"
    else:
        membership = TenantMembership(
            tenant_id=ctx.tenant_id,
            user_id=user.id,
            role=payload.role,
            status="ACTIVE",
            last_permission_change_at=now,
        )
        db.add(membership)
        action = "MEMBER_ASSIGN"

    db.flush()

    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action=action,
        resource_type="TENANT_MEMBERSHIP",
        resource_id=membership.id,
        outcome="SUCCESS",
        metadata_json={"target_email": target_email, "role": payload.role},
    )
    db.add(audit)
    db.commit()
    db.refresh(membership)

    return TenantMemberResponse(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=user.id,
        user_email=user.email,
        user_display_name=user.display_name,
        role=membership.role,
        status=membership.status,
        last_permission_change_at=membership.last_permission_change_at,
        created_at=membership.created_at,
    )


@router.patch("/{tenant_id}/members/{user_id}", response_model=TenantMemberResponse)
def update_tenant_member(
    user_id: uuid.UUID,
    payload: MemberUpdateRequest,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to modify a member's role or status.
    Enforces real-time Permission Change Guard: updates last_permission_change_at timestamp.
    """
    membership = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise ResourceNotFoundError("Tenant membership not found.")

    now = datetime.now(timezone.utc)
    if payload.role:
        membership.role = payload.role
    if payload.status:
        membership.status = payload.status
    membership.last_permission_change_at = now

    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="MEMBER_PERMISSION_MODIFIED",
        resource_type="TENANT_MEMBERSHIP",
        resource_id=membership.id,
        outcome="SUCCESS",
        metadata_json={
            "target_user_id": str(user_id),
            "updated_role": membership.role,
            "updated_status": membership.status,
            "guard_timestamp": now.isoformat(),
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(membership)

    return TenantMemberResponse(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        user_email=membership.user.email,
        user_display_name=membership.user.display_name,
        role=membership.role,
        status=membership.status,
        last_permission_change_at=membership.last_permission_change_at,
        created_at=membership.created_at,
    )


@router.delete("/{tenant_id}/members/{user_id}")
def revoke_tenant_member(
    user_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to revoke employee workspace clearance immediately.
    Enforces real-time Permission Change Guard: status set to REVOKED, blocking immediate query access.
    """
    membership = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise ResourceNotFoundError("Tenant membership not found.")

    now = datetime.now(timezone.utc)
    membership.status = "REVOKED"
    membership.last_permission_change_at = now

    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="MEMBER_PERMISSION_REVOKED",
        resource_type="TENANT_MEMBERSHIP",
        resource_id=membership.id,
        outcome="SUCCESS",
        metadata_json={
            "target_user_id": str(user_id),
            "guard_timestamp": now.isoformat(),
        },
    )
    db.add(audit)
    db.commit()

    return {
        "status": "REVOKED",
        "message": f"User {membership.user.email} workspace access revoked. Permission Change Guard active.",
        "revoked_at": now.isoformat(),
    }


@router.get("/{tenant_id}/audit-events")
def list_tenant_audit_events(
    limit: int = 50,
    offset: int = 0,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to review tenant-scoped immutable audit log.
    Captures uploads, downloads, approvals, permission revocations, and configuration updates.
    """
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == ctx.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .offset(offset)
        .limit(min(limit, 100))
        .all()
    )
    return [
        {
            "id": str(e.id),
            "tenant_id": str(e.tenant_id),
            "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": str(e.resource_id) if e.resource_id else None,
            "outcome": e.outcome,
            "metadata": e.metadata_json or {},
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]

