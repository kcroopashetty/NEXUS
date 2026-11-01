"""Tests for database models, constraints, and relationships."""

import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Tenant,
    User,
    TenantMembership,
    Document,
    DocumentVersion,
    ProcessingJob,
    DocumentPage,
    DocumentChunk,
    DocumentChange,
    DocumentChangeItem,
    DocumentImpactSuggestion,
    QueryEvent,
    QueryEvidence,
    AuditEvent,
    SecurityEvent,
    SecurityTestRun,
    SecurityTestResult,
)
from app.core.security import hash_password


def test_tenant_and_user_creation(db_session: Session):
    """Test creating tenants, users, and memberships."""
    tenant = Tenant(slug="acme-corp", name="Acme Corporation")
    user = User(
        email="alice@acme.com",
        display_name="Alice Smith",
        password_hash=hash_password("SuperSecure123!"),
        platform_role="USER",
    )
    db_session.add_all([tenant, user])
    db_session.commit()

    assert tenant.id is not None
    assert user.id is not None

    # Add membership
    membership = TenantMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        role="CLIENT_ADMIN",
    )
    db_session.add(membership)
    db_session.commit()

    assert membership.id is not None
    assert membership.last_permission_change_at is not None
    assert len(tenant.memberships) == 1
    assert tenant.memberships[0].role == "CLIENT_ADMIN"


def test_duplicate_membership_rejected(db_session: Session):
    """Verify unique constraint on (tenant_id, user_id)."""
    tenant = Tenant(slug="beta-corp", name="Beta Corp")
    user = User(
        email="bob@beta.com",
        display_name="Bob Jones",
        password_hash=hash_password("Password123!"),
    )
    db_session.add_all([tenant, user])
    db_session.commit()

    m1 = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="EMPLOYEE")
    db_session.add(m1)
    db_session.commit()

    m2 = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="CLIENT_ADMIN")
    db_session.add(m2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_document_and_version_lifecycle(db_session: Session):
    """Test creating documents, versions, pages, chunks, and jobs."""
    tenant = Tenant(slug="gamma-corp", name="Gamma Corp")
    user = User(email="carol@gamma.com", display_name="Carol", password_hash="hash")
    db_session.add_all([tenant, user])
    db_session.commit()

    # Create document
    doc = Document(
        tenant_id=tenant.id,
        title="Leave Policy",
        authority_level="OFFICIAL_POLICY",
        created_by=user.id,
    )
    db_session.add(doc)
    db_session.commit()

    # Create version 1
    v1 = DocumentVersion(
        tenant_id=tenant.id,
        document_id=doc.id,
        version_number=1,
        original_filename="leave_v1.pdf",
        storage_key=f"tenants/{tenant.id}/documents/{doc.id}/v1/original",
        sha256="a" * 64,
        mime_type="application/pdf",
        file_size_bytes=1024,
        status="ACTIVE",
        uploaded_by=user.id,
        quality_score=0.95,
        ocr_needed=False,
    )
    db_session.add(v1)
    db_session.commit()

    # Add page
    page = DocumentPage(
        tenant_id=tenant.id,
        version_id=v1.id,
        page_number=1,
        extracted_text="Employees receive 18 days of annual leave.",
        text_sha256="b" * 64,
    )
    # Add chunk
    chunk = DocumentChunk(
        tenant_id=tenant.id,
        version_id=v1.id,
        chunk_index=0,
        page_start=1,
        page_end=1,
        section_heading="Annual Leave",
        chunk_text="Employees receive 18 days of annual leave.",
        text_sha256="b" * 64,
        embedding_model="all-MiniLM-L6-v2",
        vector_id=f"chunk_{v1.id}_0",
        allowed_roles="EMPLOYEE,CLIENT_ADMIN",
        classification="INTERNAL",
    )
    # Add processing job
    job = ProcessingJob(
        tenant_id=tenant.id,
        version_id=v1.id,
        status="SUCCEEDED",
        stage="COMPLETED",
    )
    db_session.add_all([page, chunk, job])
    db_session.commit()

    assert len(v1.pages) == 1
    assert len(v1.chunks) == 1
    assert len(v1.jobs) == 1


def test_evidence_ledger_and_query_events(db_session: Session):
    """Test persisting query events with Query Trace and Evidence Passport provenance."""
    tenant = Tenant(slug="delta-corp", name="Delta Corp")
    user = User(email="dave@delta.com", display_name="Dave", password_hash="hash")
    db_session.add_all([tenant, user])
    db_session.commit()

    doc = Document(tenant_id=tenant.id, title="SLA Document", created_by=user.id)
    db_session.add(doc)
    db_session.commit()

    version = DocumentVersion(
        tenant_id=tenant.id,
        document_id=doc.id,
        version_number=1,
        original_filename="sla.pdf",
        storage_key="storage_key_delta",
        sha256="c" * 64,
        mime_type="application/pdf",
        file_size_bytes=2048,
        status="ACTIVE",
        uploaded_by=user.id,
    )
    db_session.add(version)
    db_session.commit()

    # Log QueryEvent with Query Trace stages
    query = QueryEvent(
        tenant_id=tenant.id,
        user_id=user.id,
        question_text="What is the complaint resolution SLA?",
        answer_text="The complaint resolution SLA is 48 hours.",
        status="ANSWERED",
        grounding_verified=True,
        grounding_score=0.98,
        trace_stages=[
            {"stage": "AUTH_VERIFY", "duration_ms": 2, "status": "PASSED"},
            {"stage": "VECTOR_SEARCH", "duration_ms": 15, "status": "PASSED"},
            {"stage": "PERMISSION_GUARD", "duration_ms": 3, "status": "PASSED"},
            {"stage": "LLM_INFERENCE", "duration_ms": 120, "status": "PASSED"},
        ],
        latency_ms=140,
    )
    db_session.add(query)
    db_session.commit()

    # Add QueryEvidence snapshot
    evidence = QueryEvidence(
        tenant_id=tenant.id,
        query_id=query.id,
        version_id=version.id,
        page_start=1,
        page_end=1,
        claim_text="Complaint resolution SLA is 48 hours.",
        claim_supported=True,
        evidence_text_snapshot="Clause 4.1: Customer complaints shall be resolved within 48 hours.",
        content_sha256="d" * 64,
        retrieval_rank=1,
        retrieval_score=0.89,
    )
    db_session.add(evidence)
    db_session.commit()

    assert len(query.evidence_items) == 1
    assert query.evidence_items[0].claim_supported is True
    assert query.evidence_items[0].version_id == version.id

