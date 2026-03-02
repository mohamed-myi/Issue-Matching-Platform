"""
Integration tests for public API routes.
Tests /feed/trending and /stats without authentication.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gim_backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


class _FeedItem:
    """Mock feed item for testing."""

    def __init__(self, node_id: str = "I_test123"):
        self.node_id = node_id
        self.title = "Test Issue"
        self.body_preview = "Test body preview"
        self.labels = ["bug", "help wanted"]
        self.q_score = 0.85
        self.repo_name = "test/repo"
        self.primary_language = "Python"
        self.repo_topics = ["testing"]
        self.github_created_at = datetime(2026, 1, 9, 12, 0, 0, tzinfo=UTC)
        self.similarity_score = None
        self.why_this = None


class _FeedResponse:
    """Mock feed response for testing."""

    def __init__(self, count: int = 3, total: int = 100):
        self.results = [_FeedItem(f"I_test{i}") for i in range(count)]
        self.total = total
        self.page = 1
        self.page_size = count
        self.has_more = True
        self.is_personalized = False
        self.profile_cta = None


class _PlatformStats:
    """Mock stats for testing."""

    def __init__(self):
        self.total_issues = 15000
        self.total_repos = 500
        self.total_languages = 25
        self.indexed_at = datetime(2026, 1, 9, 6, 0, 0, tzinfo=UTC)


class TestTrendingRoute:
    """Tests for GET /feed/trending."""

    def test_trending_returns_200_without_auth(self, client):
        """Trending endpoint works without authentication."""
        with patch(
            "gim_backend.api.routes.public._get_trending_feed",
            return_value=_FeedResponse(count=5),
        ):
            response = client.get("/feed/trending")

        assert response.status_code == 200

    def test_trending_returns_expected_structure(self, client):
        """Response has expected fields."""
        with patch(
            "gim_backend.api.routes.public._get_trending_feed",
            return_value=_FeedResponse(count=3),
        ):
            response = client.get("/feed/trending")

        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "page_size" in data

    def test_trending_results_have_expected_fields(self, client):
        """Each result has expected issue fields."""
        with patch(
            "gim_backend.api.routes.public._get_trending_feed",
            return_value=_FeedResponse(count=1),
        ):
            response = client.get("/feed/trending")

        data = response.json()
        result = data["results"][0]
        assert "node_id" in result
        assert "title" in result
        assert "body_preview" in result
        assert "labels" in result
        assert "q_score" in result
        assert "repo_name" in result
        assert "primary_language" in result
        assert "github_created_at" in result

    def test_trending_limit_is_10(self, client):
        """Public endpoint defaults to page_size of 10."""
        with patch(
            "gim_backend.api.routes.public._get_trending_feed",
            return_value=_FeedResponse(count=10),
        ):
            response = client.get("/feed/trending")

        data = response.json()
        assert data["page_size"] == 10

    def test_trending_returns_empty_for_empty_db(self, client):
        """Returns empty results gracefully."""
        with patch(
            "gim_backend.api.routes.public._get_trending_feed",
            return_value=_FeedResponse(count=0, total=0),
        ):
            response = client.get("/feed/trending")

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0


class TestStatsRoute:
    """Tests for GET /stats."""

    def test_stats_returns_200_without_auth(self, client):
        """Stats endpoint works without authentication."""
        with patch(
            "gim_backend.api.routes.public.get_platform_stats",
            return_value=_PlatformStats(),
        ):
            response = client.get("/stats")

        assert response.status_code == 200

    def test_stats_returns_expected_fields(self, client):
        """Response has all required fields."""
        with patch(
            "gim_backend.api.routes.public.get_platform_stats",
            return_value=_PlatformStats(),
        ):
            response = client.get("/stats")

        data = response.json()
        assert "total_issues" in data
        assert "total_repos" in data
        assert "total_languages" in data
        assert "indexed_at" in data

    def test_stats_returns_correct_values(self, client):
        """Response contains correct stat values."""
        with patch(
            "gim_backend.api.routes.public.get_platform_stats",
            return_value=_PlatformStats(),
        ):
            response = client.get("/stats")

        data = response.json()
        assert data["total_issues"] == 15000
        assert data["total_repos"] == 500
        assert data["total_languages"] == 25

    def test_stats_handles_null_indexed_at(self, client):
        """Handles null indexed_at gracefully."""
        stats = _PlatformStats()
        stats.indexed_at = None

        with patch(
            "gim_backend.api.routes.public.get_platform_stats",
            return_value=stats,
        ):
            response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["indexed_at"] is None
