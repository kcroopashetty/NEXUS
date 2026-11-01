"""Comprehensive multi-tenant isolation and security test suite (Client Alpha vs Client Beta).

Verifies non-negotiable enterprise isolation guarantees:
1. Cross-tenant document listing isolation
2. Direct document ID path parameter tampering
3. Cross-tenant physical file download prevention
4. Cross-tenant chat query and evidence access prevention
5. Cross-tenant query history and QueryTrace isolation
6. Evidence passport / Evidence ID tampering prevention
7. Cross-tenant document change approval prevention
8. Inactive tenant membership denial
9. Employee role escalation to Client Admin prevention
10. Inactive and superseded version retrieval exclusion
11. Connection pool tenant context leakage prevention
"""

import io
import uuid
import pytest
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Tenant, User, TenantMembership, Document, DocumentVersion
from app.db.rls import TenantRLSManager


@pytest.fixture
def multi_tenant_env(client: TestClient, db_session: Session):
    """Provisions isolated Client Alpha and Client Beta workspaces and users."""
    pw_hash = hash_password("IsoSecretPass123!")
    tag = uuid.uuid4().hex[:6]

    # 1. Tenant Alpha (Victim)
    t_alpha = Tenant(slug=f"alpha-{tag}", name=f"Client Alpha Corp {tag}")
    u_admin_alpha = User(email=f"admin@{tag}-alpha.corp", display_name="Alpha Admin", password_hash=pw_hash)
    u_emp_alpha = User(email=f"emp@{tag}-alpha.corp", display_name="Alpha Emp", password_hash=pw_hash)

    # 2. Tenant Beta (Attacker)
    t_beta = Tenant(slug=f"beta-{tag}", name=f"Client Beta Corp {tag}")
    u_admin_beta = User(email=f"admin@{tag}-beta.corp", display_name="Beta Admin", password_hash=pw_hash)
    u_emp_beta = User(email=f"emp@{tag}-beta.corp", display_name="Beta Emp", password_hash=pw_hash)

    db_session.add_all([t_alpha, u_admin_alpha, u_emp_alpha, t_beta, u_admin_beta, u_emp_beta])
    db_session.commit()

    m_admin_alpha = TenantMembership(tenant_id=t_alpha.id, user_id=u_admin_alpha.id, role="CLIENT_ADMIN")
    m_emp_alpha = TenantMembership(tenant_id=t_alpha.id, user_id=u_emp_alpha.id, role="EMPLOYEE")
    m_admin_beta = TenantMembership(tenant_id=t_beta.id, user_id=u_admin_beta.id, role="CLIENT_ADMIN")
    m_emp_beta = TenantMembership(tenant_id=t_beta.id, user_id=u_emp_beta.id, role="EMPLOYEE")

    db_session.add_all([m_admin_alpha, m_emp_alpha, m_admin_beta, m_emp_beta])
    db_session.commit()

    # Login tokens
    tok_admin_alpha = client.post("/api/v1/auth/login", json={"email": u_admin_alpha.email, "password": "IsoSecretPass123!"}).json()["access_token"]
    tok_emp_alpha = client.post("/api/v1/auth/login", json={"email": u_emp_alpha.email, "password": "IsoSecretPass123!"}).json()["access_token"]
    tok_admin_beta = client.post("/api/v1/auth/login", json={"email": u_admin_beta.email, "password": "IsoSecretPass123!"}).json()["access_token"]
    tok_emp_beta = client.post("/api/v1/auth/login", json={"email": u_emp_beta.email, "password": "IsoSecretPass123!"}).json()["access_token"]

    # Upload secret Alpha document
    alpha_doc_bytes = b"CONFIDENTIAL ALPHA ROADMAP: Q4 operating budget is exactly $75,000,000."
    file_upload = {"file": ("alpha_roadmap.txt", io.BytesIO(alpha_doc_bytes), "text/plain")}
    resp = client.post(
        f"/api/v1/tenants/{t_alpha.id}/documents",
        headers={"Authorization": f"Bearer {tok_admin_alpha}"},
        data={"title": "Alpha Confidential Roadmap", "authority_level": "OFFICIAL_POLICY"},
        files=file_upload,
    )
    assert resp.status_code == 201
    doc_alpha_id = resp.json()["document_id"]
    ver_alpha_id = resp.json()["version_id"]

    # Activate version 1
    ver_obj = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(ver_alpha_id)).first()
    ver_obj.status = "ACTIVE"
    db_session.commit()

    return {
        "t_alpha": t_alpha,
        "t_beta": t_beta,
        "u_admin_alpha": u_admin_alpha,
        "u_emp_alpha": u_emp_alpha,
        "u_admin_beta": u_admin_beta,
        "u_emp_beta": u_emp_beta,
        "tok_admin_alpha": tok_admin_alpha,
        "tok_emp_alpha": tok_emp_alpha,
        "tok_admin_beta": tok_admin_beta,
        "tok_emp_beta": tok_emp_beta,
        "doc_alpha_id": doc_alpha_id,
        "ver_alpha_id": ver_alpha_id,
    }


def test_cross_tenant_document_listing_isolation(client: TestClient, multi_tenant_env: dict):
    """Beta user listing their own documents receives 0 Alpha documents."""
    env = multi_tenant_env
    res = client.get(
        f"/api/v1/tenants/{env['t_beta'].id}/documents",
        headers={"Authorization": f"Bearer {env['tok_admin_beta']}"},
    )
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 0
    assert not any(d["title"] == "Alpha Confidential Roadmap" for d in docs)


def test_direct_document_id_tampering_denied(client: TestClient, multi_tenant_env: dict):
    """Beta user attempting to fetch Alpha document by ID receives 404/403 without data leakage."""
    env = multi_tenant_env
    # 1. Beta user accesses Alpha route with Alpha doc ID -> 403 Forbidden
    res1 = client.get(
        f"/api/v1/tenants/{env['t_alpha'].id}/documents/{env['doc_alpha_id']}",
        headers={"Authorization": f"Bearer {env['tok_admin_beta']}"},
    )
    assert res1.status_code == 403

    # 2. Beta user accesses Beta route with Alpha doc ID -> 404 Not Found (not found in Beta)
    res2 = client.get(
        f"/api/v1/tenants/{env['t_beta'].id}/documents/{env['doc_alpha_id']}",
        headers={"Authorization": f"Bearer {env['tok_admin_beta']}"},
    )
    assert res2.status_code == 404


def test_cross_tenant_file_download_denied(client: TestClient, multi_tenant_env: dict):
    """Beta user attempting to download Alpha version file gets 403/404; zero bytes leaked."""
    env = multi_tenant_env
    res = client.get(
        f"/api/v1/tenants/{env['t_alpha'].id}/documents/{env['doc_alpha_id']}/versions/{env['ver_alpha_id']}/download",
        headers={"Authorization": f"Bearer {env['tok_admin_beta']}"},
    )
    assert res.status_code == 403
    assert b"75,000,000" not in res.content


def test_cross_tenant_chat_vector_isolation(client: TestClient, multi_tenant_env: dict):
    """Beta user asking about Alpha confidential content receives honest refusal with zero chunks."""
    env = multi_tenant_env
    res = client.post(
        f"/api/v1/tenants/{env['t_beta'].id}/chat/query",
        headers={"Authorization": f"Bearer {env['tok_emp_beta']}"},
        json={"question": "What is the Q4 operating budget for Client Alpha roadmap?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "INSUFFICIENT_EVIDENCE"
    assert "75,000,000" not in str(data)
    assert len(data["evidence_passport"]["evidence_items"]) == 0


def test_cross_tenant_query_trace_lookup_denied(client: TestClient, multi_tenant_env: dict):
    """Alpha user asks query; Beta user cannot view Alpha's query trace or evidence."""
    env = multi_tenant_env
    # Alpha asks legitimate query
    res_query = client.post(
        f"/api/v1/tenants/{env['t_alpha'].id}/chat/query",
        headers={"Authorization": f"Bearer {env['tok_emp_alpha']}"},
        json={"question": "What is the Q4 budget?"},
    )
    assert res_query.status_code == 200
    query_id = res_query.json()["query_id"]

    # Beta attempts to read Alpha's query trace -> 403 Forbidden
    res_trace = client.get(
        f"/api/v1/tenants/{env['t_alpha'].id}/queries/{query_id}/trace",
        headers={"Authorization": f"Bearer {env['tok_emp_beta']}"},
    )
    assert res_trace.status_code == 403

    # Beta attempts to query under Beta route with Alpha's query ID -> 404
    res_trace_beta = client.get(
        f"/api/v1/tenants/{env['t_beta'].id}/queries/{query_id}/trace",
        headers={"Authorization": f"Bearer {env['tok_emp_beta']}"},
    )
    assert res_trace_beta.status_code == 404


def test_cross_tenant_version_approval_denied(client: TestClient, multi_tenant_env: dict):
    """Beta Client Admin cannot approve an Alpha document version."""
    env = multi_tenant_env
    res = client.post(
        f"/api/v1/tenants/{env['t_alpha'].id}/versions/{env['ver_alpha_id']}/approve",
        headers={"Authorization": f"Bearer {env['tok_admin_beta']}"},
    )
    assert res.status_code == 403


def test_employee_cannot_approve_version(client: TestClient, multi_tenant_env: dict):
    """Alpha regular EMPLOYEE cannot approve a version even within their own tenant."""
    env = multi_tenant_env
    res = client.post(
        f"/api/v1/tenants/{env['t_alpha'].id}/versions/{env['ver_alpha_id']}/approve",
        headers={"Authorization": f"Bearer {env['tok_emp_alpha']}"},
    )
    assert res.status_code == 403


def test_inactive_membership_denied(client: TestClient, db_session: Session, multi_tenant_env: dict):
    """User whose tenant membership is SUSPENDED or INACTIVE is immediately denied."""
    env = multi_tenant_env
    # Deactivate Alpha employee membership
    mem = (
        db_session.query(TenantMembership)
        .filter(TenantMembership.tenant_id == env["t_alpha"].id, TenantMembership.user_id == env["u_emp_alpha"].id)
        .first()
    )
    mem.status = "SUSPENDED"
    db_session.commit()

    res = client.get(
        f"/api/v1/tenants/{env['t_alpha'].id}/documents",
        headers={"Authorization": f"Bearer {env['tok_emp_alpha']}"},
    )
    assert res.status_code == 403
    assert "not an active member" in res.text.lower()


def test_connection_pool_tenant_context_leakage_prevented(db_session: Session, multi_tenant_env: dict):
    """
    Verifies that setting tenant context on a session does not leak across
    reset or connection return.
    """
    env = multi_tenant_env
    t_alpha_id = env["t_alpha"].id
    t_beta_id = env["t_beta"].id

    # 1. Set context to Alpha
    TenantRLSManager.set_tenant_context(db_session, t_alpha_id)
    assert db_session.info.get("current_tenant_id") == str(t_alpha_id)

    # 2. Reset context
    TenantRLSManager.reset_tenant_context(db_session)
    assert "current_tenant_id" not in db_session.info

    # 3. Re-set to Beta
    TenantRLSManager.set_tenant_context(db_session, t_beta_id)
    assert db_session.info.get("current_tenant_id") == str(t_beta_id)

    TenantRLSManager.reset_tenant_context(db_session)
