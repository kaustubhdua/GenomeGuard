"""Regression coverage for browser security headers on error responses."""

from starlette.testclient import TestClient

import app.api as api_module
from tests.helpers import make_client


def test_security_headers_cover_unhandled_https_500_responses(monkeypatch):
    service, _client = make_client()

    def fail_readiness(_service):
        raise RuntimeError("synthetic test failure")

    monkeypatch.setattr(api_module, "readiness_checks", fail_readiness)
    client = TestClient(
        api_module.create_app(service),
        base_url="https://testserver",
        raise_server_exceptions=False,
    )

    response = client.get("/health")

    assert response.status_code == 500
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
