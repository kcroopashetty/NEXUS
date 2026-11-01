"""Tests for Vertical Slice 6: Knowledge Change Intelligence (Version Diff & Human Approval)."""

import io
import uuid
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Tenant, User, TenantMembership, Document, DocumentVersion
from app.core.security import hash_password


def _setup_diff_test_workspace(client: TestClient, db_session: Session):
    pw = hash_password("DiffPass123!")
    t = Tenant(slug="diff-tenant", name="Diff Tenant Corp")
    u_admin = User(email="admin@diff.corp", display_name="Admin Diff", password_hash=pw)
    u_emp = User(email="emp@diff.corp", display_name="Emp Diff", password_hash=pw)

    db_session.add_all([t, u_admin, u_emp])
    db_session.commit()

    m_admin = TenantMembership(tenant_id=t.id, user_id=u_admin.id, role="CLIENT_ADMIN")
    m_emp = TenantMembership(tenant_id=t.id, user_id=u_emp.id, role="EMPLOYEE")
    db_session.add_all([m_admin, m_emp])
    db_session.commit()

    login_admin = client.post("/api/v1/auth/login", json={"email": "admin@diff.corp", "password": "DiffPass123!"})
    tok_admin = login_admin.json()["access_token"]

    login_emp = client.post("/api/v1/auth/login", json={"email": "emp@diff.corp", "password": "DiffPass123!"})
    tok_emp = login_emp.json()["access_token"]

    # Upload Version 1
    v1_content = (
        b"Clause 1.1: Standard refund requests shall be processed within 48 hours.\n"
        b"Clause 1.2: Director signoff is required for claims over $10,000 USD."
    )
    res_v1 = client.post(
        f"/api/v1/tenants/{t.id}/documents",
        headers={"Authorization": f"Bearer {tok_admin}"},
        data={"title": "Refund and Claims Policy", "authority_level": "OFFICIAL_POLICY"},
        files={"file": ("refund_v1.txt", io.BytesIO(v1_content), "text/plain")},
    )
    doc_id = res_v1.json()["document_id"]
    ver1_id = res_v1.json()["version_id"]

    # Approve v1 directly so it is ACTIVE
    client.post(
        f"/api/v1/tenants/{t.id}/versions/{ver1_id}/approve",
        headers={"Authorization": f"Bearer {tok_admin}"},
    )

    # Upload Version 2 (candidate in REVIEW)
    v2_content = (
        b"Clause 1.1: Standard refund requests shall be processed within 24 hours.\n"
        b"Clause 1.2: Director signoff is required for claims over $10,000 USD.\n"
        b"Clause 1.3: Expedited processing fee is $50 USD."
    )
    res_v2 = client.post(
        f"/api/v1/tenants/{t.id}/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {tok_admin}"},
        files={"file": ("refund_v2.txt", io.BytesIO(v2_content), "text/plain")},
    )
    ver2_id = res_v2.json()["version_id"]

    return {
        "tenant_id": t.id,
        "doc_id": doc_id,
        "ver1_id": ver1_id,
        "ver2_id": ver2_id,
        "tok_admin": tok_admin,
        "tok_emp": tok_emp,
    }


def test_compute_version_diff(client: TestClient, db_session: Session):
    """Verify deterministic version diff detects modifications and additions."""
    data = _setup_diff_test_workspace(client, db_session)

    res = client.get(
        f"/api/v1/tenants/{data['tenant_id']}/documents/{data['doc_id']}/changes",
        headers={"Authorization": f"Bearer {data['tok_admin']}"},
    )
    assert res.status_code == 200
    diff = res.json()

    assert diff["status"] == "PENDING_REVIEW"
    assert "v1 -> v2" in diff["summary"]

    # Verify change items
    items = diff["items"]
    assert len(items) >= 2

    # Check for modification of Clause 1.1 (48 hours -> 24 hours)
    modifications = [it for it in items if it["change_type"] == "MODIFICATION"]
    assert len(modifications) >= 1
    mod = modifications[0]
    assert "48 hours" in mod["old_text"]
    assert "24 hours" in mod["new_text"]
    assert mod["classification"] == "SLA"

    # Check for addition of Clause 1.3
    additions = [it for it in items if it["change_type"] == "ADDITION"]
    assert len(additions) >= 1
    add = additions[0]
    assert "Expedited processing fee" in add["new_text"]
    assert add["classification"] == "FINANCIAL"


def test_employee_cannot_approve_or_reject_version(client: TestClient, db_session: Session):
    """Verify regular EMPLOYEE is forbidden from approving or rejecting candidate versions."""
    data = _setup_diff_test_workspace(client, db_session)

    # Employee tries to approve
    resp_approve = client.post(
        f"/api/v1/tenants/{data['tenant_id']}/versions/{data['ver2_id']}/approve",
        headers={"Authorization": f"Bearer {data['tok_emp']}"},
    )
    assert resp_approve.status_code == 403

    # Employee tries to reject
    resp_reject = client.post(
        f"/api/v1/tenants/{data['tenant_id']}/versions/{data['ver2_id']}/reject",
        headers={"Authorization": f"Bearer {data['tok_emp']}"},
    )
    assert resp_reject.status_code == 403


def test_atomic_approval_transitions_versions_and_updates_rag(client: TestClient, db_session: Session):
    """
    KNOWLEDGE CHANGE INTELLIGENCE + PERMISSION GUARD TEST:
    1. Before approval: RAG answers with v1 (48 hours).
    2. Admin approves candidate v2.
    3. v1 is demoted to SUPERSEDED; v2 is promoted to ACTIVE.
    4. At most one ACTIVE version exists for the document.
    5. After approval: RAG answers with v2 (24 hours).
    """
    data = _setup_diff_test_workspace(client, db_session)

    # 1. Before approval: query SLA
    q1 = client.post(
        f"/api/v1/tenants/{data['tenant_id']}/chat/query",
        headers={"Authorization": f"Bearer {data['tok_emp']}"},
        json={"question": "What is the refund processing turnaround time?"},
    )
    assert q1.status_code == 200
    assert "48 hours" in q1.json()["answer"]

    # 2. Client Admin approves v2
    appr_res = client.post(
        f"/api/v1/tenants/{data['tenant_id']}/versions/{data['ver2_id']}/approve",
        headers={"Authorization": f"Bearer {data['tok_admin']}"},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"
    assert data["ver1_id"] in appr_res.json()["superseded_versions"]

    # 3. Verify DB state: v1 is SUPERSEDED, v2 is ACTIVE
    v1 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(data["ver1_id"])).first()
    v2 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(data["ver2_id"])).first()
    assert v1.status == "SUPERSEDED"
    assert v2.status == "ACTIVE"

    # Verify only 1 active version exists
    actives = (
        db_session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == uuid.UUID(data["doc_id"]), DocumentVersion.status == "ACTIVE")
        .all()
    )
    assert len(actives) == 1

    # 4. After approval: query SLA now reflects v2 (24 hours)
    q2 = client.post(
        f"/api/v1/tenants/{data['tenant_id']}/chat/query",
        headers={"Authorization": f"Bearer {data['tok_emp']}"},
        json={"question": "What is the refund processing turnaround time?"},
    )
    assert q2.status_code == 200
    assert "24 hours" in q2.json()["answer"]


def test_reject_candidate_version(client: TestClient, db_session: Session):
    """Verify rejection sets status to FAILED and leaves previous ACTIVE version active."""
    data = _setup_diff_test_workspace(client, db_session)

    rej_res = client.post(
        f"/api/v1/tenants/{data['tenant_id']}/versions/{data['ver2_id']}/reject",
        headers={"Authorization": f"Bearer {data['tok_admin']}"},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"

    v2 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(data["ver2_id"])).first()
    assert v2.status == "FAILED"

    v1 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(data["ver1_id"])).first()
    assert v1.status == "ACTIVE"

