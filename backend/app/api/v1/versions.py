"""Document version review, atomic approval, and rejection endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError, ValidationPayloadError
from app.db.session import get_db
from app.models import Document, DocumentVersion, DocumentChange, AuditEvent
from app.services.authorization.context import (
    require_client_admin_context,
    AuthorizedTenantContext,
)

logger = logging.getLogger("nexus.versions")

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/versions", tags=["Document Versions"])


@router.post("/{version_id}/approve")
def approve_version(
    version_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to approve a candidate document version.
    Executes an atomic transaction with row locking:
      1. Locks Document row.
      2. Demotes any existing ACTIVE version to SUPERSEDED.
      3. Promotes candidate version to ACTIVE.
      4. Marks associated DocumentChange as APPROVED.
      5. Records audit event and commits.
    Enforces partial unique index: at most one ACTIVE version per document.
    """
    version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.id == version_id, DocumentVersion.tenant_id == ctx.tenant_id)
        .first()
    )
    if not version:
        raise ResourceNotFoundError("Document version not found.")

    if version.status == "ACTIVE":
        return {
            "status": "ALREADY_ACTIVE",
            "message": "This version is already active.",
            "version_id": str(version.id),
            "document_id": str(version.document_id),
            "version_number": version.version_number,
        }

    if version.status not in ("REVIEW", "UPLOADED"):
        raise ValidationPayloadError(
            f"Cannot approve version in status '{version.status}'. Version must be in 'REVIEW'."
        )

    # 1. Row-level lock on the parent Document
    doc = (
        db.query(Document)
        .filter(Document.id == version.document_id, Document.tenant_id == ctx.tenant_id)
        .with_for_update()
        .first()
    )
    if not doc:
        raise ResourceNotFoundError("Parent document not found.")

    # 2. Find and demote existing ACTIVE versions
    prior_actives = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.tenant_id == ctx.tenant_id,
            DocumentVersion.document_id == doc.id,
            DocumentVersion.status == "ACTIVE",
        )
        .all()
    )
    superseded_ids = []
    for pv in prior_actives:
        pv.status = "SUPERSEDED"
        superseded_ids.append(str(pv.id))
    db.flush()

    # 3. Promote candidate version
    version.status = "ACTIVE"
    db.flush()

    # 4. Update DocumentChange status if present
    change = (
        db.query(DocumentChange)
        .filter(
            DocumentChange.tenant_id == ctx.tenant_id,
            DocumentChange.to_version_id == version.id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if change:
        change.status = "APPROVED"
        change.reviewed_by = ctx.user_id
        change.reviewed_at = now

    # 5. Record Audit Event
    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_VERSION_APPROVED",
        resource_type="DOCUMENT_VERSION",
        resource_id=version.id,
        outcome="SUCCESS",
        metadata_json={
            "document_id": str(doc.id),
            "version_number": version.version_number,
            "superseded_versions": superseded_ids,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(version)

    logger.info(
        "Version approved: doc=%s v=%s superseded=%s by user=%s",
        doc.id,
        version.version_number,
        superseded_ids,
        ctx.user_id,
    )

    return {
        "status": "APPROVED",
        "message": f"Version {version.version_number} is now ACTIVE.",
        "version_id": str(version.id),
        "document_id": str(doc.id),
        "version_number": version.version_number,
        "superseded_versions": superseded_ids,
    }


@router.post("/{version_id}/reject")
def reject_version(
    version_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to reject a candidate version in REVIEW.
    Transitions version to FAILED; previous ACTIVE version remains undisturbed.
    """
    version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.id == version_id, DocumentVersion.tenant_id == ctx.tenant_id)
        .first()
    )
    if not version:
        raise ResourceNotFoundError("Document version not found.")

    if version.status == "ACTIVE":
        raise ValidationPayloadError("Cannot reject an ACTIVE version.")

    version.status = "FAILED"
    version.error_code = "ADMIN_REJECTED"
    version.error_message = "Candidate version rejected by client administrator during human review."

    # Update DocumentChange
    change = (
        db.query(DocumentChange)
        .filter(
            DocumentChange.tenant_id == ctx.tenant_id,
            DocumentChange.to_version_id == version.id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if change:
        change.status = "REJECTED"
        change.reviewed_by = ctx.user_id
        change.reviewed_at = now

    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_VERSION_REJECTED",
        resource_type="DOCUMENT_VERSION",
        resource_id=version.id,
        outcome="SUCCESS",
        metadata_json={
            "document_id": str(version.document_id),
            "version_number": version.version_number,
        },
    )
    db.add(audit)
    db.commit()

    return {
        "status": "REJECTED",
        "message": f"Version {version.version_number} has been rejected.",
        "version_id": str(version.id),
        "document_id": str(version.document_id),
        "version_number": version.version_number,
    }
