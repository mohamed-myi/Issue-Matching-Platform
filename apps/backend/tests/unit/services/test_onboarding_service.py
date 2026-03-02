"""Unit tests for onboarding service step tracking and state transitions."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.exec = AsyncMock()
    return db


@pytest.fixture
def mock_profile():
    profile = MagicMock()
    profile.user_id = uuid4()
    profile.intent_text = None
    profile.resume_skills = None
    profile.github_username = None
    profile.preferred_languages = None
    profile.onboarding_status = "not_started"
    profile.onboarding_completed_at = None
    return profile


class TestCompletedSteps:
    """Tests for step completion detection logic."""

    def test_completed_steps_empty_when_no_data(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "not_started"
        mock_profile.intent_text = None
        mock_profile.github_username = None
        mock_profile.resume_skills = None
        mock_profile.preferred_languages = None

        steps = _get_completed_steps(mock_profile)

        assert steps == []

    def test_completed_steps_includes_welcome_when_in_progress(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"

        steps = _get_completed_steps(mock_profile)

        assert "welcome" in steps

    def test_completed_steps_includes_welcome_when_completed(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "completed"

        steps = _get_completed_steps(mock_profile)

        assert "welcome" in steps

    def test_completed_steps_includes_welcome_when_skipped(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "skipped"

        steps = _get_completed_steps(mock_profile)

        assert "welcome" in steps

    def test_completed_steps_includes_intent_when_populated(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.intent_text = "I want to contribute to open source"

        steps = _get_completed_steps(mock_profile)

        assert "intent" in steps

    def test_completed_steps_includes_github_when_populated(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.github_username = "octocat"

        steps = _get_completed_steps(mock_profile)

        assert "github" in steps

    def test_completed_steps_includes_resume_when_populated(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.resume_skills = ["Python", "FastAPI"]

        steps = _get_completed_steps(mock_profile)

        assert "resume" in steps

    def test_completed_steps_includes_preferences_when_languages_set(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.preferred_languages = ["Python", "TypeScript"]

        steps = _get_completed_steps(mock_profile)

        assert "preferences" in steps

    def test_all_steps_completed_when_all_populated(self, mock_profile):
        from gim_backend.services.onboarding_service import ALL_STEPS, _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.intent_text = "I want to contribute"
        mock_profile.github_username = "octocat"
        mock_profile.resume_skills = ["Python"]
        mock_profile.preferred_languages = ["Python"]

        steps = _get_completed_steps(mock_profile)

        assert set(steps) == set(ALL_STEPS)


class TestAvailableSteps:
    """Tests for available steps calculation."""

    def test_available_steps_returns_all_when_none_completed(self):
        from gim_backend.services.onboarding_service import ALL_STEPS, _get_available_steps

        available = _get_available_steps([])

        assert set(available) == set(ALL_STEPS)

    def test_available_steps_excludes_completed(self):
        from gim_backend.services.onboarding_service import _get_available_steps

        completed = ["welcome", "intent"]
        available = _get_available_steps(completed)

        assert "welcome" not in available
        assert "intent" not in available
        assert "github" in available
        assert "resume" in available
        assert "preferences" in available

    def test_available_steps_empty_when_all_completed(self):
        from gim_backend.services.onboarding_service import ALL_STEPS, _get_available_steps

        available = _get_available_steps(ALL_STEPS)

        assert available == []


class TestCanComplete:
    """Tests for can_complete calculation."""

    def test_can_complete_false_when_no_sources(self, mock_profile):
        from gim_backend.services.onboarding_service import _can_complete

        mock_profile.intent_text = None
        mock_profile.resume_skills = None
        mock_profile.github_username = None

        result = _can_complete(mock_profile)

        assert result is False

    def test_can_complete_true_with_intent_only(self, mock_profile):
        from gim_backend.services.onboarding_service import _can_complete

        mock_profile.intent_text = "I want to contribute"
        mock_profile.resume_skills = None
        mock_profile.github_username = None

        result = _can_complete(mock_profile)

        assert result is True

    def test_can_complete_true_with_resume_only(self, mock_profile):
        from gim_backend.services.onboarding_service import _can_complete

        mock_profile.intent_text = None
        mock_profile.resume_skills = ["Python", "FastAPI"]
        mock_profile.github_username = None

        result = _can_complete(mock_profile)

        assert result is True

    def test_can_complete_true_with_github_only(self, mock_profile):
        from gim_backend.services.onboarding_service import _can_complete

        mock_profile.intent_text = None
        mock_profile.resume_skills = None
        mock_profile.github_username = "octocat"

        result = _can_complete(mock_profile)

        assert result is True

    def test_can_complete_true_with_all_sources(self, mock_profile):
        from gim_backend.services.onboarding_service import _can_complete

        mock_profile.intent_text = "I want to contribute"
        mock_profile.resume_skills = ["Python"]
        mock_profile.github_username = "octocat"

        result = _can_complete(mock_profile)

        assert result is True


class TestComputeOnboardingState:
    """Tests for the composite state computation."""

    def test_compute_state_returns_all_fields(self, mock_profile):
        from gim_backend.services.onboarding_service import compute_onboarding_state

        state = compute_onboarding_state(mock_profile)

        assert hasattr(state, "status")
        assert hasattr(state, "completed_steps")
        assert hasattr(state, "available_steps")
        assert hasattr(state, "can_complete")

    def test_compute_state_not_started_profile(self, mock_profile):
        from gim_backend.services.onboarding_service import compute_onboarding_state

        mock_profile.onboarding_status = "not_started"

        state = compute_onboarding_state(mock_profile)

        assert state.status == "not_started"
        assert state.completed_steps == []
        assert "welcome" in state.available_steps
        assert state.can_complete is False

    def test_compute_state_in_progress_with_intent(self, mock_profile):
        from gim_backend.services.onboarding_service import compute_onboarding_state

        mock_profile.onboarding_status = "in_progress"
        mock_profile.intent_text = "I want to contribute"
        mock_profile.preferred_languages = ["Python"]

        state = compute_onboarding_state(mock_profile)

        assert state.status == "in_progress"
        assert "welcome" in state.completed_steps
        assert "intent" in state.completed_steps
        assert "preferences" in state.completed_steps
        assert state.can_complete is True


class TestCompleteOnboarding:
    """Tests for the complete_onboarding function."""

    @pytest.mark.asyncio
    async def test_complete_raises_when_no_sources(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import (
            CannotCompleteOnboardingError,
            complete_onboarding,
        )

        mock_profile.intent_text = None
        mock_profile.resume_skills = None
        mock_profile.github_username = None
        mock_profile.onboarding_status = "not_started"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            with pytest.raises(CannotCompleteOnboardingError):
                await complete_onboarding(mock_db, mock_profile.user_id)

    @pytest.mark.asyncio
    async def test_complete_succeeds_with_intent(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import complete_onboarding

        mock_profile.intent_text = "I want to contribute"
        mock_profile.onboarding_status = "in_progress"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            state = await complete_onboarding(mock_db, mock_profile.user_id)

        assert mock_profile.onboarding_status == "completed"
        assert mock_profile.onboarding_completed_at is not None
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_complete_raises_when_already_completed(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import (
            OnboardingAlreadyCompletedError,
            complete_onboarding,
        )

        mock_profile.intent_text = "I want to contribute"
        mock_profile.onboarding_status = "completed"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            with pytest.raises(OnboardingAlreadyCompletedError):
                await complete_onboarding(mock_db, mock_profile.user_id)

    @pytest.mark.asyncio
    async def test_complete_raises_when_already_skipped(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import (
            OnboardingAlreadyCompletedError,
            complete_onboarding,
        )

        mock_profile.intent_text = "I want to contribute"
        mock_profile.onboarding_status = "skipped"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            with pytest.raises(OnboardingAlreadyCompletedError):
                await complete_onboarding(mock_db, mock_profile.user_id)


class TestSkipOnboarding:
    """Tests for the skip_onboarding function."""

    @pytest.mark.asyncio
    async def test_skip_succeeds_without_sources(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import skip_onboarding

        mock_profile.intent_text = None
        mock_profile.resume_skills = None
        mock_profile.github_username = None
        mock_profile.onboarding_status = "not_started"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            state = await skip_onboarding(mock_db, mock_profile.user_id)

        assert mock_profile.onboarding_status == "skipped"
        assert mock_profile.onboarding_completed_at is not None
        assert state.status == "skipped"

    @pytest.mark.asyncio
    async def test_skip_raises_when_already_completed(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import (
            OnboardingAlreadyCompletedError,
            skip_onboarding,
        )

        mock_profile.onboarding_status = "completed"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            with pytest.raises(OnboardingAlreadyCompletedError):
                await skip_onboarding(mock_db, mock_profile.user_id)

    @pytest.mark.asyncio
    async def test_skip_raises_when_already_skipped(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import (
            OnboardingAlreadyCompletedError,
            skip_onboarding,
        )

        mock_profile.onboarding_status = "skipped"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            with pytest.raises(OnboardingAlreadyCompletedError):
                await skip_onboarding(mock_db, mock_profile.user_id)


class TestMarkOnboardingInProgress:
    """Tests for the mark_onboarding_in_progress function."""

    @pytest.mark.asyncio
    async def test_transitions_from_not_started(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import mark_onboarding_in_progress

        mock_profile.onboarding_status = "not_started"

        await mark_onboarding_in_progress(mock_db, mock_profile)

        assert mock_profile.onboarding_status == "in_progress"

    @pytest.mark.asyncio
    async def test_does_not_transition_from_in_progress(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import mark_onboarding_in_progress

        mock_profile.onboarding_status = "in_progress"

        await mark_onboarding_in_progress(mock_db, mock_profile)

        assert mock_profile.onboarding_status == "in_progress"

    @pytest.mark.asyncio
    async def test_does_not_transition_from_completed(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import mark_onboarding_in_progress

        mock_profile.onboarding_status = "completed"

        await mark_onboarding_in_progress(mock_db, mock_profile)

        assert mock_profile.onboarding_status == "completed"

    @pytest.mark.asyncio
    async def test_does_not_transition_from_skipped(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import mark_onboarding_in_progress

        mock_profile.onboarding_status = "skipped"

        await mark_onboarding_in_progress(mock_db, mock_profile)

        assert mock_profile.onboarding_status == "in_progress"
        assert mock_profile.onboarding_completed_at is None


class TestStartOnboarding:
    """Tests for the start_onboarding function."""

    @pytest.mark.asyncio
    async def test_start_transitions_not_started_to_in_progress(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import start_onboarding

        mock_profile.onboarding_status = "not_started"
        mock_profile.onboarding_completed_at = None

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await start_onboarding(mock_db, mock_profile.user_id)

        assert mock_profile.onboarding_status == "in_progress"
        assert result.action == "started"
        assert result.state.status == "in_progress"

    @pytest.mark.asyncio
    async def test_start_restarts_from_skipped(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import start_onboarding

        mock_profile.onboarding_status = "skipped"
        mock_profile.onboarding_completed_at = "2026-01-01T00:00:00Z"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await start_onboarding(mock_db, mock_profile.user_id)

        assert mock_profile.onboarding_status == "in_progress"
        assert mock_profile.onboarding_completed_at is None
        assert result.action == "restarted"
        assert result.state.status == "in_progress"

    @pytest.mark.asyncio
    async def test_start_noop_when_already_in_progress(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import start_onboarding

        mock_profile.onboarding_status = "in_progress"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await start_onboarding(mock_db, mock_profile.user_id)

        assert result.action == "noop"
        assert result.state.status == "in_progress"

    @pytest.mark.asyncio
    async def test_start_raises_when_completed(self, mock_db, mock_profile):
        from gim_backend.services.onboarding_service import OnboardingAlreadyCompletedError, start_onboarding

        mock_profile.onboarding_status = "completed"

        with patch(
            "gim_backend.services.onboarding_service._get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            with pytest.raises(OnboardingAlreadyCompletedError):
                await start_onboarding(mock_db, mock_profile.user_id)


class TestAnyOrderCompletion:
    """Tests verifying any-order completion works correctly."""

    def test_github_before_intent_shows_github_completed(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.github_username = "octocat"
        mock_profile.intent_text = None

        steps = _get_completed_steps(mock_profile)

        assert "github" in steps
        assert "intent" not in steps

    def test_resume_before_intent_shows_resume_completed(self, mock_profile):
        from gim_backend.services.onboarding_service import _get_completed_steps

        mock_profile.onboarding_status = "in_progress"
        mock_profile.resume_skills = ["Python", "FastAPI"]
        mock_profile.intent_text = None

        steps = _get_completed_steps(mock_profile)

        assert "resume" in steps
        assert "intent" not in steps

    def test_can_complete_with_github_only_no_intent(self, mock_profile):
        from gim_backend.services.onboarding_service import _can_complete

        mock_profile.github_username = "octocat"
        mock_profile.intent_text = None
        mock_profile.resume_skills = None

        result = _can_complete(mock_profile)

        assert result is True
