"""Tests for document upload, quarantine lifecycle, and tenant boundary enforcement."""

import io
import uuid
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Tenant, User, TenantMembership, Document, DocumentVersion
from app.core.security import hash_password


def _setup_tenants_and_users(db_session: Session):
    password_hash = hash_password("Password123!")

    # Tenant Alpha
    t_a = Tenant(slug="tenant-alpha", name="Tenant Alpha")
    u_admin_a = User(email="admin@alpha.corp", display_name="Admin Alpha", password_hash=password_hash)
    u_emp_a = User(email="emp@alpha.corp", display_name="Emp Alpha", password_hash=password_hash)

    # Tenant Beta
    t_b = Tenant(slug="tenant-beta", name="Tenant Beta")
    u_admin_b = User(email="admin@beta.corp", display_name="Admin Beta", password_hash=password_hash)

    db_session.add_all([t_a, u_admin_a, u_emp_a, t_b, u_admin_b])
    db_session.commit()

    m_admin_a = TenantMembership(tenant_id=t_a.id, user_id=u_admin_a.id, role="CLIENT_ADMIN")
    m_emp_a = TenantMembership(tenant_id=t_a.id, user_id=u_emp_a.id, role="EMPLOYEE")
    m_admin_b = TenantMembership(tenant_id=t_b.id, user_id=u_admin_b.id, role="CLIENT_ADMIN")

    db_session.add_all([m_admin_a, m_emp_a, m_admin_b])
    db_session.commit()

    return {
        "t_a": t_a,
        "u_admin_a": u_admin_a,
        "u_emp_a": u_emp_a,
        "t_b": t_b,
        "u_admin_b": u_admin_b,
    }


def test_upload_document_v1_success(client: TestClient, db_session: Session):
    """Verify Client Admin can upload a valid text/pdf document."""
    data = _setup_tenants_and_users(db_session)

    # Login as Admin A
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    tenant_id = data["t_a"].id

    file_content = b"This is synthetic complaint resolution SOP v1 with 48 hours SLA."
    files = {"file": ("complaint_sop_v1.txt", io.BytesIO(file_content), "text/plain")}
    data_form = {
        "title": "Customer Complaint Resolution SOP",
        "category": "Customer Support",
        "authority_level": "OFFICIAL_POLICY",
    }

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data=data_form,
        files=files,
    )
    assert resp.status_code == 201
    res = resp.json()
    assert res["version_number"] == 1
    assert res["status"] in ["UPLOADED", "REVIEW"]
    assert "document_id" in res


def test_employee_cannot_upload_document(client: TestClient, db_session: Session):
    """Verify standard EMPLOYEE is forbidden from uploading new documents."""
    data = _setup_tenants_and_users(db_session)

    # Login as Employee A
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "emp@alpha.corp", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    tenant_id = data["t_a"].id

    files = {"file": ("unauth.txt", io.BytesIO(b"Employee upload"), "text/plain")}
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Unauthorized Document"},
        files=files,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_upload_candidate_version_v2(client: TestClient, db_session: Session):
    """Verify uploading a candidate version increments version number to 2."""
    data = _setup_tenants_and_users(db_session)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    tenant_id = data["t_a"].id

    # 1. Upload v1
    files_v1 = {"file": ("sop_v1.txt", io.BytesIO(b"Clause 1: 48 hours"), "text/plain")}
    resp1 = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "SOP Document"},
        files=files_v1,
    )
    doc_id = resp1.json()["document_id"]

    # 2. Upload v2 candidate for same document
    files_v2 = {"file": ("sop_v2.txt", io.BytesIO(b"Clause 1: 24 hours"), "text/plain")}
    resp2 = client.post(
        f"/api/v1/tenants/{tenant_id}/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {token}"},
        files=files_v2,
    )
    assert resp2.status_code == 201
    res2 = resp2.json()
    assert res2["version_number"] == 2
    assert res2["document_id"] == doc_id


def test_unsupported_file_extension_rejected(client: TestClient, db_session: Session):
    """ATTACK TEST: Attempting to upload an unsupported executable or script is rejected."""
    data = _setup_tenants_and_users(db_session)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    tenant_id = data["t_a"].id

    files = {"file": ("malware.exe", io.BytesIO(b"MZ..."), "application/x-msdownload")}
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Exploit Attempt"},
        files=files,
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_cross_tenant_document_download_denied(client: TestClient, db_session: Session):
    """
    ATTACK TEST: User in Tenant B attempts to download a document from Tenant A.
    Must be blocked by tenant authorization.
    """
    data = _setup_tenants_and_users(db_session)

    # 1. Admin A uploads a document to Tenant A
    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    token_a = login_a.json()["access_token"]
    tenant_a_id = data["t_a"].id

    files_a = {"file": ("secret_alpha.txt", io.BytesIO(b"Alpha Confidential Data"), "text/plain")}
    resp_upload = client.post(
        f"/api/v1/tenants/{tenant_a_id}/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"title": "Alpha Confidential Document"},
        files=files_a,
    )
    doc_id = resp_upload.json()["document_id"]
    ver_id = resp_upload.json()["version_id"]

    # 2. Admin B (from Tenant B) attempts to download this document using Tenant A's route
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@beta.corp", "password": "Password123!"},
    )
    token_b = login_b.json()["access_token"]

    cross_resp = client.get(
        f"/api/v1/tenants/{tenant_a_id}/documents/{doc_id}/versions/{ver_id}/download",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_resp.status_code == 403
    assert cross_resp.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    # 3. Admin B attempts to spoof tenant route by passing Tenant B ID with Tenant A's document UUID
    tenant_b_id = data["t_b"].id
    spoof_resp = client.get(
        f"/api/v1/tenants/{tenant_b_id}/documents/{doc_id}/versions/{ver_id}/download",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert spoof_resp.status_code == 404
    assert spoof_resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_delete_document_client_admin_success(client: TestClient, db_session: Session):
    """Verify Client Admin can successfully delete a policy document and its versions."""
    data = _setup_tenants_and_users(db_session)
    tenant_id = data["t_a"].id

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # 1. Upload a policy document
    files = {"file": ("policy_to_delete.txt", io.BytesIO(b"Temporary policy clause."), "text/plain")}
    resp_upload = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Policy Document To Delete"},
        files=files,
    )
    assert resp_upload.status_code == 201
    doc_id = resp_upload.json()["document_id"]

    # 2. Delete the policy document as Client Admin
    del_resp = client.delete(
        f"/api/v1/tenants/{tenant_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"
    assert "deleted" in del_resp.json()["message"]

    # 3. Verify document no longer exists
    get_resp = client.get(
        f"/api/v1/tenants/{tenant_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_delete_document_forbidden_for_regular_employee(client: TestClient, db_session: Session):
    """Verify regular employees (MEMBER/EMPLOYEE role) cannot delete policy documents."""
    data = _setup_tenants_and_users(db_session)
    tenant_id = data["t_a"].id

    # Admin uploads document
    login_admin = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    admin_token = login_admin.json()["access_token"]
    files = {"file": ("protected_policy.txt", io.BytesIO(b"Critical security policy."), "text/plain")}
    resp_upload = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"title": "Protected Company Policy"},
        files=files,
    )
    doc_id = resp_upload.json()["document_id"]

    # Regular employee logs in
    login_emp = client.post(
        "/api/v1/auth/login",
        json={"email": "emp@alpha.corp", "password": "Password123!"},
    )
    emp_token = login_emp.json()["access_token"]

    # Regular employee attempts to delete document
    del_resp = client.delete(
        f"/api/v1/tenants/{tenant_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert del_resp.status_code == 403
    assert del_resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # Confirm document still exists
    get_resp = client.get(
        f"/api/v1/tenants/{tenant_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_resp.status_code == 200


def test_delete_document_cross_tenant_denied(client: TestClient, db_session: Session):
    """Verify cross-tenant document deletion is strictly blocked."""
    data = _setup_tenants_and_users(db_session)
    tenant_a_id = data["t_a"].id
    tenant_b_id = data["t_b"].id

    # Admin A uploads document to Tenant A
    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.corp", "password": "Password123!"},
    )
    token_a = login_a.json()["access_token"]
    files = {"file": ("alpha_doc.txt", io.BytesIO(b"Alpha proprietary document."), "text/plain")}
    resp_upload = client.post(
        f"/api/v1/tenants/{tenant_a_id}/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"title": "Alpha Proprietary Document"},
        files=files,
    )
    doc_id = resp_upload.json()["document_id"]

    # Admin B attempts to delete Admin A's document via Tenant B path
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@beta.corp", "password": "Password123!"},
    )
    token_b = login_b.json()["access_token"]

    del_spoof_resp = client.delete(
        f"/api/v1/tenants/{tenant_b_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_spoof_resp.status_code == 404

    # Admin B attempts to delete via Tenant A path directly
    del_direct_resp = client.delete(
        f"/api/v1/tenants/{tenant_a_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_direct_resp.status_code == 403
    assert del_direct_resp.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

