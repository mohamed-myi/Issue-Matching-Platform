"""Unit tests for Cloud Tasks service."""

from unittest.mock import AsyncMock
from uuid import uuid4


class TestCloudTasksClientMockMode:
    """Tests for Cloud Tasks client in mock mode."""

    async def test_enqueue_resume_task_returns_job_id(self):
        from gim_backend.services.cloud_tasks_service import (
            reset_client_for_testing,
        )

        reset_client_for_testing()

    async def test_resume_enqueue_uses_shared_builder(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()
        user_id = uuid4()

        client._enqueue_http_json_task = AsyncMock(return_value="job-123")  # type: ignore[method-assign]

        result = await client.enqueue_resume_task(
            user_id=user_id,
            file_bytes=b"test pdf content",
            filename="resume.pdf",
            content_type="application/pdf",
        )

        assert result == "job-123"
        client._enqueue_http_json_task.assert_awaited_once()
        _, kwargs = client._enqueue_http_json_task.await_args
        assert kwargs["user_id"] == user_id
        assert kwargs["job_type"] == "resume"
        assert kwargs["endpoint_url"].endswith("/tasks/resume/parse")
        assert kwargs["log_label"] == "resume parsing"
        assert kwargs["payload_fields"]["filename"] == "resume.pdf"
        assert kwargs["payload_fields"]["content_type"] == "application/pdf"
        assert "file_bytes_b64" in kwargs["payload_fields"]

        reset_client_for_testing()

    async def test_github_enqueue_uses_shared_builder(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()
        user_id = uuid4()

        client._enqueue_http_json_task = AsyncMock(return_value="job-456")  # type: ignore[method-assign]

        result = await client.enqueue_github_task(user_id=user_id)

        assert result == "job-456"
        client._enqueue_http_json_task.assert_awaited_once()
        _, kwargs = client._enqueue_http_json_task.await_args
        assert kwargs["user_id"] == user_id
        assert kwargs["job_type"] == "github"
        assert kwargs["endpoint_url"].endswith("/tasks/github/fetch")
        assert kwargs["log_label"] == "GitHub fetch"
        assert kwargs["payload_fields"] == {}

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()

        job_id = await client.enqueue_resume_task(
            user_id=user_id,
            file_bytes=b"test pdf content",
            filename="resume.pdf",
            content_type="application/pdf",
        )

        assert job_id is not None
        assert isinstance(job_id, str)
        assert len(job_id) > 0

        reset_client_for_testing()

    async def test_enqueue_github_task_returns_job_id(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()

        job_id = await client.enqueue_github_task(user_id=user_id)

        assert job_id is not None
        assert isinstance(job_id, str)
        assert len(job_id) > 0

        reset_client_for_testing()

    async def test_mock_tasks_are_stored(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()

        await client.enqueue_resume_task(
            user_id=user_id,
            file_bytes=b"content",
            filename="test.pdf",
        )

        mock_tasks = client.get_mock_tasks()

        assert len(mock_tasks) == 1

        task_name = list(mock_tasks.keys())[0]
        assert str(user_id) in task_name
        assert "resume" in task_name

        reset_client_for_testing()

    async def test_cancel_user_tasks_removes_all_user_tasks(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id_1 = uuid4()
        user_id_2 = uuid4()

        await client.enqueue_resume_task(user_id=user_id_1, file_bytes=b"a", filename="a.pdf")
        await client.enqueue_github_task(user_id=user_id_1)
        await client.enqueue_resume_task(user_id=user_id_2, file_bytes=b"b", filename="b.pdf")

        assert len(client.get_mock_tasks()) == 3

        cancelled = await client.cancel_user_tasks(user_id_1)

        assert cancelled == 2

        remaining = client.get_mock_tasks()
        assert len(remaining) == 1

        task_name = list(remaining.keys())[0]
        assert str(user_id_2) in task_name

        reset_client_for_testing()

    async def test_cancel_user_tasks_returns_zero_when_no_tasks(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()

        cancelled = await client.cancel_user_tasks(user_id)

        assert cancelled == 0

        reset_client_for_testing()

    async def test_clear_mock_tasks(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()
        await client.enqueue_resume_task(user_id=user_id, file_bytes=b"x", filename="x.pdf")

        assert len(client.get_mock_tasks()) == 1

        client.clear_mock_tasks()

        assert len(client.get_mock_tasks()) == 0

        reset_client_for_testing()


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    async def test_enqueue_resume_task_function(self):
        from gim_backend.services.cloud_tasks_service import (
            enqueue_resume_task,
            reset_client_for_testing,
        )

        reset_client_for_testing()

        user_id = uuid4()
        job_id = await enqueue_resume_task(
            user_id=user_id,
            file_bytes=b"content",
            filename="test.pdf",
        )

        assert job_id is not None

        reset_client_for_testing()

    async def test_enqueue_github_task_function(self):
        from gim_backend.services.cloud_tasks_service import (
            enqueue_github_task,
            reset_client_for_testing,
        )

        reset_client_for_testing()

        user_id = uuid4()
        job_id = await enqueue_github_task(user_id=user_id)

        assert job_id is not None

        reset_client_for_testing()

    async def test_cancel_user_tasks_function(self):
        from gim_backend.services.cloud_tasks_service import (
            cancel_user_tasks,
            enqueue_resume_task,
            reset_client_for_testing,
        )

        reset_client_for_testing()

        user_id = uuid4()
        await enqueue_resume_task(user_id=user_id, file_bytes=b"x", filename="x.pdf")

        cancelled = await cancel_user_tasks(user_id)

        assert cancelled == 1

        reset_client_for_testing()


class TestTaskPayloads:
    """Tests for task payload structure."""

    async def test_resume_task_payload_contains_required_fields(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()

        await client.enqueue_resume_task(
            user_id=user_id,
            file_bytes=b"pdf content here",
            filename="resume.pdf",
            content_type="application/pdf",
        )

        mock_tasks = client.get_mock_tasks()
        task = list(mock_tasks.values())[0]
        payload = task["payload"]

        assert "job_id" in payload
        assert "user_id" in payload
        assert "filename" in payload
        assert "content_type" in payload
        assert "file_bytes_b64" in payload
        assert "created_at" in payload

        assert payload["user_id"] == str(user_id)
        assert payload["filename"] == "resume.pdf"
        assert payload["content_type"] == "application/pdf"

        reset_client_for_testing()

    async def test_github_task_payload_contains_required_fields(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()

        user_id = uuid4()

        await client.enqueue_github_task(user_id=user_id)

        mock_tasks = client.get_mock_tasks()
        task = list(mock_tasks.values())[0]
        payload = task["payload"]

        assert "job_id" in payload
        assert "user_id" in payload
        assert "created_at" in payload

        assert payload["user_id"] == str(user_id)

        reset_client_for_testing()
