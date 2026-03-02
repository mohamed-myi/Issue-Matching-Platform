"""Integration tests for GitHub profile API routes."""

from unittest.mock import AsyncMock, patch

import pytest


class TestAuthRequired:
    """Verifies authentication middleware is applied to all GitHub routes."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("post", "/profile/github"),
            ("get", "/profile/github"),
            ("post", "/profile/github/refresh"),
            ("delete", "/profile/github"),
        ],
    )
    def test_returns_401_without_auth(self, client, method, path):
        response = getattr(client, method)(path)
        assert response.status_code == 401


class TestPostGitHub:
    """Tests for POST /profile/github endpoint (async processing)."""

    def test_returns_400_when_no_github_connected(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.core.errors import GitHubNotConnectedError

            mock_initiate.side_effect = GitHubNotConnectedError(
                "No GitHub account connected. Please connect GitHub first at /auth/connect/github"
            )

            response = authenticated_client.post("/profile/github")

        assert response.status_code == 400
        assert "connect" in response.json()["detail"].lower()

    def test_returns_400_when_token_revoked(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.core.errors import GitHubNotConnectedError

            mock_initiate.side_effect = GitHubNotConnectedError("Please reconnect your GitHub account")

            response = authenticated_client.post("/profile/github")

        assert response.status_code == 400
        assert "connect github" in response.json()["detail"].lower()

    def test_successful_initiate_returns_202_accepted(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-github-123",
                "status": "processing",
                "message": "GitHub profile fetch started. Processing in background.",
            }

            response = authenticated_client.post("/profile/github")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "processing"
        assert data["job_id"] == "job-github-123"
        assert "background" in data["message"].lower()


class TestGetGitHub:
    """Tests for GET /profile/github endpoint."""

    def test_returns_404_when_not_populated(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.get_github_data",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            response = authenticated_client.get("/profile/github")

        assert response.status_code == 404
        assert "no github data" in response.json()["detail"].lower()

    def test_returns_data_when_populated(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.get_github_data",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "status": "ready",
                "username": "octocat",
                "starred_count": 42,
                "contributed_repos": 10,
                "languages": ["Python", "TypeScript"],
                "topics": ["web", "api", "async"],
                "vector_status": "ready",
                "fetched_at": "2026-01-04T12:00:00+00:00",
            }

            response = authenticated_client.get("/profile/github")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "octocat"
        assert data["starred_count"] == 42
        assert data["contributed_repos"] == 10
        assert "Python" in data["languages"]
        assert "web" in data["topics"]
        assert data["vector_status"] == "ready"


class TestRefreshGitHub:
    """Tests for POST /profile/github/refresh endpoint."""

    def test_returns_429_when_too_soon(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.core.errors import RefreshRateLimitError

            mock_initiate.side_effect = RefreshRateLimitError(1800)

            response = authenticated_client.post("/profile/github/refresh")

        assert response.status_code == 429
        assert "minute" in response.json()["detail"].lower()

    def test_allows_refresh_after_cooldown_returns_202(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-refresh-456",
                "status": "processing",
                "message": "GitHub profile fetch started. Processing in background.",
            }

            response = authenticated_client.post("/profile/github/refresh")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "processing"
        assert data["job_id"] == "job-refresh-456"


class TestDeleteGitHub:
    """Tests for DELETE /profile/github endpoint."""

    def test_returns_404_when_no_data(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.delete_github",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = False

            response = authenticated_client.delete("/profile/github")

        assert response.status_code == 404
        assert "no github data" in response.json()["detail"].lower()

    def test_successfully_deletes_data(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.delete_github",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = True

            response = authenticated_client.delete("/profile/github")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert "cleared" in data["message"].lower()


class TestAsyncProcessingFlow:
    """Tests verifying async processing via Cloud Tasks."""

    def test_initiate_returns_job_id_for_polling(self, authenticated_client, mock_user):
        """Verifies that initiate returns job_id for status polling."""
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "test-github-job-789",
                "status": "processing",
                "message": "GitHub profile fetch started. Processing in background.",
            }

            response = authenticated_client.post("/profile/github")

            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == "test-github-job-789"

    def test_get_github_shows_processing_status(self, authenticated_client, mock_user):
        """Verifies GET endpoint can show in-progress status."""
        with patch(
            "gim_backend.api.routes.profile_github.get_github_data",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "status": "ready",
                "username": "octocat",
                "starred_count": 0,
                "contributed_repos": 0,
                "languages": [],
                "topics": [],
                "vector_status": None,
                "fetched_at": None,
            }

            response = authenticated_client.get("/profile/github")

            assert response.status_code == 200
            data = response.json()
            assert data["vector_status"] is None


class TestErrorMessages:
    """Tests for error message formatting per PROFILE.md."""

    def test_oauth_revoked_message(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.core.errors import GitHubNotConnectedError

            mock_initiate.side_effect = GitHubNotConnectedError("Please reconnect your GitHub account")

            response = authenticated_client.post("/profile/github")

        assert response.status_code == 400
        assert "connect github" in response.json()["detail"].lower()

    def test_refresh_rate_limit_shows_minutes(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_github.initiate_github_fetch",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.core.errors import RefreshRateLimitError

            mock_initiate.side_effect = RefreshRateLimitError(1800)

            response = authenticated_client.post("/profile/github/refresh")

        assert response.status_code == 429
        detail = response.json()["detail"].lower()
        assert "minute" in detail
