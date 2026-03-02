"""Integration tests for onboarding API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuthRequired:
    """Verifies authentication middleware is applied to onboarding routes."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/profile/onboarding"),
            ("post", "/profile/onboarding/start"),
            ("patch", "/profile/onboarding/step/welcome"),
            ("patch", "/profile/onboarding/step/intent"),
            ("patch", "/profile/onboarding/step/preferences"),
            ("post", "/profile/onboarding/complete"),
            ("post", "/profile/onboarding/skip"),
            ("get", "/profile/preview-recommendations"),
        ],
    )
    def test_returns_401_without_auth(self, client, method, path):
        if method == "patch" and path.endswith("/intent"):
            response = getattr(client, method)(
                path,
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "I want to contribute to open source Python projects",
                },
            )
        elif method == "patch" and path.endswith("/preferences"):
            response = getattr(client, method)(path, json={"min_heat_threshold": 0.7})
        else:
            response = getattr(client, method)(path)
        assert response.status_code == 401


class TestGetOnboarding:
    """Tests for GET /profile/onboarding endpoint."""

    def test_returns_not_started_for_new_user(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="not_started",
            completed_steps=[],
            available_steps=["welcome", "intent", "github", "resume", "preferences"],
            can_complete=False,
        )

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
            new_callable=AsyncMock,
            return_value=mock_state,
        ):
            response = authenticated_client.get("/profile/onboarding")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_started"
        assert data["completed_steps"] == []
        assert data["can_complete"] is False

    def test_returns_in_progress_with_intent(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome", "intent", "preferences"],
            available_steps=["github", "resume"],
            can_complete=True,
        )

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
            new_callable=AsyncMock,
            return_value=mock_state,
        ):
            response = authenticated_client.get("/profile/onboarding")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert "welcome" in data["completed_steps"]
        assert "intent" in data["completed_steps"]
        assert data["can_complete"] is True

    def test_returns_completed_status(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="completed",
            completed_steps=["welcome", "intent", "preferences"],
            available_steps=["github", "resume"],
            can_complete=True,
        )

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
            new_callable=AsyncMock,
            return_value=mock_state,
        ):
            response = authenticated_client.get("/profile/onboarding")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"


class TestCompleteOnboarding:
    """Tests for POST /profile/onboarding/complete endpoint."""

    def test_complete_succeeds_with_source(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="completed",
            completed_steps=["welcome", "intent", "preferences"],
            available_steps=["github", "resume"],
            can_complete=True,
        )

        with patch(
            "gim_backend.api.routes.profile_onboarding.complete_onboarding",
            new_callable=AsyncMock,
            return_value=mock_state,
        ):
            response = authenticated_client.post("/profile/onboarding/complete")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_complete_fails_without_sources(self, authenticated_client):
        from gim_backend.services.onboarding_service import CannotCompleteOnboardingError

        with patch(
            "gim_backend.api.routes.profile_onboarding.complete_onboarding",
            new_callable=AsyncMock,
            side_effect=CannotCompleteOnboardingError("Cannot complete without sources"),
        ):
            response = authenticated_client.post("/profile/onboarding/complete")

        assert response.status_code == 400
        assert "Cannot complete" in response.json()["detail"]

    def test_complete_returns_409_when_already_completed(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingAlreadyCompletedError

        with patch(
            "gim_backend.api.routes.profile_onboarding.complete_onboarding",
            new_callable=AsyncMock,
            side_effect=OnboardingAlreadyCompletedError("Onboarding already completed"),
        ):
            response = authenticated_client.post("/profile/onboarding/complete")

        assert response.status_code == 409
        assert "already" in response.json()["detail"]


class TestSkipOnboarding:
    """Tests for POST /profile/onboarding/skip endpoint."""

    def test_skip_succeeds_without_sources(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="skipped",
            completed_steps=["welcome"],
            available_steps=["intent", "github", "resume", "preferences"],
            can_complete=False,
        )

        with patch(
            "gim_backend.api.routes.profile_onboarding.skip_onboarding",
            new_callable=AsyncMock,
            return_value=mock_state,
        ):
            response = authenticated_client.post("/profile/onboarding/skip")

        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    def test_skip_returns_409_when_already_skipped(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingAlreadyCompletedError

        with patch(
            "gim_backend.api.routes.profile_onboarding.skip_onboarding",
            new_callable=AsyncMock,
            side_effect=OnboardingAlreadyCompletedError("Onboarding already skipped"),
        ):
            response = authenticated_client.post("/profile/onboarding/skip")

        assert response.status_code == 409


class TestPreviewRecommendations:
    """Tests for GET /profile/preview-recommendations endpoint."""

    def test_returns_issues_with_intent_vector(self, authenticated_client):
        from gim_backend.services.recommendation_preview_service import PreviewIssue

        mock_issues = [
            PreviewIssue(
                node_id="MDU6SXNzdWUx",
                title="Fix async bug",
                repo_name="fastapi/fastapi",
                primary_language="Python",
                q_score=0.85,
            ),
            PreviewIssue(
                node_id="MDU6SXNzdWUy",
                title="Add TypeScript support",
                repo_name="vercel/next.js",
                primary_language="TypeScript",
                q_score=0.78,
            ),
            PreviewIssue(
                node_id="MDU6SXNzdWUz",
                title="Improve error handling",
                repo_name="rust-lang/rust",
                primary_language="Rust",
                q_score=0.72,
            ),
        ]

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_preview_recommendations",
            new_callable=AsyncMock,
            return_value=mock_issues,
        ):
            response = authenticated_client.get("/profile/preview-recommendations?source=intent")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "intent"
        assert len(data["issues"]) == 3
        assert data["issues"][0]["title"] == "Fix async bug"
        assert data["issues"][0]["q_score"] == 0.85

    def test_returns_empty_without_vector(self, authenticated_client):
        with patch(
            "gim_backend.api.routes.profile_onboarding.get_preview_recommendations",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = authenticated_client.get("/profile/preview-recommendations?source=intent")

        assert response.status_code == 200
        assert response.json()["issues"] == []

    def test_returns_trending_when_no_source(self, authenticated_client):
        from gim_backend.services.recommendation_preview_service import PreviewIssue

        mock_issues = [
            PreviewIssue(
                node_id="MDU6SXNzdWUx",
                title="Trending issue",
                repo_name="popular/repo",
                primary_language="Python",
                q_score=0.95,
            ),
        ]

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_preview_recommendations",
            new_callable=AsyncMock,
            return_value=mock_issues,
        ):
            response = authenticated_client.get("/profile/preview-recommendations")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] is None
        assert len(data["issues"]) == 1

    def test_validates_source_parameter(self, authenticated_client):
        from gim_backend.services.recommendation_preview_service import InvalidSourceError

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_preview_recommendations",
            new_callable=AsyncMock,
            side_effect=InvalidSourceError("Invalid source: 'invalid'"),
        ):
            response = authenticated_client.get("/profile/preview-recommendations?source=invalid")

        assert response.status_code == 400
        assert "Invalid source" in response.json()["detail"]

    def test_accepts_resume_source(self, authenticated_client):
        with patch(
            "gim_backend.api.routes.profile_onboarding.get_preview_recommendations",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = authenticated_client.get("/profile/preview-recommendations?source=resume")

        assert response.status_code == 200
        assert response.json()["source"] == "resume"

    def test_accepts_github_source(self, authenticated_client):
        with patch(
            "gim_backend.api.routes.profile_onboarding.get_preview_recommendations",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = authenticated_client.get("/profile/preview-recommendations?source=github")

        assert response.status_code == 200
        assert response.json()["source"] == "github"


class TestOnboardingAfterIntentCreate:
    """Integration tests verifying onboarding updates after intent creation."""

    def test_creating_intent_transitions_onboarding_to_in_progress(self, authenticated_client):
        """
        Verifies that creating intent via POST /profile/intent
        transitions onboarding status from not_started to in_progress.
        """
        from gim_database.models.profiles import UserProfile

        from gim_backend.services.onboarding_service import OnboardingState

        mock_profile = MagicMock(spec=UserProfile)
        mock_profile.intent_text = "I want to contribute"
        mock_profile.intent_stack_areas = ["backend"]
        mock_profile.intent_experience = "intermediate"
        mock_profile.intent_vector = [0.1] * 256
        mock_profile.preferred_languages = ["Python"]
        mock_profile.updated_at = datetime.now(UTC)
        mock_profile.onboarding_status = "in_progress"

        with patch(
            "gim_backend.api.routes.profile.create_intent_service",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            response = authenticated_client.post(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "I want to contribute to open source Python projects",
                    "experience_level": "intermediate",
                },
            )

        assert response.status_code == 201

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome", "intent", "preferences"],
            available_steps=["github", "resume"],
            can_complete=True,
        )

        with patch(
            "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
            new_callable=AsyncMock,
            return_value=mock_state,
        ):
            onboarding_response = authenticated_client.get("/profile/onboarding")

        assert onboarding_response.status_code == 200
        data = onboarding_response.json()
        assert data["status"] == "in_progress"
        assert "intent" in data["completed_steps"]


class TestStartOnboarding:
    """Tests for POST /profile/onboarding/start endpoint."""

    def test_start_returns_action_and_state(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingStartResult, OnboardingState

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome"],
            available_steps=["intent", "github", "resume", "preferences"],
            can_complete=False,
        )
        mock_result = OnboardingStartResult(state=mock_state, action="started")

        with patch(
            "gim_backend.api.routes.profile_onboarding.start_onboarding",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = authenticated_client.post("/profile/onboarding/start")

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "started"
        assert data["status"] == "in_progress"

    def test_start_returns_409_when_completed(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingAlreadyCompletedError

        with patch(
            "gim_backend.api.routes.profile_onboarding.start_onboarding",
            new_callable=AsyncMock,
            side_effect=OnboardingAlreadyCompletedError("Onboarding already completed"),
        ):
            response = authenticated_client.post("/profile/onboarding/start")

        assert response.status_code == 409

    def test_start_can_restart_from_skipped(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingStartResult, OnboardingState

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome"],
            available_steps=["intent", "github", "resume", "preferences"],
            can_complete=False,
        )
        mock_result = OnboardingStartResult(state=mock_state, action="restarted")

        with patch(
            "gim_backend.api.routes.profile_onboarding.start_onboarding",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = authenticated_client.post("/profile/onboarding/start")

        assert response.status_code == 200
        assert response.json()["action"] == "restarted"


class TestOnboardingStep:
    """Tests for PATCH /profile/onboarding/step/{step} endpoint."""

    def test_invalid_step_returns_400(self, authenticated_client):
        response = authenticated_client.patch("/profile/onboarding/step/invalid", json={})
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid onboarding step"}

    def test_welcome_step_behaves_like_start(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingStartResult, OnboardingState

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome"],
            available_steps=["intent", "github", "resume", "preferences"],
            can_complete=False,
        )

        with (
            patch(
                "gim_backend.api.routes.profile_onboarding.start_onboarding",
                new_callable=AsyncMock,
                return_value=OnboardingStartResult(state=mock_state, action="noop"),
            ),
            patch(
                "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
                new_callable=AsyncMock,
                return_value=mock_state,
            ),
        ):
            response = authenticated_client.patch("/profile/onboarding/step/welcome")

        assert response.status_code == 200
        data = response.json()
        assert data["step"] == "welcome"
        assert data["payload"]["action"] == "noop"
        assert data["status"] == "in_progress"

    def test_intent_step_saves_intent_and_returns_payload(self, authenticated_client):
        from datetime import datetime

        from gim_database.models.profiles import UserProfile

        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome", "intent"],
            available_steps=["github", "resume", "preferences"],
            can_complete=True,
        )

        mock_profile = MagicMock(spec=UserProfile)
        mock_profile.preferred_languages = ["Python"]
        mock_profile.intent_stack_areas = ["backend"]
        mock_profile.intent_text = "I want to contribute"
        mock_profile.intent_experience = None
        mock_profile.intent_vector = [0.1] * 256
        mock_profile.updated_at = datetime.now(UTC)

        with (
            patch(
                "gim_backend.api.routes.profile_onboarding.put_intent_service",
                new_callable=AsyncMock,
                return_value=(mock_profile, True),
            ),
            patch(
                "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
                new_callable=AsyncMock,
                return_value=mock_state,
            ),
        ):
            response = authenticated_client.patch(
                "/profile/onboarding/step/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "I want to contribute",
                    "experience_level": None,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["step"] == "intent"
        assert data["payload"]["created"] is True
        assert data["payload"]["intent"]["languages"] == ["Python"]

    def test_preferences_step_rejects_empty_payload(self, authenticated_client):
        response = authenticated_client.patch("/profile/onboarding/step/preferences", json={})
        assert response.status_code == 400

    def test_preferences_step_saves_and_returns_payload(self, authenticated_client):
        from gim_backend.services.onboarding_service import OnboardingState

        mock_state = OnboardingState(
            status="in_progress",
            completed_steps=["welcome", "preferences"],
            available_steps=["intent", "github", "resume"],
            can_complete=False,
        )

        mock_profile = MagicMock()
        mock_profile.preferred_languages = ["Python"]
        mock_profile.preferred_topics = ["async"]
        mock_profile.min_heat_threshold = 0.7

        with (
            patch(
                "gim_backend.api.routes.profile_onboarding.update_preferences_service",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
            patch(
                "gim_backend.api.routes.profile_onboarding.get_onboarding_status",
                new_callable=AsyncMock,
                return_value=mock_state,
            ),
        ):
            response = authenticated_client.patch(
                "/profile/onboarding/step/preferences",
                json={
                    "preferred_languages": ["Python"],
                    "preferred_topics": ["async"],
                    "min_heat_threshold": 0.7,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["step"] == "preferences"
        assert data["payload"]["preferences"]["min_heat_threshold"] == 0.7
