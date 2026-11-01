"""Tests for health check endpoints and request correlation."""

from starlette.testclient import TestClient


def test_healthz_liveness(client: TestClient):
    """Verify /healthz returns 200 and healthy status."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "api" in data["services"]
    assert response.headers.get("X-Request-ID") is not None


def test_readiness_probe(client: TestClient):
    """Verify /api/v1/health checks database and storage."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data["services"]
    assert data["services"]["database"]["status"] == "healthy"
    assert "storage" in data["services"]
    assert data["services"]["storage"]["status"] == "healthy"


def test_custom_request_id_preserved(client: TestClient):
    """Verify inbound X-Request-ID is preserved in response headers."""
    custom_id = "test-req-12345"
    response = client.get("/healthz", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id

