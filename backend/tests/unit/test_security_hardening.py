"""Unit tests for Application & Infrastructure Security Hardening in NEXUS.

Tests verify:
1. File upload magic bytes validation and executable disguise prevention.
2. Path traversal filename rejection.
3. Security headers middleware injection (nosniff, DENY framing, CSP).
4. Production cryptographic secret validation in Settings.
5. Rate limiter sliding-window enforcement.
"""

import io
import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.config import Settings
from app.core.rate_limit import RateLimiterMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.main import app
from app.models import Tenant, User, TenantMembership
from app.core.security import hash_password, create_access_token


def test_production_secret_validation_rejects_insecure_keys():
    """Verify that NEXUS refuses to start in production if SECRET_KEY is too short or default."""
    # 1. Short secret
    with pytest.raises(ValidationError):
        Settings(NEXUS_ENV="production", SECRET_KEY="too-short")

    # 2. Known default secret
    with pytest.raises(ValidationError):
        Settings(
            NEXUS_ENV="production",
            SECRET_KEY="nexus-hackathon-super-secret-key-32bytes-minimum",
        )

    # 3. Strong secret succeeds
    valid_settings = Settings(
        NEXUS_ENV="production",
        SECRET_KEY="c84f59e9b0153381a179326e5e0cf792a7e780dc993218bf0a01a9fbf1a8d542",
    )
    assert valid_settings.NEXUS_ENV == "production"


def test_security_headers_middleware_injected(client: TestClient):
    """Verify standard OWASP and enterprise security headers on API responses."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert "strict-origin-when-cross-origin" in headers.get("Referrer-Policy", "")
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    assert "camera=()" in headers.get("Permissions-Policy", "")


def test_rate_limiter_middleware_enforcement():
    """Verify sliding-window rate limiter returns HTTP 429 when threshold exceeded."""
    test_app = FastAPI()
    # Configure with very tight limit of 3 requests/min for test
    test_app.add_middleware(
        RateLimiterMiddleware,
        requests_per_minute=3,
        burst_limit=3,
        exempt_testing=False,
    )

    @test_app.get("/test-endpoint")
    def sample():
        return {"ok": True}

    client = TestClient(test_app)

    # First 3 requests must succeed
    for _ in range(3):
        res = client.get("/test-endpoint")
        assert res.status_code == 200

    # 4th request must be rate limited
    res = client.get("/test-endpoint")
    assert res.status_code == 429
    data = res.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in res.headers


def test_upload_blocks_path_traversal_filenames(client: TestClient, db_session):
    """Verify that filenames containing directory traversal characters are rejected."""
    # Setup test tenant and admin user
    tenant = Tenant(name="Security Tenant", slug="sec-tenant")
    db_session.add(tenant)
    db_session.flush()

    user = User(
        email="secadmin@test.corp",
        password_hash=hash_password("Password123!"),
        display_name="Sec Admin",
        platform_role="USER",
    )
    db_session.add(user)
    db_session.flush()

    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="CLIENT_ADMIN")
    db_session.add(membership)
    db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        claims={"email": user.email, "platform_role": user.platform_role},
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Traversal with Unix slashes
    files = {"file": ("../../etc/passwd", io.BytesIO(b"%PDF-1.4 test document content"), "application/pdf")}
    data = {"title": "Traversal Attack 1"}
    res = client.post(f"/api/v1/tenants/{tenant.id}/documents", data=data, files=files, headers=headers)
    assert res.status_code == 400
    assert "PATH_TRAVERSAL" in res.text

    # 2. Traversal with Windows backslashes
    files = {"file": ("..\\..\\windows\\system32\\cmd.exe", io.BytesIO(b"%PDF-1.4 test document content"), "application/pdf")}
    data = {"title": "Traversal Attack 2"}
    res = client.post(f"/api/v1/tenants/{tenant.id}/documents", data=data, files=files, headers=headers)
    assert res.status_code == 400
    assert "PATH_TRAVERSAL" in res.text


def test_upload_magic_bytes_validation(client: TestClient, db_session):
    """Verify that magic byte headers are checked against declared extensions."""
    tenant = Tenant(name="Magic Byte Tenant", slug="magic-tenant")
    db_session.add(tenant)
    db_session.flush()

    user = User(
        email="magicadmin@test.corp",
        password_hash=hash_password("Password123!"),
        display_name="Magic Admin",
        platform_role="USER",
    )
    db_session.add(user)
    db_session.flush()

    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="CLIENT_ADMIN")
    db_session.add(membership)
    db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        claims={"email": user.email, "platform_role": user.platform_role},
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fake PDF (actually plain text or corrupt)
    fake_pdf = io.BytesIO(b"This is definitely not a PDF file structure.")
    res = client.post(
        f"/api/v1/tenants/{tenant.id}/documents",
        data={"title": "Corrupt PDF"},
        files={"file": ("fake.pdf", fake_pdf, "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 415
    assert "FILE_SIGNATURE_MISMATCH" in res.text

    # 2. Disguised Windows Executable (PE binary header MZ...) disguised as .txt
    disguised_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00")
    res = client.post(
        f"/api/v1/tenants/{tenant.id}/documents",
        data={"title": "Disguised Malware"},
        files={"file": ("malware.txt", disguised_exe, "text/plain")},
        headers=headers,
    )
    assert res.status_code == 415
    assert "MALICIOUS_PAYLOAD_DETECTED" in res.text

    # 3. Disguised Linux ELF binary header (\x7fELF) disguised as .txt
    disguised_elf = io.BytesIO(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00")
    res = client.post(
        f"/api/v1/tenants/{tenant.id}/documents",
        data={"title": "Disguised ELF"},
        files={"file": ("payload.txt", disguised_elf, "text/plain")},
        headers=headers,
    )
    assert res.status_code == 415
    assert "MALICIOUS_PAYLOAD_DETECTED" in res.text

    # 4. Legitimate text document succeeds
    valid_txt = io.BytesIO(b"NEXUS Employee Handbook: Section 1. All employees must follow security policies.")
    res = client.post(
        f"/api/v1/tenants/{tenant.id}/documents",
        data={"title": "Valid Policy Document"},
        files={"file": ("handbook.txt", valid_txt, "text/plain")},
        headers=headers,
    )
    assert res.status_code == 201
    assert "document_id" in res.json()

