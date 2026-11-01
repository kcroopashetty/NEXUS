"""Tests for Vertical Slice 7: Red-Team Sentinel Automated Security Test Suite."""

from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.core.security import hash_password
from app.services.security.sentinel import SentinelRunner


def test_sentinel_runner_all_attacks_pass(client: TestClient, db_session: Session):
    """
    Direct invocation of the Sentinel security runner.
    Verifies that all 7 adversarial checks (path tampering, file leak, vector leak,
    prompt injection, inactive chunk exclusion, role escalation, bad extension) PASS.
    """
    runner = SentinelRunner(db=db_session, client=client)
    run = runner.run_suite()

    assert run.status == "PASSED"
    assert run.summary_json["total_tests"] == 8
    assert run.summary_json["passed_tests"] == 8
    assert run.summary_json["failed_tests"] == 0
    assert run.summary_json["pass_rate_percent"] == 100.0


def test_sentinel_api_endpoints(client: TestClient, db_session: Session):
    """Verify Platform Admin can trigger and review Sentinel runs via the REST API."""
    pw_hash = hash_password("SentinelAdmin123!")
    admin = User(
        email="sentinel_admin@platform.corp",
        display_name="Sentinel Admin",
        password_hash=pw_hash,
        platform_role="PLATFORM_ADMIN",
    )
    db_session.add(admin)
    db_session.commit()

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "sentinel_admin@platform.corp", "password": "SentinelAdmin123!"},
    )
    token = login_res.json()["access_token"]

    # Trigger test run via API
    run_resp = client.post(
        "/api/v1/security/sentinel/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    assert run_data["status"] == "PASSED"
    run_id = run_data["run_id"]

    # List historical test runs
    list_resp = client.get(
        "/api/v1/security/test-runs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert any(r["id"] == run_id for r in runs)

    # Get details of specific test run
    detail_resp = client.get(
        f"/api/v1/security/test-runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["results"]) == 8
    for res in detail["results"]:
        assert res["passed"] is True

