"""Integration tests for issue routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gim_backend.main import app
from gim_backend.middleware.auth import require_auth
from gim_backend.services.issue_service import IssueDetail, SimilarIssue


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_user():
    """Create mock user."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_session(mock_user):
    """Create mock session."""
    session = MagicMock()
    session.id = uuid4()
    session.user_id = mock_user.id
    return session


@pytest.fixture
def authenticated_client(client, mock_user, mock_session):
    """Client with mocked authentication using dependency override."""

    def mock_require_auth():
        return (mock_user, mock_session)

    app.dependency_overrides[require_auth] = mock_require_auth
    yield client
    app.dependency_overrides.clear()


class TestPublicAccess:
    """Verifies issue routes are accessible without authentication."""

    def test_issue_detail_accessible_without_auth(self, client):
        issue = IssueDetail(
            node_id="I_public",
            title="Public issue",
            body="Body",
            labels=["bug"],
            q_score=0.8,
            repo_name="org/repo",
            repo_url="https://github.com/org/repo",
            github_url="https://github.com/org/repo/issues/1",
            primary_language="Python",
            github_created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            state="open",
        )

        with patch("gim_backend.api.routes.issues.get_issue_by_node_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = issue
            response = client.get("/issues/I_public")
            assert response.status_code == 200

    def test_similar_accessible_without_auth(self, client):
        with patch("gim_backend.api.routes.issues.get_similar_issues", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = []
            response = client.get("/issues/I_public/similar")
            assert response.status_code == 200


class TestGetIssueDetail:
    """Tests for GET /issues/{node_id} endpoint."""

    def test_returns_issue_when_found(self, authenticated_client):
        """Should return full issue detail."""
        issue = IssueDetail(
            node_id="I_abc123",
            title="Fix memory leak",
            body="Full body content",
            labels=["bug", "memory"],
            q_score=0.85,
            repo_name="facebook/react",
            repo_url="https://github.com/facebook/react",
            github_url="https://github.com/facebook/react/issues/123",
            primary_language="JavaScript",
            github_created_at=datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC),
            state="open",
        )

        with patch("gim_backend.api.routes.issues.get_issue_by_node_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = issue

            response = authenticated_client.get("/issues/I_abc123")

            assert response.status_code == 200
            data = response.json()
            assert data["node_id"] == "I_abc123"
            assert data["title"] == "Fix memory leak"
            assert data["labels"] == ["bug", "memory"]

    def test_returns_404_when_not_found(self, authenticated_client):
        """Should return 404 when issue doesn't exist."""
        with patch("gim_backend.api.routes.issues.get_issue_by_node_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            response = authenticated_client.get("/issues/I_nonexistent")

            assert response.status_code == 404
            assert "Issue not found" in response.json()["detail"]


class TestGetSimilarIssues:
    """Tests for GET /issues/{node_id}/similar endpoint."""

    def test_returns_similar_issues(self, authenticated_client):
        """Should return list of similar issues."""
        similar1 = SimilarIssue(
            node_id="I_similar1",
            title="Related Issue",
            repo_name="org/repo",
            similarity_score=0.95,
        )

        with patch("gim_backend.api.routes.issues.get_similar_issues", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = [similar1]

            response = authenticated_client.get("/issues/I_source/similar")

            assert response.status_code == 200
            data = response.json()
            assert len(data["issues"]) == 1
            assert data["issues"][0]["node_id"] == "I_similar1"
            assert data["issues"][0]["similarity_score"] == 0.95

    def test_returns_empty_list_when_no_embedding(self, authenticated_client):
        """Should return empty list when source has no embedding."""
        with patch("gim_backend.api.routes.issues.get_similar_issues", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = []

            response = authenticated_client.get("/issues/I_noembedding/similar")

            assert response.status_code == 200
            assert response.json()["issues"] == []

    def test_returns_404_when_source_not_found(self, authenticated_client):
        """Should return 404 when source issue doesn't exist."""
        with patch("gim_backend.api.routes.issues.get_similar_issues", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = None

            response = authenticated_client.get("/issues/I_nonexistent/similar")

            assert response.status_code == 404

    def test_respects_limit_parameter(self, authenticated_client):
        """Should pass limit parameter to service."""
        with patch("gim_backend.api.routes.issues.get_similar_issues", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = []

            authenticated_client.get("/issues/I_source/similar?limit=3")

            mock_similar.assert_called_once()
            call_kwargs = mock_similar.call_args[1]
            assert call_kwargs["limit"] == 3

    def test_validates_limit_max(self, authenticated_client):
        """Should reject limit above max."""
        with patch("gim_backend.api.routes.issues.get_similar_issues", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = []

            response = authenticated_client.get("/issues/I_source/similar?limit=100")

            assert response.status_code == 422
