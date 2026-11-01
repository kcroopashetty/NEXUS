"""Tests for Secure RAG, Evidence Passport, Knowledge Integrity Engine, and Query Trace."""

import io
import uuid
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Tenant, User, TenantMembership, Document, DocumentVersion
from app.core.security import hash_password
from app.services.ingestion.pipeline import ingestion_pipeline


def _seed_active_rag_tenants(client: TestClient, db_session: Session):
    password_hash = hash_password("SecretPass123!")

    # Tenant A
    t_a = Tenant(slug="tenant-a-rag", name="Tenant A RAG")
    u_admin_a = User(email="admin@rag-a.corp", display_name="Admin A", password_hash=password_hash)
    u_emp_a = User(email="emp@rag-a.corp", display_name="Emp A", password_hash=password_hash)

    # Tenant B
    t_b = Tenant(slug="tenant-b-rag", name="Tenant B RAG")
    u_admin_b = User(email="admin@rag-b.corp", display_name="Admin B", password_hash=password_hash)

    db_session.add_all([t_a, u_admin_a, u_emp_a, t_b, u_admin_b])
    db_session.commit()

    m_admin_a = TenantMembership(tenant_id=t_a.id, user_id=u_admin_a.id, role="CLIENT_ADMIN")
    m_emp_a = TenantMembership(tenant_id=t_a.id, user_id=u_emp_a.id, role="EMPLOYEE")
    m_admin_b = TenantMembership(tenant_id=t_b.id, user_id=u_admin_b.id, role="CLIENT_ADMIN")

    db_session.add_all([m_admin_a, m_emp_a, m_admin_b])
    db_session.commit()

    # Log in Admin A to upload document
    login_a = client.post("/api/v1/auth/login", json={"email": "admin@rag-a.corp", "password": "SecretPass123!"})
    token_a = login_a.json()["access_token"]

    sop_content = b"Clause 4.1: Customer complaints shall be resolved within 48 hours.\nClause 4.2: Escalations require director signoff."
    files = {"file": ("complaint_sop.txt", io.BytesIO(sop_content), "text/plain")}
    resp = client.post(
        f"/api/v1/tenants/{t_a.id}/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"title": "Complaint Handling SOP", "authority_level": "OFFICIAL_POLICY"},
        files=files,
    )
    doc_id = resp.json()["document_id"]
    ver_id = resp.json()["version_id"]

    # Activate version 1 in DB for RAG testing
    v1 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(ver_id)).first()
    v1.status = "ACTIVE"
    db_session.commit()

    return {
        "t_a": t_a,
        "u_emp_a": u_emp_a,
        "t_b": t_b,
        "u_admin_b": u_admin_b,
        "doc_id": doc_id,
        "ver_id": ver_id,
    }


def test_grounded_query_success(client: TestClient, db_session: Session):
    """Verify asking an answerable question against active document returns grounded answer & Evidence Passport."""
    data = _seed_active_rag_tenants(client, db_session)

    # Login as Employee A
    login_resp = client.post("/api/v1/auth/login", json={"email": "emp@rag-a.corp", "password": "SecretPass123!"})
    token = login_resp.json()["access_token"]
    tenant_id = data["t_a"].id

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/chat/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the resolution SLA for customer complaints?"},
    )
    assert resp.status_code == 200
    res = resp.json()

    assert res["status"] == "ANSWERED"
    assert "48 hours" in res["answer"]
    assert "evidence_passport" in res
    passport = res["evidence_passport"]
    assert passport["grounding_verified"] is True
    assert passport["grounding_score"] >= 0.50
    assert len(passport["claims"]) >= 1
    assert len(passport["evidence_items"]) >= 1
    assert passport["evidence_items"][0]["document_title"] == "Complaint Handling SOP"
    assert passport["evidence_items"][0]["page_start"] == 1


def test_unsupported_question_honest_refusal(client: TestClient, db_session: Session):
    """Verify an unsupported question receives an honest refusal."""
    data = _seed_active_rag_tenants(client, db_session)

    login_resp = client.post("/api/v1/auth/login", json={"email": "emp@rag-a.corp", "password": "SecretPass123!"})
    token = login_resp.json()["access_token"]
    tenant_id = data["t_a"].id

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/chat/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the reimbursement limit for company international flights?"},
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert "cannot answer" in res["answer"].lower()


def test_permission_guard_blocks_inactive_versions(client: TestClient, db_session: Session):
    """
    PERMISSION CHANGE GUARD TEST:
    A document version in REVIEW, SUPERSEDED, or FAILED status must NOT enter RAG context.
    """
    data = _seed_active_rag_tenants(client, db_session)
    tenant_id = data["t_a"].id

    # Demote v1 from ACTIVE to REVIEW (simulate unapproved candidate)
    v1 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(data["ver_id"])).first()
    v1.status = "REVIEW"
    db_session.commit()

    login_resp = client.post("/api/v1/auth/login", json={"email": "emp@rag-a.corp", "password": "SecretPass123!"})
    token = login_resp.json()["access_token"]

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/chat/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the resolution SLA for customer complaints?"},
    )
    assert resp.status_code == 200
    res = resp.json()
    # Since candidate is in REVIEW, PostgreSQL filter blocks it and system refuses
    assert res["status"] == "INSUFFICIENT_EVIDENCE"


def test_query_trace_diagnostics(client: TestClient, db_session: Session):
    """Verify Query Trace captures step-by-step latency and status."""
    data = _seed_active_rag_tenants(client, db_session)
    tenant_id = data["t_a"].id

    login_resp = client.post("/api/v1/auth/login", json={"email": "emp@rag-a.corp", "password": "SecretPass123!"})
    token = login_resp.json()["access_token"]

    q_resp = client.post(
        f"/api/v1/tenants/{tenant_id}/chat/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the resolution SLA?"},
    )
    query_id = q_resp.json()["query_id"]

    # Fetch Query Trace
    trace_resp = client.get(
        f"/api/v1/tenants/{tenant_id}/queries/{query_id}/trace",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert trace_resp.status_code == 200
    trace = trace_resp.json()
    assert trace["query_id"] == query_id
    assert len(trace["stages"]) >= 5
    stage_names = [s["stage"] for s in trace["stages"]]
    assert "AUTH_VERIFY" in stage_names
    assert ("PGVECTOR_CONSOLIDATED_RETRIEVAL" in stage_names) or ("VECTOR_SEARCH" in stage_names and "PERMISSION_GUARD" in stage_names)
    assert "INTEGRITY_CHECK" in stage_names
    assert "LLM_INFERENCE" in stage_names


def test_evidence_ledger_historical_lookup(client: TestClient, db_session: Session):
    """Verify querying /queries/{query_id} returns exact evidence snapshot."""
    data = _seed_active_rag_tenants(client, db_session)
    tenant_id = data["t_a"].id

    login_resp = client.post("/api/v1/auth/login", json={"email": "emp@rag-a.corp", "password": "SecretPass123!"})
    token = login_resp.json()["access_token"]

    q_resp = client.post(
        f"/api/v1/tenants/{tenant_id}/chat/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the resolution SLA?"},
    )
    query_id = q_resp.json()["query_id"]

    hist_resp = client.get(
        f"/api/v1/tenants/{tenant_id}/queries/{query_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert hist["query_id"] == query_id
    assert len(hist["evidence_passport"]["evidence_items"]) >= 1
    assert "Clause 4.1" in hist["evidence_passport"]["evidence_items"][0]["exact_passage"]

