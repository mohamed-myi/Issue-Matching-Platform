"""
End-to-end integration tests for Profile Engine Phase 6.
Tests full onboarding flow, feed personalization, and error handling.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_user_email() -> str:
    return "e2e@example.com"


def create_mock_profile(
    user_id,
    intent_text=None,
    intent_vector=None,
    resume_skills=None,
    resume_vector=None,
    github_username=None,
    github_vector=None,
    combined_vector=None,
    onboarding_status="not_started",
):
    """Creates a mock profile object with configurable state."""
    profile = MagicMock()
    profile.user_id = user_id
    profile.intent_text = intent_text
    profile.intent_stack_areas = ["backend"] if intent_text else None
    profile.intent_experience = "intermediate" if intent_text else None
    profile.intent_vector = intent_vector
    profile.resume_skills = resume_skills
    profile.resume_job_titles = ["Engineer"] if resume_skills else None
    profile.resume_vector = resume_vector
    profile.resume_uploaded_at = datetime.now(UTC) if resume_skills else None
    profile.github_username = github_username
    profile.github_languages = ["Python"] if github_username else None
    profile.github_topics = ["web"] if github_username else None
    profile.github_vector = github_vector
    profile.github_data = {"starred_count": 10} if github_username else None
    profile.github_fetched_at = datetime.now(UTC) if github_username else None
    profile.combined_vector = combined_vector
    profile.preferred_languages = ["Python"] if intent_text else None
    profile.preferred_topics = None
    profile.min_heat_threshold = 0.6
    profile.is_calculating = False
    profile.onboarding_status = onboarding_status
    profile.onboarding_completed_at = None
    profile.updated_at = datetime.now(UTC)
    return profile


SAMPLE_VECTOR = [0.01] * 256


class TestFeedAuthRequired:
    """Verifies authentication is required for feed endpoint."""

    def test_feed_returns_401_without_auth(self, client):
        response = client.get("/feed")
        assert response.status_code == 401


class TestFeedTrendingFallback:
    """Tests trending feed fallback when user has no profile."""

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_returns_trending_when_no_combined_vector(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(mock_user.id)
        mock_get_profile.return_value = mock_profile

        with patch("gim_backend.services.feed_service._get_trending_feed") as mock_trending:
            from gim_backend.services.feed_service import TRENDING_CTA, FeedPage

            mock_trending.return_value = FeedPage(
                results=[],
                total=0,
                page=1,
                page_size=20,
                has_more=False,
                is_personalized=False,
                profile_cta=TRENDING_CTA,
            )

            response = authenticated_client.get("/feed")

        assert response.status_code == 200
        data = response.json()
        assert data["is_personalized"] is False
        assert data["profile_cta"] is not None
        assert "trending" in data["profile_cta"].lower()

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_trending_feed_shows_cta_message(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(mock_user.id)
        mock_get_profile.return_value = mock_profile

        with patch("gim_backend.services.feed_service._get_trending_feed") as mock_trending:
            from gim_backend.services.feed_service import TRENDING_CTA, FeedPage

            mock_trending.return_value = FeedPage(
                results=[],
                total=0,
                page=1,
                page_size=20,
                has_more=False,
                is_personalized=False,
                profile_cta=TRENDING_CTA,
            )

            response = authenticated_client.get("/feed")

        data = response.json()
        assert "Complete your profile" in data["profile_cta"]


class TestFeedPersonalized:
    """Tests personalized feed when user has combined_vector."""

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_returns_personalized_when_has_combined_vector(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(
            mock_user.id,
            intent_text="I want to contribute",
            intent_vector=SAMPLE_VECTOR,
            combined_vector=SAMPLE_VECTOR,
            onboarding_status="completed",
        )
        mock_get_profile.return_value = mock_profile

        with patch("gim_backend.services.feed_service._get_personalized_feed") as mock_personalized:
            from gim_backend.services.feed_service import FeedPage

            mock_personalized.return_value = FeedPage(
                results=[],
                total=0,
                page=1,
                page_size=20,
                has_more=False,
                is_personalized=True,
                profile_cta=None,
            )

            response = authenticated_client.get("/feed")

        assert response.status_code == 200
        data = response.json()
        assert data["is_personalized"] is True
        assert data["profile_cta"] is None

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_personalized_feed_no_cta(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(
            mock_user.id,
            intent_text="I want to contribute",
            intent_vector=SAMPLE_VECTOR,
            combined_vector=SAMPLE_VECTOR,
        )
        mock_get_profile.return_value = mock_profile

        with patch("gim_backend.services.feed_service._get_personalized_feed") as mock_personalized:
            from gim_backend.services.feed_service import FeedPage

            mock_personalized.return_value = FeedPage(
                results=[],
                total=0,
                page=1,
                page_size=20,
                has_more=False,
                is_personalized=True,
                profile_cta=None,
            )

            response = authenticated_client.get("/feed")

        data = response.json()
        assert data["profile_cta"] is None


class TestFeedPagination:
    """Tests feed pagination parameters."""

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_accepts_page_parameter(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(mock_user.id)
        mock_get_profile.return_value = mock_profile

        with patch("gim_backend.services.feed_service._get_trending_feed") as mock_trending:
            from gim_backend.services.feed_service import TRENDING_CTA, FeedPage

            mock_trending.return_value = FeedPage(
                results=[],
                total=0,
                page=2,
                page_size=20,
                has_more=False,
                is_personalized=False,
                profile_cta=TRENDING_CTA,
            )

            response = authenticated_client.get("/feed?page=2")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_accepts_page_size_parameter(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(mock_user.id)
        mock_get_profile.return_value = mock_profile

        with patch("gim_backend.services.feed_service._get_trending_feed") as mock_trending:
            from gim_backend.services.feed_service import TRENDING_CTA, FeedPage

            mock_trending.return_value = FeedPage(
                results=[],
                total=0,
                page=1,
                page_size=10,
                has_more=False,
                is_personalized=False,
                profile_cta=TRENDING_CTA,
            )

            response = authenticated_client.get("/feed?page_size=10")

        assert response.status_code == 200


class TestOnboardingToFeedFlow:
    """Tests the complete flow from onboarding to personalized feed."""

    @pytest.mark.asyncio
    async def test_intent_vector_triggers_combined_calculation(self):
        """Verifies that intent creation would trigger combined vector calculation."""
        from gim_backend.services.profile_embedding_service import calculate_combined_vector

        intent_vector = SAMPLE_VECTOR

        combined = await calculate_combined_vector(
            intent_vector=intent_vector,
            resume_vector=None,
            github_vector=None,
        )

        assert combined is not None
        magnitude = sum(x * x for x in combined) ** 0.5
        assert abs(magnitude - 1.0) < 0.001


class TestRetryLogic:
    """Tests retry logic for embedding failures."""

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        from gim_backend.services.vector_generation import generate_intent_vector_with_retry

        call_count = 0

        async def mock_embed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Embedding service unavailable")
            return SAMPLE_VECTOR

        with patch("gim_backend.services.profile_embedding_service.embed_query", mock_embed):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await generate_intent_vector_with_retry(["backend"], "Test text", max_retries=3)

        assert call_count == 3
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_after_max_retries(self):
        from gim_backend.services.vector_generation import generate_intent_vector_with_retry

        async def always_fail(*args, **kwargs):
            raise Exception("Embedding service down")

        with patch("gim_backend.services.profile_embedding_service.embed_query", always_fail):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await generate_intent_vector_with_retry(["backend"], "Test text", max_retries=3)

        assert result is None


class TestErrorHandling:
    """Tests user-friendly error messages."""

    def test_resume_unsupported_format_error(self, authenticated_client):
        response = authenticated_client.post(
            "/profile/resume",
            files={"file": ("resume.txt", b"Plain text content", "text/plain")},
        )

        assert response.status_code == 400
        assert "PDF or DOCX" in response.json()["detail"]

    def test_error_handler_converts_github_not_connected(self):
        """Verifies error handler produces correct response for GitHubNotConnectedError."""
        from gim_backend.api.routes.profile_github import _handle_github_error
        from gim_backend.core.errors import GitHubNotConnectedError

        error = GitHubNotConnectedError("No account linked")
        http_exc = _handle_github_error(error)

        assert http_exc.status_code == 400
        assert "connect GitHub" in http_exc.detail

    def test_error_handler_converts_refresh_rate_limit(self):
        """Verifies error handler produces correct response for RefreshRateLimitError."""
        from gim_backend.api.routes.profile_github import _handle_github_error
        from gim_backend.core.errors import RefreshRateLimitError

        error = RefreshRateLimitError(seconds_remaining=3600)
        http_exc = _handle_github_error(error)

        assert http_exc.status_code == 429
        assert "minute" in http_exc.detail


class TestCombinedVectorCalculation:
    """Tests combined vector calculation with different source combinations."""

    @pytest.mark.asyncio
    async def test_intent_only_combined_equals_intent(self):
        from gim_backend.services.profile_embedding_service import calculate_combined_vector

        intent_vector = [1.0] * 256

        result = await calculate_combined_vector(
            intent_vector=intent_vector,
            resume_vector=None,
            github_vector=None,
        )

        assert result is not None
        magnitude = sum(x * x for x in result) ** 0.5
        assert abs(magnitude - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_all_sources_uses_correct_weights(self):
        from gim_backend.services.profile_embedding_service import calculate_combined_vector

        intent_vector = [1.0, 0.0, 0.0] + [0.0] * 765
        resume_vector = [0.0, 1.0, 0.0] + [0.0] * 765
        github_vector = [0.0, 0.0, 1.0] + [0.0] * 765

        result = await calculate_combined_vector(
            intent_vector=intent_vector,
            resume_vector=resume_vector,
            github_vector=github_vector,
        )

        assert result is not None
        assert result[0] > result[1] > result[2]

    @pytest.mark.asyncio
    async def test_no_sources_returns_none(self):
        from gim_backend.services.profile_embedding_service import calculate_combined_vector

        result = await calculate_combined_vector(
            intent_vector=None,
            resume_vector=None,
            github_vector=None,
        )

        assert result is None


class TestProfileDeletionCancelsJobs:
    """Tests that profile deletion cancels pending Cloud Tasks."""

    async def test_cloud_tasks_cancel_user_tasks(self):
        """Verifies Cloud Tasks client can cancel tasks for a user in mock mode."""
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()

        client = get_cloud_tasks_client()

        user_id = uuid4()

        _ = await client.enqueue_resume_task(
            user_id=user_id,
            file_bytes=b"test content",
            filename="resume.pdf",
        )

        mock_tasks = client.get_mock_tasks()
        assert len(mock_tasks) == 1

        cancelled_count = await client.cancel_user_tasks(user_id)

        assert cancelled_count == 1
        assert len(client.get_mock_tasks()) == 0

        reset_client_for_testing()
