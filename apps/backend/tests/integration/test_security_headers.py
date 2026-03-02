"""Tests for security headers middleware."""

import pytest
from fastapi.testclient import TestClient

from gim_backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestSecurityHeaders:
    """Verify security headers are set on all responses."""

    def test_health_endpoint_has_security_headers(self, client):
        """Health endpoint should include all security headers."""
        response = client.get("/health")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_404_endpoint_has_security_headers(self, client):
        """Even error responses should have security headers."""
        response = client.get("/nonexistent-endpoint")

        assert response.status_code == 404
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_protected_endpoint_has_security_headers(self, client):
        """Authenticated endpoints should have security headers."""
        response = client.get("/profile")

        assert response.status_code == 401
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


class TestCORSConfiguration:
    """Verify CORS middleware is active."""

    def test_cors_credentials_header_present(self, client):
        """CORS middleware should be active (credentials header present)."""
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_rejects_unconfigured_origin(self, client):
        """Unconfigured origins should not get CORS allow-origin header."""
        response = client.get("/health", headers={"Origin": "https://malicious-site.com"})

        # Should NOT include the malicious origin in CORS header
        cors_origin = response.headers.get("access-control-allow-origin", "")
        assert "malicious-site.com" not in cors_origin
