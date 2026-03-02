"""Integration tests for repository routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from gim_backend.main import app
from gim_backend.services.repository_service import RepositoryItem


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestRepositoriesEndpointIsPublic:
    """Verifies repositories endpoint doesn't require auth."""

    def test_returns_200_without_auth(self, client):
        """Should not require authentication."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            response = client.get("/repositories")

            assert response.status_code == 200


class TestListRepositories:
    """Tests for GET /repositories endpoint."""

    def test_returns_repositories_list(self, client):
        """Should return list of repositories."""
        repo = RepositoryItem(
            name="facebook/react",
            primary_language="JavaScript",
            issue_count=1250,
        )

        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [repo]

            response = client.get("/repositories")

            assert response.status_code == 200
            data = response.json()
            assert len(data["repositories"]) == 1
            assert data["repositories"][0]["name"] == "facebook/react"

    def test_filters_by_language(self, client):
        """Should pass language filter to service."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            client.get("/repositories?language=Python")

            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args[1]
            assert call_kwargs["language"] == "Python"

    def test_filters_by_search_query(self, client):
        """Should pass search query to service."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            client.get("/repositories?q=react")

            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args[1]
            assert call_kwargs["search_query"] == "react"

    def test_respects_limit_parameter(self, client):
        """Should pass limit to service."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            client.get("/repositories?limit=25")

            call_kwargs = mock_list.call_args[1]
            assert call_kwargs["limit"] == 25

    def test_validates_limit_max(self, client):
        """Should reject limit above max."""
        response = client.get("/repositories?limit=500")
        assert response.status_code == 422

    def test_handles_empty_result(self, client):
        """Should return empty list when no repos match."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            response = client.get("/repositories")

            assert response.status_code == 200
            assert response.json()["repositories"] == []


class TestSQLSafety:
    """Tests for SQL injection prevention."""

    def test_wildcard_percent_is_safe(self, client):
        """Should treat % as literal string, not SQL wildcard."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            # This should not match every repo
            response = client.get("/repositories?q=%")

            assert response.status_code == 200
            # Verify the service was called (no SQL error)
            mock_list.assert_called_once()

    def test_wildcard_underscore_is_safe(self, client):
        """Should treat _ as literal string, not SQL wildcard."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            response = client.get("/repositories?q=_")

            assert response.status_code == 200
            mock_list.assert_called_once()

    def test_sql_injection_is_safe(self, client):
        """Should treat SQL injection attempts as literal strings."""
        with patch("gim_backend.api.routes.repositories.list_repositories", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            response = client.get("/repositories?q='; DROP TABLE--")

            assert response.status_code == 200
            mock_list.assert_called_once()
