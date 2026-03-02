"""Unit tests for embed worker endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.embed_worker import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "embed-worker"


class TestCloudTasksVerification:
    """Tests for Cloud Tasks token verification."""

    def test_accepts_request_in_development(self):
        """Development mode should accept all requests."""
        with patch("gim_backend.workers.embed_worker.settings") as mock_settings:
            mock_settings.environment = "development"

            from gim_backend.workers.embed_worker import _verify_cloud_tasks_token

            result = _verify_cloud_tasks_token(None)
            assert result is True

    def test_accepts_request_with_valid_oidc_and_header(self):
        """Production requires Cloud Tasks header plus valid OIDC bearer."""
        with patch("gim_backend.workers.embed_worker.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_settings.embed_worker_url = "https://embed.example"

            with patch(
                "gim_backend.workers.embed_worker._verify_oidc_bearer_token",
                return_value=True,
            ) as mock_verify:
                from gim_backend.workers.embed_worker import _verify_cloud_tasks_token

                result = _verify_cloud_tasks_token(
                    "task-name-123",
                    "Bearer token",
                    audience="https://embed.example/tasks/embed/resume",
                )
                assert result is True
                mock_verify.assert_called_once()

    def test_rejects_request_without_header_in_production(self):
        """Production requests without header should be rejected."""
        with patch("gim_backend.workers.embed_worker.settings") as mock_settings:
            mock_settings.environment = "production"

            from gim_backend.workers.embed_worker import _verify_cloud_tasks_token

            result = _verify_cloud_tasks_token(None)
            assert result is False

    def test_rejects_spoofed_header_without_bearer_in_production(self):
        with patch("gim_backend.workers.embed_worker.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_settings.embed_worker_url = "https://embed.example"

            from gim_backend.workers.embed_worker import _verify_cloud_tasks_token

            result = _verify_cloud_tasks_token(
                "task-name-123",
                None,
                audience="https://embed.example/tasks/embed/resume",
            )
            assert result is False


class TestResumeEmbedEndpoint:
    """Tests for POST /tasks/embed/resume endpoint."""

    def test_returns_403_without_auth_in_production(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.embed_worker import app

        with patch("gim_backend.workers.embed_worker.settings") as mock_settings:
            mock_settings.environment = "production"

            client = TestClient(app)
            response = client.post(
                "/tasks/embed/resume",
                json={
                    "job_id": "job-123",
                    "user_id": str(uuid4()),
                    "markdown_text": "Test markdown content",
                },
            )

            assert response.status_code == 403

    def test_accepts_request_with_valid_cloud_tasks_auth(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.embed_worker import app

        user_id = uuid4()
        mock_profile = MagicMock()
        mock_profile.intent_vector = None
        mock_profile.github_vector = None

        with (
            patch("gim_backend.workers.embed_worker.settings") as mock_settings,
            patch("gim_backend.workers.embed_worker.embed_document", new_callable=AsyncMock) as mock_embed,
            patch("gim_backend.workers.embed_worker.async_session_factory") as mock_session_factory,
            patch("gim_backend.workers.embed_worker._get_profile", new_callable=AsyncMock) as mock_get_profile,
            patch("gim_backend.workers.embed_worker.calculate_combined_vector", new_callable=AsyncMock) as mock_calc,
            patch("gim_backend.workers.embed_worker._verify_oidc_bearer_token", return_value=True),
        ):
            mock_settings.environment = "production"
            mock_settings.embed_worker_url = "https://embed.example"
            mock_embed.return_value = [0.1] * 256
            mock_get_profile.return_value = mock_profile
            mock_calc.return_value = [0.1] * 256

            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            client = TestClient(app)
            response = client.post(
                "/tasks/embed/resume",
                json={
                    "job_id": "job-123",
                    "user_id": str(user_id),
                    "markdown_text": "Test markdown content",
                },
                headers={
                    "X-CloudTasks-TaskName": "task-123",
                    "Authorization": "Bearer token",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"


class TestGitHubEmbedEndpoint:
    """Tests for POST /tasks/embed/github endpoint."""

    def test_returns_403_without_auth_in_production(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.embed_worker import app

        with patch("gim_backend.workers.embed_worker.settings") as mock_settings:
            mock_settings.environment = "production"

            client = TestClient(app)
            response = client.post(
                "/tasks/embed/github",
                json={
                    "job_id": "job-456",
                    "user_id": str(uuid4()),
                    "formatted_text": "Python, Go, web development",
                },
            )

            assert response.status_code == 403


class TestProfileNotFound:
    """Tests for handling deleted profiles."""

    def test_returns_abandoned_when_profile_not_found(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.embed_worker import app

        user_id = uuid4()

        with (
            patch("gim_backend.workers.embed_worker.settings") as mock_settings,
            patch("gim_backend.workers.embed_worker.embed_document", new_callable=AsyncMock) as mock_embed,
            patch("gim_backend.workers.embed_worker.async_session_factory") as mock_session_factory,
            patch("gim_backend.workers.embed_worker._get_profile", new_callable=AsyncMock) as mock_get_profile,
        ):
            mock_settings.environment = "development"
            mock_embed.return_value = [0.1] * 256
            mock_get_profile.return_value = None

            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            client = TestClient(app)
            response = client.post(
                "/tasks/embed/resume",
                json={
                    "job_id": "job-orphan",
                    "user_id": str(user_id),
                    "markdown_text": "Test content",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "abandoned"
            assert data["reason"] == "profile_not_found"
