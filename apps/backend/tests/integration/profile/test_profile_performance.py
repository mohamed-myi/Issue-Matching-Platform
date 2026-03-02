"""
Performance tests for Profile Engine.
Verify timing benchmarks:
    Intent vector: < 3 seconds
    Resume parsing: < 30 seconds
    GitHub fetch: < 15 seconds
    GET /profile: < 100ms
"""

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_user_email() -> str:
    return "perf@example.com"


def create_mock_profile(user_id):
    profile = MagicMock()
    profile.user_id = user_id
    profile.intent_text = None
    profile.intent_stack_areas = None
    profile.intent_experience = None
    profile.intent_vector = None
    profile.resume_skills = None
    profile.resume_job_titles = None
    profile.resume_vector = None
    profile.resume_uploaded_at = None
    profile.resume_raw_entities = None
    profile.github_username = None
    profile.github_languages = None
    profile.github_topics = None
    profile.github_vector = None
    profile.github_data = None
    profile.github_fetched_at = None
    profile.combined_vector = None
    profile.preferred_languages = None
    profile.preferred_topics = None
    profile.min_heat_threshold = 0.6
    profile.is_calculating = False
    profile.onboarding_status = "not_started"
    profile.onboarding_completed_at = None
    profile.updated_at = datetime.now(UTC)
    return profile


class TestGetProfilePerformance:
    """GET /profile should respond under 100ms."""

    @patch("gim_backend.services.profile_service.get_or_create_profile")
    def test_get_profile_under_100ms(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(mock_user.id)
        mock_get_profile.return_value = mock_profile

        iterations = 10
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            response = authenticated_client.get("/profile")
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            assert response.status_code == 200

        avg_time = sum(times) / len(times)
        p95_time = sorted(times)[int(len(times) * 0.95)]

        assert avg_time < 100, f"Average response time {avg_time:.2f}ms exceeds 100ms target"
        assert p95_time < 150, f"P95 response time {p95_time:.2f}ms exceeds 150ms"


class TestFeedPerformance:
    """GET /feed should respond under 200ms for routing and service layer."""

    @patch("gim_backend.services.feed_service.get_or_create_profile")
    def test_feed_routing_under_200ms(self, mock_get_profile, authenticated_client, mock_user):
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

            iterations = 10
            times = []

            for _ in range(iterations):
                start = time.perf_counter()
                response = authenticated_client.get("/feed")
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
                assert response.status_code == 200

            avg_time = sum(times) / len(times)

            assert avg_time < 200, f"Average response time {avg_time:.2f}ms exceeds 200ms target"


class TestVectorGenerationTiming:
    """Tests timing targets for vector generation operations."""

    @pytest.mark.asyncio
    async def test_intent_vector_generation_under_3s(self):
        """Intent vector should generate under 3 seconds (mocked embedding)."""
        from gim_backend.services.profile_embedding_service import generate_intent_vector

        with patch("gim_backend.services.profile_embedding_service.embed_query") as mock_embed:
            mock_embed.return_value = [0.01] * 256

            start = time.perf_counter()
            result = await generate_intent_vector(
                ["backend", "data_engineering"],
                "I want to contribute to Python async libraries and API frameworks",
            )
            elapsed = time.perf_counter() - start

            assert result is not None
            assert elapsed < 3.0, f"Intent vector took {elapsed:.2f}s, exceeds 3s target"

    @pytest.mark.asyncio
    async def test_combined_vector_calculation_under_1s(self):
        """Combined vector calculation should be under 1 second."""
        from gim_backend.services.profile_embedding_service import calculate_combined_vector

        intent_vec = [0.01] * 256
        resume_vec = [0.02] * 256
        github_vec = [0.03] * 256

        iterations = 100
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            result = await calculate_combined_vector(
                intent_vector=intent_vec,
                resume_vector=resume_vec,
                github_vector=github_vec,
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            assert result is not None

        avg_time = sum(times) / len(times)

        assert avg_time < 0.01, f"Average combined vector time {avg_time * 1000:.2f}ms exceeds 10ms"


class TestCloudTasksPerformance:
    """Tests Cloud Tasks operations are non-blocking in mock mode."""

    @pytest.mark.asyncio
    async def test_enqueue_is_fast(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()
        user_id = uuid4()

        iterations = 100
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            await client.enqueue_resume_task(
                user_id=user_id,
                file_bytes=b"test content",
                filename="resume.pdf",
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        assert avg_time < 0.01, f"Average enqueue time {avg_time * 1000:.2f}ms exceeds 10ms"

        reset_client_for_testing()

    @pytest.mark.asyncio
    async def test_cancel_user_tasks_is_fast(self):
        from gim_backend.services.cloud_tasks_service import (
            get_cloud_tasks_client,
            reset_client_for_testing,
        )

        reset_client_for_testing()
        client = get_cloud_tasks_client()
        user_id = uuid4()

        start = time.perf_counter()
        _ = await client.cancel_user_tasks(user_id)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.01, f"Cancel tasks took {elapsed * 1000:.2f}ms"

        reset_client_for_testing()


class TestOnboardingEndpointPerformance:
    """Tests onboarding endpoints respond quickly."""

    @patch("gim_backend.services.onboarding_service._get_or_create_profile")
    def test_get_onboarding_under_100ms(self, mock_get_profile, authenticated_client, mock_user):
        mock_profile = create_mock_profile(mock_user.id)
        mock_get_profile.return_value = mock_profile

        iterations = 10
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            response = authenticated_client.get("/profile/onboarding")
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            assert response.status_code == 200

        avg_time = sum(times) / len(times)

        assert avg_time < 100, f"Average onboarding GET time {avg_time:.2f}ms exceeds 100ms"
