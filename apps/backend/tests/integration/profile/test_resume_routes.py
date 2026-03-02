"""Integration tests for resume profile API routes."""

from unittest.mock import AsyncMock, patch

import pytest


class TestAuthRequired:
    """Verifies authentication middleware is applied to all resume routes."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("post", "/profile/resume"),
            ("get", "/profile/resume"),
            ("delete", "/profile/resume"),
        ],
    )
    def test_returns_401_without_auth(self, client, method, path):
        if method == "post":
            response = client.post(path, files={"file": ("resume.pdf", b"content", "application/pdf")})
        else:
            response = getattr(client, method)(path)
        assert response.status_code == 401


class TestPostResume:
    """Tests for POST /profile/resume endpoint (async processing)."""

    def test_returns_400_for_invalid_format(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.services.resume_parsing_service import UnsupportedFormatError

            mock_initiate.side_effect = UnsupportedFormatError("Please upload a PDF or DOCX file")

            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.txt", b"text content", "text/plain")},
            )

        assert response.status_code == 400
        assert "PDF or DOCX" in response.json()["detail"]

    def test_returns_413_for_large_file(self, authenticated_client, mock_user):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE

        large_content = b"x" * (MAX_FILE_SIZE + 1)

        response = authenticated_client.post(
            "/profile/resume",
            files={"file": ("resume.pdf", large_content, "application/pdf")},
        )

        assert response.status_code == 413
        assert "5MB" in response.json()["detail"]

    def test_successful_upload_returns_202_accepted(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-123-abc",
                "status": "processing",
                "message": "Resume uploaded. Processing in background.",
            }

            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.pdf", b"pdf content", "application/pdf")},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "processing"
        assert data["job_id"] == "job-123-abc"
        assert "background" in data["message"].lower()

    def test_accepts_docx_file(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-456-def",
                "status": "processing",
                "message": "Resume uploaded. Processing in background.",
            }

            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.docx", b"docx content", content_type)},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "processing"


class TestGetResume:
    """Tests for GET /profile/resume endpoint."""

    def test_returns_404_when_not_populated(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.get_resume_data",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            response = authenticated_client.get("/profile/resume")

        assert response.status_code == 404
        assert "no resume data" in response.json()["detail"].lower()

    def test_returns_data_when_populated(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.get_resume_data",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "status": "ready",
                "skills": ["Python", "PostgreSQL", "Docker", "FastAPI"],
                "job_titles": ["Backend Engineer", "Tech Lead"],
                "vector_status": "ready",
                "uploaded_at": "2026-01-04T12:00:00+00:00",
            }

            response = authenticated_client.get("/profile/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "Python" in data["skills"]
        assert "PostgreSQL" in data["skills"]
        assert "Backend Engineer" in data["job_titles"]
        assert data["vector_status"] == "ready"
        assert "2026-01-04" in data["uploaded_at"]


class TestDeleteResume:
    """Tests for DELETE /profile/resume endpoint."""

    def test_returns_404_when_no_data(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.delete_resume",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = False

            response = authenticated_client.delete("/profile/resume")

        assert response.status_code == 404
        assert "no resume data" in response.json()["detail"].lower()

    def test_successfully_deletes_data(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.delete_resume",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = True

            response = authenticated_client.delete("/profile/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert "cleared" in data["message"].lower()


class TestAsyncProcessingFlow:
    """Tests verifying async processing via Cloud Tasks."""

    def test_upload_returns_job_id_for_polling(self, authenticated_client, mock_user):
        """Verifies that upload returns job_id for status polling."""
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "test-job-id-123",
                "status": "processing",
                "message": "Resume uploaded. Processing in background.",
            }

            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.pdf", b"pdf content", "application/pdf")},
            )

            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == "test-job-id-123"

    def test_get_resume_shows_processing_status(self, authenticated_client, mock_user):
        """Verifies GET endpoint can show in-progress status."""
        with patch(
            "gim_backend.api.routes.profile_resume.get_resume_data",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "status": "ready",
                "skills": [],
                "job_titles": [],
                "vector_status": None,
                "uploaded_at": "2026-01-07T12:00:00+00:00",
            }

            response = authenticated_client.get("/profile/resume")

            assert response.status_code == 200
            data = response.json()
            assert data["vector_status"] is None


class TestErrorMessages:
    """Tests for error message formatting per PROFILE.md."""

    def test_unsupported_format_message(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            from gim_backend.services.resume_parsing_service import UnsupportedFormatError

            mock_initiate.side_effect = UnsupportedFormatError("Please upload a PDF or DOCX file")

            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.jpg", b"image content", "image/jpeg")},
            )

        assert response.status_code == 400
        assert "PDF or DOCX" in response.json()["detail"]

    def test_file_too_large_message(self, authenticated_client, mock_user):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE

        large_content = b"x" * (MAX_FILE_SIZE + 1)

        response = authenticated_client.post(
            "/profile/resume",
            files={"file": ("resume.pdf", large_content, "application/pdf")},
        )

        assert response.status_code == 413
        assert "5MB" in response.json()["detail"]


class TestFileValidation:
    """Tests for file validation at route level."""

    def test_accepts_pdf_content_type(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-pdf-123",
                "status": "processing",
                "message": "Resume uploaded. Processing in background.",
            }

            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.pdf", b"pdf content", "application/pdf")},
            )

        assert response.status_code == 202

    def test_accepts_docx_content_type(self, authenticated_client, mock_user):
        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-docx-456",
                "status": "processing",
                "message": "Resume uploaded. Processing in background.",
            }

            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.docx", b"docx content", content_type)},
            )

        assert response.status_code == 202


class TestFileSizeLimit:
    """Tests for 5MB file size limit."""

    def test_rejects_file_just_over_limit(self, authenticated_client, mock_user):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE

        content = b"x" * (MAX_FILE_SIZE + 1)

        response = authenticated_client.post(
            "/profile/resume",
            files={"file": ("resume.pdf", content, "application/pdf")},
        )

        assert response.status_code == 413

    def test_accepts_file_at_limit(self, authenticated_client, mock_user):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE

        with patch(
            "gim_backend.api.routes.profile_resume.initiate_resume_processing",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = {
                "job_id": "job-limit-789",
                "status": "processing",
                "message": "Resume uploaded. Processing in background.",
            }

            content = b"x" * MAX_FILE_SIZE

            response = authenticated_client.post(
                "/profile/resume",
                files={"file": ("resume.pdf", content, "application/pdf")},
            )

        assert response.status_code == 202
