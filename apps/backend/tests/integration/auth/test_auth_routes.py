from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gim_backend.api.routes.auth import STATE_COOKIE_NAME
from gim_backend.core.oauth import OAuthToken, UserProfile
from gim_backend.main import app


@pytest.fixture
def client():
    """Sync test client for redirect tests."""
    return TestClient(app, follow_redirects=False)


class TestLoginEndpoint:
    """Tests for GET /auth/login/{provider}"""

    def test_github_login_redirects_to_github(self, client):
        """Verify /auth/login/github redirects to GitHub authorize URL."""
        response = client.get("/auth/login/github")

        assert response.status_code == 302
        location = response.headers["location"]
        assert "github.com/login/oauth/authorize" in location
        assert "client_id=" in location
        assert "state=" in location

    def test_google_login_redirects_to_google(self, client):
        """Verify /auth/login/google redirects to Google authorize URL."""
        response = client.get("/auth/login/google")

        assert response.status_code == 302
        location = response.headers["location"]
        assert "accounts.google.com/o/oauth2/v2/auth" in location
        assert "client_id=" in location
        assert "state=" in location

    def test_login_sets_state_cookie(self, client):
        """Verify state cookie is set (contains just the token)."""
        response = client.get("/auth/login/github")

        assert STATE_COOKIE_NAME in response.cookies
        cookie = response.cookies[STATE_COOKIE_NAME]
        # Cookie should be just the token (43 chars for 32 bytes), no colons
        assert ":" not in cookie
        assert len(cookie) > 30

    def test_login_with_remember_me(self, client):
        """Verify remember_me flag is encoded in state PARAMS, not cookie."""
        response = client.get("/auth/login/github?remember_me=true")

        location = response.headers["location"]
        # Extract state param from URL
        import urllib.parse

        parsed = urllib.parse.urlparse(location)
        params = urllib.parse.parse_qs(parsed.query)
        state = params["state"][0]

        # Format: login:token:1
        assert state.startswith("login:")
        assert state.endswith(":1")

    def test_login_without_remember_me(self, client):
        """Verify remember_me=false is encoded in state PARAMS."""
        response = client.get("/auth/login/github?remember_me=false")

        location = response.headers["location"]
        import urllib.parse

        parsed = urllib.parse.urlparse(location)
        params = urllib.parse.parse_qs(parsed.query)
        state = params["state"][0]

        assert state.startswith("login:")
        assert state.endswith(":0")

    def test_invalid_provider_redirects_with_error(self, client):
        """Verify invalid provider redirects to login with error."""
        response = client.get("/auth/login/invalid_provider")

        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_provider" in location


class TestCallbackEndpoint:
    """Tests for GET /auth/callback/{provider}"""

    def test_callback_rejects_missing_state(self, client):
        """Verify redirect with csrf_failed when state missing."""
        response = client.get(
            "/auth/callback/github",
            params={"code": "test_code"},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=missing_code" in location

    def test_callback_rejects_mismatched_state(self, client):
        """Verify redirect with csrf_failed when state mismatches cookie."""
        client.cookies.set(STATE_COOKIE_NAME, "stored_token_12345")

        state = "login:different_token_67890:0"

        response = client.get(
            "/auth/callback/github",
            params={"code": "test_code", "state": state},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=csrf_failed" in location

    def test_callback_handles_consent_denied(self, client):
        """Verify redirect when user denies OAuth consent."""
        response = client.get(
            "/auth/callback/github",
            params={"error": "access_denied"},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=consent_denied" in location

    def test_callback_rejects_invalid_provider(self, client):
        """Verify redirect with invalid_provider error."""
        response = client.get(
            "/auth/callback/invalid",
            params={"code": "test_code", "state": "test_state"},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_provider" in location


class TestCallbackSuccessFlow:
    """Tests for successful OAuth callback with mocked dependencies."""

    @pytest.fixture
    def mock_oauth_flow(self):
        """Mock all OAuth dependencies for success flow."""
        with (
            patch("gim_backend.api.routes.auth.exchange_code_for_token") as mock_exchange,
            patch("gim_backend.api.routes.auth.fetch_user_profile") as mock_profile,
            patch("gim_backend.api.routes.auth.upsert_user") as mock_upsert,
            patch("gim_backend.api.routes.auth.create_session") as mock_session,
            patch("gim_backend.api.routes.auth.get_db") as mock_db,
            patch("gim_backend.api.routes.auth.get_http_client") as mock_client,
        ):
            # Configure mock returns
            mock_exchange.return_value = OAuthToken(
                access_token="test_token",
                token_type="bearer",
            )
            mock_profile.return_value = UserProfile(
                email="test@example.com",
                provider_id="node_123",
                avatar_url="https://example.com/avatar.png",
                is_verified=True,
                username="testuser",
            )

            mock_user = MagicMock()
            mock_user.id = "00000000-0000-0000-0000-000000000001"
            mock_upsert.return_value = mock_user

            mock_session_obj = MagicMock()
            mock_session_obj.id = "00000000-0000-0000-0000-000000000002"
            from datetime import datetime, timedelta

            mock_expires = datetime.now(UTC) + timedelta(days=7)
            mock_session.return_value = (mock_session_obj, mock_expires)

            # Mock async generators
            async def mock_db_gen():
                yield MagicMock()

            async def mock_client_gen():
                yield MagicMock()

            mock_db.return_value = mock_db_gen()
            mock_client.return_value = mock_client_gen()

            yield {
                "exchange": mock_exchange,
                "profile": mock_profile,
                "upsert": mock_upsert,
                "session": mock_session,
            }

    def test_callback_proceeds_without_fingerprint(self, client, mock_oauth_flow):
        """Verify callback proceeds without X-Device-Fingerprint header (fingerprint now optional)."""
        token = "validtoken1234567890123456789012"
        state = f"login:{token}:0"

        client.cookies.set(STATE_COOKIE_NAME, token)

        response = client.get("/auth/callback/github", params={"code": "valid_code", "state": state})

        # Should redirect to dashboard (not reject with 400 for missing fingerprint)
        assert response.status_code == 302
        location = response.headers["location"]
        assert "dashboard" in location

    @patch("gim_backend.api.routes.auth.get_settings")
    def test_callback_success_redirects_to_dashboard(self, mock_settings, client, mock_oauth_flow):
        """Verify successful callback redirects to /dashboard."""
        mock_settings.return_value.frontend_base_url = "http://localhost:3000"

        token = "validtoken1234567890123456789012"
        state = f"login:{token}:0"

        client.cookies.set(STATE_COOKIE_NAME, token)

        response = client.get(
            "/auth/callback/github",
            params={"code": "valid_code", "state": state},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "http://localhost:3000/dashboard" in location

    def test_callback_success_sets_session_cookie(self, client, mock_oauth_flow):
        """Verify session cookie is set after successful auth."""
        token = "validtoken1234567890123456789012"
        # remember_me=1
        state = f"login:{token}:1"

        client.cookies.set(STATE_COOKIE_NAME, token)

        response = client.get(
            "/auth/callback/github",
            params={"code": "valid_code", "state": state},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        assert "session_id" in response.cookies

        # Verify session_id is a valid UUID format
        from uuid import UUID

        session_value = response.cookies.get("session_id")
        UUID(session_value)

    def test_callback_success_clears_state_cookie(self, client, mock_oauth_flow):
        """State cookie must be cleared to prevent replay attacks."""
        token = "validtoken1234567890123456789012"
        state = f"login:{token}:0"

        client.cookies.set(STATE_COOKIE_NAME, token)

        response = client.get(
            "/auth/callback/github",
            params={"code": "valid_code", "state": state},
            headers={"X-Device-Fingerprint": "test_fingerprint"},
        )

        # State cookie should be deleted (empty or max-age=0)
        state_cookie = response.cookies.get(STATE_COOKIE_NAME)
        assert state_cookie == "" or state_cookie is None, (
            "State cookie must be cleared after callback to prevent replay"
        )

    def test_callback_redirects_on_oauth_provider_failure(self, client):
        from gim_backend.core.oauth import OAuthError

        token = "validtoken1234567890123456789012"
        state = f"login:{token}:0"
        client.cookies.set(STATE_COOKIE_NAME, token)

        with patch("gim_backend.api.routes.auth.exchange_code_for_token") as mock_exchange:
            mock_exchange.side_effect = OAuthError("provider temporarily unavailable")

            response = client.get(
                "/auth/callback/github",
                params={"code": "valid_code", "state": state},
                headers={"X-Device-Fingerprint": "test_fingerprint"},
            )

        assert response.status_code == 302
        assert "error=oauth_unavailable" in response.headers["location"]

    def test_link_callback_redirects_on_oauth_provider_failure(self, client):
        from gim_backend.core.oauth import OAuthError

        token = "validtoken1234567890123456789012"
        state = f"link:{token}"
        client.cookies.set(STATE_COOKIE_NAME, token)

        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"

        with (
            patch(
                "gim_backend.api.routes.auth.require_authenticated_user_session",
                return_value=(mock_user, mock_session),
            ),
            patch("gim_backend.api.routes.auth.exchange_code_for_token") as mock_exchange,
        ):
            mock_exchange.side_effect = OAuthError("provider temporarily unavailable")

            response = client.get(
                "/auth/callback/github",
                params={"code": "valid_code", "state": state},
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "/settings/accounts" in location
        assert "error=oauth_unavailable" in location

    def test_connect_callback_redirects_on_oauth_provider_failure(self, client):
        from gim_backend.core.oauth import OAuthError

        token = "validtoken1234567890123456789012"
        state = f"connect:{token}"
        client.cookies.set(STATE_COOKIE_NAME, token)

        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"

        with (
            patch(
                "gim_backend.api.routes.auth.require_authenticated_user_session",
                return_value=(mock_user, mock_session),
            ),
            patch("gim_backend.api.routes.auth.exchange_code_for_token") as mock_exchange,
        ):
            mock_exchange.side_effect = OAuthError("provider temporarily unavailable")

            response = client.get(
                "/auth/callback/github",
                params={"code": "valid_code", "state": state},
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "/profile/onboarding" in location
        assert "error=oauth_unavailable" in location
