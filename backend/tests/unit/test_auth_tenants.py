"""Tests for authentication, tenant isolation, and Permission Change Guard."""

import uuid
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Tenant, User, TenantMembership
from app.core.security import hash_password


def _setup_test_tenants_and_users(db_session: Session):
    """Seed two isolated tenants and users for testing."""
    password_hash = hash_password("ValidPassword123!")

    # Platform Admin
    p_admin = User(
        email="root@nexus.corp",
        display_name="Root Admin",
        password_hash=password_hash,
        platform_role="PLATFORM_ADMIN",
    )

    # Tenant Alpha
    t_a = Tenant(slug="tenant-a", name="Tenant Alpha")
    u_admin_a = User(email="admin_a@alpha.com", display_name="Admin A", password_hash=password_hash)
    u_emp_a = User(email="emp_a@alpha.com", display_name="Emp A", password_hash=password_hash)

    # Tenant Beta
    t_b = Tenant(slug="tenant-b", name="Tenant Beta")
    u_admin_b = User(email="admin_b@beta.com", display_name="Admin B", password_hash=password_hash)

    db_session.add_all([p_admin, t_a, u_admin_a, u_emp_a, t_b, u_admin_b])
    db_session.commit()

    # Memberships
    m_admin_a = TenantMembership(tenant_id=t_a.id, user_id=u_admin_a.id, role="CLIENT_ADMIN")
    m_emp_a = TenantMembership(tenant_id=t_a.id, user_id=u_emp_a.id, role="EMPLOYEE")
    m_admin_b = TenantMembership(tenant_id=t_b.id, user_id=u_admin_b.id, role="CLIENT_ADMIN")

    db_session.add_all([m_admin_a, m_emp_a, m_admin_b])
    db_session.commit()

    return {
        "p_admin": p_admin,
        "t_a": t_a,
        "u_admin_a": u_admin_a,
        "u_emp_a": u_emp_a,
        "t_b": t_b,
        "u_admin_b": u_admin_b,
        "m_emp_a": m_emp_a,
    }


def test_login_success(client: TestClient, db_session: Session):
    """Verify login returns token and user memberships."""
    data = _setup_test_tenants_and_users(db_session)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin_a@alpha.com", "password": "ValidPassword123!"},
    )
    assert response.status_code == 200
    res = response.json()
    assert "access_token" in res
    assert res["user"]["email"] == "admin_a@alpha.com"
    assert len(res["user"]["memberships"]) == 1
    assert res["user"]["memberships"][0]["tenant_slug"] == "tenant-a"
    assert res["user"]["memberships"][0]["role"] == "CLIENT_ADMIN"


def test_login_invalid_password(client: TestClient, db_session: Session):
    """Verify login with bad credentials returns 401 with generic message."""
    _setup_test_tenants_and_users(db_session)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin_a@alpha.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    res = response.json()
    assert res["error"]["code"] == "AUTHENTICATION_FAILED"


def test_platform_admin_can_create_tenant(client: TestClient, db_session: Session):
    """Verify only PLATFORM_ADMIN can create a tenant."""
    data = _setup_test_tenants_and_users(db_session)

    # Login as platform admin
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "root@nexus.corp", "password": "ValidPassword123!"},
    )
    token = login_resp.json()["access_token"]

    # Create new workspace
    create_resp = client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "tenant-new", "name": "New Enterprise Workspace"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["slug"] == "tenant-new"


def test_regular_user_cannot_create_tenant(client: TestClient, db_session: Session):
    """Verify client admin or employee cannot create a new tenant (denied)."""
    data = _setup_test_tenants_and_users(db_session)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin_a@alpha.com", "password": "ValidPassword123!"},
    )
    token = login_resp.json()["access_token"]

    create_resp = client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "tenant-hacked", "name": "Unauthorized Workspace"},
    )
    assert create_resp.status_code == 403
    assert create_resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_cross_tenant_member_access_denied(client: TestClient, db_session: Session):
    """
    ATTACK TEST: Client admin of Tenant A attempts to list or add members in Tenant B.
    Must be rejected with 403 TENANT_ACCESS_DENIED.
    """
    data = _setup_test_tenants_and_users(db_session)

    # Login as Admin of Tenant A
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin_a@alpha.com", "password": "ValidPassword123!"},
    )
    token = login_resp.json()["access_token"]
    tenant_b_id = data["t_b"].id

    # Attempt to list members of Tenant B
    list_resp = client.get(
        f"/api/v1/tenants/{tenant_b_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 403
    assert list_resp.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    # Attempt to add a member to Tenant B
    add_resp = client.post(
        f"/api/v1/tenants/{tenant_b_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "spy@alpha.com", "role": "CLIENT_ADMIN"},
    )
    assert add_resp.status_code == 403
    assert add_resp.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


def test_permission_change_guard_immediate_revocation(client: TestClient, db_session: Session):
    """
    PERMISSION CHANGE GUARD TEST:
    Employee A logs in and has access to Tenant A.
    Admin suspends Employee A's membership in PostgreSQL.
    Next request by Employee A to Tenant A must be immediately rejected (403).
    """
    data = _setup_test_tenants_and_users(db_session)

    # 1. Employee A logs in
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "emp_a@alpha.com", "password": "ValidPassword123!"},
    )
    token = login_resp.json()["access_token"]
    tenant_a_id = data["t_a"].id

    # 2. Employee accesses my tenants
    t_resp = client.get("/api/v1/tenants", headers={"Authorization": f"Bearer {token}"})
    assert t_resp.status_code == 200
    assert len(t_resp.json()) == 1

    # 3. Simulate administrator revoking/suspending Employee A's membership in DB
    membership = data["m_emp_a"]
    membership.status = "SUSPENDED"
    db_session.commit()

    # 4. Immediate subsequent request for Tenant A resources is denied by Permission Change Guard
    subsequent_resp = client.get(
        f"/api/v1/tenants/{tenant_a_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert subsequent_resp.status_code == 403
