"""Unit tests for resume worker endpoints."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.resume_worker import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "resume-worker"


class TestCloudTasksVerification:
    """Tests for Cloud Tasks token verification."""

    def test_accepts_request_in_development(self):
        """Development mode should accept all requests."""
        with patch("gim_backend.workers.resume_worker.settings") as mock_settings:
            mock_settings.environment = "development"

            from gim_backend.workers.resume_worker import _verify_cloud_tasks_token

            result = _verify_cloud_tasks_token(None)
            assert result is True

    def test_accepts_request_with_valid_oidc_and_header(self):
        """Production requires Cloud Tasks header plus valid OIDC bearer."""
        with patch("gim_backend.workers.resume_worker.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_settings.resume_worker_url = "https://resume.example"

            with patch(
                "gim_backend.workers.resume_worker._verify_oidc_bearer_token",
                return_value=True,
            ) as mock_verify:
                from gim_backend.workers.resume_worker import _verify_cloud_tasks_token

                result = _verify_cloud_tasks_token(
                    "task-name-123",
                    "Bearer token",
                    audience="https://resume.example/tasks/resume/parse",
                )
                assert result is True
                mock_verify.assert_called_once()

    def test_rejects_request_without_header_in_production(self):
        """Production requests without header should be rejected."""
        with patch("gim_backend.workers.resume_worker.settings") as mock_settings:
            mock_settings.environment = "production"

            from gim_backend.workers.resume_worker import _verify_cloud_tasks_token

            result = _verify_cloud_tasks_token(None)
            assert result is False

    def test_rejects_spoofed_header_without_bearer_in_production(self):
        with patch("gim_backend.workers.resume_worker.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_settings.resume_worker_url = "https://resume.example"

            from gim_backend.workers.resume_worker import _verify_cloud_tasks_token

            result = _verify_cloud_tasks_token(
                "task-name-123",
                None,
                audience="https://resume.example/tasks/resume/parse",
            )
            assert result is False


class TestResumeParseEndpoint:
    """Tests for POST /tasks/resume/parse endpoint."""

    def test_returns_403_without_auth_in_production(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.resume_worker import app

        file_content = b"PDF content here"
        file_b64 = base64.b64encode(file_content).decode("utf-8")

        with patch("gim_backend.workers.resume_worker.settings") as mock_settings:
            mock_settings.environment = "production"

            client = TestClient(app)
            response = client.post(
                "/tasks/resume/parse",
                json={
                    "job_id": "job-123",
                    "user_id": str(uuid4()),
                    "filename": "resume.pdf",
                    "content_type": "application/pdf",
                    "file_bytes_b64": file_b64,
                    "created_at": "2026-01-07T12:00:00Z",
                },
            )

            assert response.status_code == 403

    def test_decodes_base64_file_content(self):
        """Verifies file bytes are properly decoded from base64."""
        from fastapi.testclient import TestClient

        from gim_backend.workers.resume_worker import app

        original_content = b"This is the original PDF content"
        file_b64 = base64.b64encode(original_content).decode("utf-8")
        user_id = uuid4()

        mock_profile = MagicMock()
        mock_profile.intent_vector = None
        mock_profile.github_vector = None

        captured_content = None

        def capture_parse(file_bytes, filename):
            nonlocal captured_content
            captured_content = file_bytes
            return "# Parsed Markdown\n\nSkills: Python, Docker"

        with (
            patch("gim_backend.workers.resume_worker.settings") as mock_settings,
            patch("gim_backend.workers.resume_worker.parse_resume_to_markdown", side_effect=capture_parse),
            patch("gim_backend.workers.resume_worker.extract_entities") as mock_extract,
            patch("gim_backend.workers.resume_worker.normalize_entities") as mock_normalize,
            patch("gim_backend.workers.resume_worker.check_minimal_data") as mock_check,
            patch("gim_backend.workers.resume_worker.embed_document", new_callable=AsyncMock) as mock_embed,
            patch("gim_backend.workers.resume_worker.async_session_factory") as mock_session_factory,
            patch("gim_backend.workers.resume_worker._get_profile", new_callable=AsyncMock) as mock_get_profile,
            patch("gim_backend.workers.resume_worker.calculate_combined_vector", new_callable=AsyncMock) as mock_calc,
            patch("gim_backend.workers.resume_worker._verify_oidc_bearer_token", return_value=True),
        ):
            mock_settings.environment = "development"
            mock_extract.return_value = []
            mock_normalize.return_value = (["Python"], [], {})
            mock_check.return_value = None
            mock_embed.return_value = [0.1] * 256
            mock_get_profile.return_value = mock_profile
            mock_calc.return_value = [0.1] * 256

            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            client = TestClient(app)
            response = client.post(
                "/tasks/resume/parse",
                json={
                    "job_id": "job-decode-test",
                    "user_id": str(user_id),
                    "filename": "resume.pdf",
                    "content_type": "application/pdf",
                    "file_bytes_b64": file_b64,
                    "created_at": "2026-01-07T12:00:00Z",
                },
            )

            assert captured_content == original_content
            assert response.status_code == 200


class TestProfileNotFound:
    """Tests for handling deleted profiles."""

    def test_returns_abandoned_when_profile_not_found(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.resume_worker import app

        file_content = b"PDF content"
        file_b64 = base64.b64encode(file_content).decode("utf-8")
        user_id = uuid4()

        with (
            patch("gim_backend.workers.resume_worker.settings") as mock_settings,
            patch("gim_backend.workers.resume_worker.parse_resume_to_markdown") as mock_parse,
            patch("gim_backend.workers.resume_worker.extract_entities") as mock_extract,
            patch("gim_backend.workers.resume_worker.normalize_entities") as mock_normalize,
            patch("gim_backend.workers.resume_worker.check_minimal_data") as mock_check,
            patch("gim_backend.workers.resume_worker.async_session_factory") as mock_session_factory,
            patch("gim_backend.workers.resume_worker._get_profile", new_callable=AsyncMock) as mock_get_profile,
        ):
            mock_settings.environment = "development"
            mock_parse.return_value = "# Resume"
            mock_extract.return_value = []
            mock_normalize.return_value = ([], [], {})
            mock_check.return_value = None
            mock_get_profile.return_value = None

            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            client = TestClient(app)
            response = client.post(
                "/tasks/resume/parse",
                json={
                    "job_id": "job-orphan",
                    "user_id": str(user_id),
                    "filename": "resume.pdf",
                    "content_type": "application/pdf",
                    "file_bytes_b64": file_b64,
                    "created_at": "2026-01-07T12:00:00Z",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "abandoned"
            assert data["reason"] == "profile_not_found"


class TestSuccessfulParsing:
    """Tests for successful resume parsing flow."""

    def test_returns_completed_with_counts(self):
        from fastapi.testclient import TestClient

        from gim_backend.workers.resume_worker import app

        file_content = b"PDF content"
        file_b64 = base64.b64encode(file_content).decode("utf-8")
        user_id = uuid4()

        mock_profile = MagicMock()
        mock_profile.intent_vector = None
        mock_profile.github_vector = None

        with (
            patch("gim_backend.workers.resume_worker.settings") as mock_settings,
            patch("gim_backend.workers.resume_worker.parse_resume_to_markdown") as mock_parse,
            patch("gim_backend.workers.resume_worker.extract_entities") as mock_extract,
            patch("gim_backend.workers.resume_worker.normalize_entities") as mock_normalize,
            patch("gim_backend.workers.resume_worker.check_minimal_data") as mock_check,
            patch("gim_backend.workers.resume_worker.embed_document", new_callable=AsyncMock) as mock_embed,
            patch("gim_backend.workers.resume_worker.async_session_factory") as mock_session_factory,
            patch("gim_backend.workers.resume_worker._get_profile", new_callable=AsyncMock) as mock_get_profile,
            patch("gim_backend.workers.resume_worker.calculate_combined_vector", new_callable=AsyncMock) as mock_calc,
            patch("gim_backend.workers.resume_worker._verify_oidc_bearer_token", return_value=True),
        ):
            mock_settings.environment = "development"
            mock_parse.return_value = "# Resume\n\n## Skills\nPython, Docker, FastAPI"
            mock_extract.return_value = [
                {"text": "Python", "label": "Skill"},
                {"text": "Docker", "label": "Tool"},
                {"text": "Senior Engineer", "label": "Job Title"},
            ]
            mock_normalize.return_value = (
                ["Python", "Docker"],
                ["Senior Engineer"],
                {"entities": [], "unrecognized": []},
            )
            mock_check.return_value = None
            mock_embed.return_value = [0.1] * 256
            mock_get_profile.return_value = mock_profile
            mock_calc.return_value = [0.1] * 256

            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            client = TestClient(app)
            response = client.post(
                "/tasks/resume/parse",
                json={
                    "job_id": "job-success",
                    "user_id": str(user_id),
                    "filename": "resume.pdf",
                    "content_type": "application/pdf",
                    "file_bytes_b64": file_b64,
                    "created_at": "2026-01-07T12:00:00Z",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["job_id"] == "job-success"
            assert data["skills_count"] == 2
            assert data["job_titles_count"] == 1
            assert data["vector_generated"] is True
