"""Integration tests for profile API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestAuthRequired:
    """Verifies authentication middleware is applied to all routes."""

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("get", "/profile", None),
            ("delete", "/profile", None),
            (
                "post",
                "/profile/intent",
                {"languages": ["Python"], "stack_areas": ["backend"], "text": "Some intent text"},
            ),
            (
                "put",
                "/profile/intent",
                {"languages": ["Python"], "stack_areas": ["backend"], "text": "Some intent text"},
            ),
            ("get", "/profile/intent", None),
            ("patch", "/profile/intent", {"text": "Updated text"}),
            ("delete", "/profile/intent", None),
            ("get", "/profile/processing-status", None),
            ("get", "/profile/preferences", None),
            ("patch", "/profile/preferences", {"min_heat_threshold": 0.7}),
        ],
    )
    def test_returns_401_without_auth(self, client, method, path, body):
        if body:
            response = getattr(client, method)(path, json=body)
        else:
            response = getattr(client, method)(path)
        assert response.status_code == 401


class TestIntentValidation:
    """Tests input validation rules for intent endpoints."""

    def test_rejects_text_under_min_length(self, authenticated_client):
        response = authenticated_client.post(
            "/profile/intent",
            json={
                "languages": ["Python"],
                "stack_areas": ["backend"],
                "text": "Short",
            },
        )
        assert response.status_code == 422

    def test_rejects_text_over_max_length(self, authenticated_client):
        response = authenticated_client.post(
            "/profile/intent",
            json={
                "languages": ["Python"],
                "stack_areas": ["backend"],
                "text": "x" * 2001,
            },
        )
        assert response.status_code == 422

    def test_rejects_empty_languages_list(self, authenticated_client):
        response = authenticated_client.post(
            "/profile/intent",
            json={
                "languages": [],
                "stack_areas": ["backend"],
                "text": "Some valid intent text",
            },
        )
        assert response.status_code == 422

    def test_rejects_languages_over_max_count(self, authenticated_client):
        response = authenticated_client.post(
            "/profile/intent",
            json={
                "languages": ["Python"] * 11,
                "stack_areas": ["backend"],
                "text": "Some valid intent text",
            },
        )
        assert response.status_code == 422

    def test_invalid_language_returns_400_with_detail(self, authenticated_client):
        from gim_backend.services.profile_service import InvalidTaxonomyValueError

        with patch("gim_backend.api.routes.profile.create_intent_service") as mock_create:
            mock_create.side_effect = InvalidTaxonomyValueError(
                field="language", invalid_value="Cobol", valid_options=["Python"]
            )

            response = authenticated_client.post(
                "/profile/intent",
                json={
                    "languages": ["Cobol"],
                    "stack_areas": ["backend"],
                    "text": "Some intent text here",
                },
            )

            assert response.status_code == 400
            assert "Cobol" in response.json()["detail"]

    def test_invalid_stack_area_returns_400_with_detail(self, authenticated_client):
        from gim_backend.services.profile_service import InvalidTaxonomyValueError

        with patch("gim_backend.api.routes.profile.create_intent_service") as mock_create:
            mock_create.side_effect = InvalidTaxonomyValueError(
                field="stack_area", invalid_value="hacking", valid_options=["backend"]
            )

            response = authenticated_client.post(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["hacking"],
                    "text": "Some intent text here",
                },
            )

            assert response.status_code == 400
            assert "hacking" in response.json()["detail"]


class TestPreferencesValidation:
    """Tests input validation rules for preferences endpoints."""

    def test_rejects_threshold_above_1(self, authenticated_client):
        response = authenticated_client.patch(
            "/profile/preferences",
            json={
                "min_heat_threshold": 1.5,
            },
        )
        assert response.status_code == 422

    def test_rejects_threshold_below_0(self, authenticated_client):
        response = authenticated_client.patch(
            "/profile/preferences",
            json={
                "min_heat_threshold": -0.1,
            },
        )
        assert response.status_code == 422

    def test_accepts_boundary_threshold_0(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.update_preferences_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = []
            mock_profile.preferred_topics = []
            mock_profile.min_heat_threshold = 0.0
            mock_update.return_value = mock_profile

            response = authenticated_client.patch(
                "/profile/preferences",
                json={
                    "min_heat_threshold": 0.0,
                },
            )
            assert response.status_code == 200

    def test_accepts_boundary_threshold_1(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.update_preferences_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = []
            mock_profile.preferred_topics = []
            mock_profile.min_heat_threshold = 1.0
            mock_update.return_value = mock_profile

            response = authenticated_client.patch(
                "/profile/preferences",
                json={
                    "min_heat_threshold": 1.0,
                },
            )
            assert response.status_code == 200


class TestConflictHandling:
    """Tests idempotency and conflict scenarios."""

    def test_create_intent_returns_409_when_exists(self, authenticated_client):
        from gim_backend.services.profile_service import IntentAlreadyExistsError

        with patch("gim_backend.api.routes.profile.create_intent_service") as mock_create:
            mock_create.side_effect = IntentAlreadyExistsError("Intent already exists")

            response = authenticated_client.post(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "Some intent text here",
                },
            )
            assert response.status_code == 409

    def test_get_intent_returns_404_when_missing(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.get_intent_service") as mock_get:
            mock_get.return_value = None

            response = authenticated_client.get("/profile/intent")
            assert response.status_code == 404

    def test_update_intent_returns_404_when_missing(self, authenticated_client):
        from gim_backend.services.profile_service import IntentNotFoundError

        with patch("gim_backend.api.routes.profile.update_intent_service") as mock_update:
            mock_update.side_effect = IntentNotFoundError("No intent exists")

            response = authenticated_client.patch(
                "/profile/intent",
                json={
                    "text": "Updated text here",
                },
            )
            assert response.status_code == 404

    def test_delete_intent_returns_404_when_missing(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.delete_intent_service") as mock_delete:
            mock_delete.return_value = False

            response = authenticated_client.delete("/profile/intent")
            assert response.status_code == 404


class TestResponseStructure:
    """Verifies API response shapes match specification."""

    def test_get_profile_returns_complete_structure(self, authenticated_client, mock_user):
        with patch("gim_backend.api.routes.profile.get_full_profile") as mock_get:
            mock_get.return_value = {
                "user_id": str(mock_user.id),
                "optimization_percent": 50,
                "combined_vector_status": None,
                "is_calculating": False,
                "onboarding_status": "not_started",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": {
                    "intent": {
                        "populated": True,
                        "vector_status": None,
                        "data": {
                            "languages": ["Python"],
                            "stack_areas": ["backend"],
                            "text": "Test intent",
                            "experience_level": "intermediate",
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    },
                    "resume": {"populated": False, "vector_status": None, "data": None},
                    "github": {"populated": False, "vector_status": None, "data": None},
                },
                "preferences": {
                    "preferred_languages": ["Python"],
                    "preferred_topics": [],
                    "min_heat_threshold": 0.6,
                },
            }

            response = authenticated_client.get("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["optimization_percent"] == 50
            assert data["sources"]["intent"]["populated"] is True
            assert data["sources"]["resume"]["populated"] is False
            assert data["preferences"]["min_heat_threshold"] == 0.6

    def test_create_intent_returns_201(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.create_intent_service") as mock_create:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.intent_stack_areas = ["backend"]
            mock_profile.intent_text = "Test intent"
            mock_profile.intent_experience = None
            mock_profile.intent_vector = None
            mock_profile.updated_at = datetime.now(UTC)
            mock_create.return_value = mock_profile

            response = authenticated_client.post(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "Test intent text here",
                },
            )

            assert response.status_code == 201


class TestPutIntent:
    """Integration tests for PUT /profile/intent."""

    def test_returns_201_when_created(self, authenticated_client):
        from gim_database.models.profiles import UserProfile

        mock_profile = MagicMock(spec=UserProfile)
        mock_profile.preferred_languages = ["Python"]
        mock_profile.intent_stack_areas = ["backend"]
        mock_profile.intent_text = "Test intent"
        mock_profile.intent_experience = None
        mock_profile.intent_vector = [0.1] * 256
        mock_profile.updated_at = datetime.now(UTC)

        with patch(
            "gim_backend.api.routes.profile.put_intent_service",
            return_value=(mock_profile, True),
        ):
            response = authenticated_client.put(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "Test intent text here",
                    "experience_level": None,
                },
            )

        assert response.status_code == 201
        assert response.json()["languages"] == ["Python"]

    def test_returns_200_when_replaced(self, authenticated_client):
        from gim_database.models.profiles import UserProfile

        mock_profile = MagicMock(spec=UserProfile)
        mock_profile.preferred_languages = ["Python"]
        mock_profile.intent_stack_areas = ["backend"]
        mock_profile.intent_text = "Test intent"
        mock_profile.intent_experience = "intermediate"
        mock_profile.intent_vector = [0.1] * 256
        mock_profile.updated_at = datetime.now(UTC)

        with patch(
            "gim_backend.api.routes.profile.put_intent_service",
            return_value=(mock_profile, False),
        ):
            response = authenticated_client.put(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "Test intent text here",
                    "experience_level": "intermediate",
                },
            )

        assert response.status_code == 200


class TestProcessingStatus:
    """Integration tests for GET /profile/processing-status."""

    def test_returns_not_started(self, authenticated_client):
        mock_profile = MagicMock()
        mock_profile.is_calculating = False
        mock_profile.intent_text = None
        mock_profile.resume_skills = None
        mock_profile.github_username = None
        mock_profile.intent_vector = None
        mock_profile.resume_vector = None
        mock_profile.github_vector = None
        mock_profile.combined_vector = None

        with patch(
            "gim_backend.api.routes.profile.get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            response = authenticated_client.get("/profile/processing-status")

        assert response.status_code == 200
        data = response.json()
        assert data["intent_status"] == "not_started"
        assert data["resume_status"] == "not_started"
        assert data["github_status"] == "not_started"

    def test_returns_processing_for_intent(self, authenticated_client):
        mock_profile = MagicMock()
        mock_profile.is_calculating = True
        mock_profile.intent_text = "Some intent"
        mock_profile.resume_skills = None
        mock_profile.github_username = None
        mock_profile.intent_vector = None
        mock_profile.resume_vector = None
        mock_profile.github_vector = None
        mock_profile.combined_vector = None

        with patch(
            "gim_backend.api.routes.profile.get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            response = authenticated_client.get("/profile/processing-status")

        assert response.status_code == 200
        assert response.json()["intent_status"] == "processing"

    def test_returns_failed_for_intent(self, authenticated_client):
        mock_profile = MagicMock()
        mock_profile.is_calculating = False
        mock_profile.intent_text = "Some intent"
        mock_profile.resume_skills = None
        mock_profile.github_username = None
        mock_profile.intent_vector = None
        mock_profile.resume_vector = None
        mock_profile.github_vector = None
        mock_profile.combined_vector = None

        with patch(
            "gim_backend.api.routes.profile.get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            response = authenticated_client.get("/profile/processing-status")

        assert response.status_code == 200
        assert response.json()["intent_status"] == "failed"

    def test_returns_ready_for_intent_and_combined(self, authenticated_client):
        mock_profile = MagicMock()
        mock_profile.is_calculating = False
        mock_profile.intent_text = "Some intent"
        mock_profile.resume_skills = None
        mock_profile.github_username = None
        mock_profile.intent_vector = [0.1] * 256
        mock_profile.resume_vector = None
        mock_profile.github_vector = None
        mock_profile.combined_vector = [0.2] * 256

        with patch(
            "gim_backend.api.routes.profile.get_or_create_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            response = authenticated_client.get("/profile/processing-status")

        assert response.status_code == 200
        data = response.json()
        assert data["intent_status"] == "ready"
        assert data["intent_vector_status"] == "ready"
        assert data["combined_vector_status"] == "ready"


class TestPatchSemantics:
    """Tests partial update behavior for PATCH endpoints."""

    def test_patch_intent_updates_only_provided_field(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.update_intent_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.intent_stack_areas = ["backend"]
            mock_profile.intent_text = "Original text"
            mock_profile.intent_experience = "advanced"
            mock_profile.intent_vector = None
            mock_profile.updated_at = datetime.now(UTC)
            mock_update.return_value = mock_profile

            response = authenticated_client.patch(
                "/profile/intent",
                json={
                    "experience_level": "advanced",
                },
            )

            assert response.status_code == 200
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["experience_level"] == "advanced"
            assert call_kwargs["_experience_level_provided"] is True

    def test_patch_intent_distinguishes_null_from_omitted(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.update_intent_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.intent_stack_areas = ["backend"]
            mock_profile.intent_text = "Original text"
            mock_profile.intent_experience = None
            mock_profile.intent_vector = None
            mock_profile.updated_at = datetime.now(UTC)
            mock_update.return_value = mock_profile

            _ = authenticated_client.patch(
                "/profile/intent",
                json={
                    "experience_level": None,
                },
            )

            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["_experience_level_provided"] is True
            assert call_kwargs["experience_level"] is None

    def test_patch_preferences_updates_only_provided_field(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.update_preferences_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.preferred_topics = []
            mock_profile.min_heat_threshold = 0.8
            mock_update.return_value = mock_profile

            response = authenticated_client.patch(
                "/profile/preferences",
                json={
                    "min_heat_threshold": 0.8,
                },
            )

            assert response.status_code == 200
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["min_heat_threshold"] == 0.8
            assert call_kwargs["preferred_languages"] is None


class TestDeleteBehavior:
    """Tests deletion semantics for profile and intent."""

    def test_delete_profile_returns_deleted_status(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.delete_profile_service") as mock_delete:
            mock_delete.return_value = True

            response = authenticated_client.delete("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["deleted"] is True

    def test_delete_profile_indicates_no_data_cleared(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.delete_profile_service") as mock_delete:
            mock_delete.return_value = False

            response = authenticated_client.delete("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["deleted"] is False

    def test_delete_intent_returns_deleted_status(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.delete_intent_service") as mock_delete:
            mock_delete.return_value = True

            response = authenticated_client.delete("/profile/intent")
            data = response.json()

            assert response.status_code == 200
            assert data["deleted"] is True


class TestVectorGeneration:
    """Verifies vector generation integration during intent CRUD."""

    def test_create_intent_generates_intent_vector(self, authenticated_client):
        mock_vector = [0.1] * 256

        with patch("gim_backend.api.routes.profile.create_intent_service") as mock_create:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.intent_stack_areas = ["backend"]
            mock_profile.intent_text = "I want to contribute to Python projects"
            mock_profile.intent_experience = None
            mock_profile.intent_vector = mock_vector
            mock_profile.updated_at = datetime.now(UTC)
            mock_create.return_value = mock_profile

            response = authenticated_client.post(
                "/profile/intent",
                json={
                    "languages": ["Python"],
                    "stack_areas": ["backend"],
                    "text": "I want to contribute to Python projects",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["vector_status"] == "ready"

    def test_create_intent_generates_combined_vector_when_intent_only(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.get_full_profile") as mock_get:
            mock_get.return_value = {
                "user_id": str(uuid4()),
                "optimization_percent": 50,
                "combined_vector_status": "ready",
                "is_calculating": False,
                "onboarding_status": "not_started",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": {
                    "intent": {
                        "populated": True,
                        "vector_status": "ready",
                        "data": {
                            "languages": ["Python"],
                            "stack_areas": ["backend"],
                            "text": "Test intent",
                            "experience_level": None,
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    },
                    "resume": {"populated": False, "vector_status": None, "data": None},
                    "github": {"populated": False, "vector_status": None, "data": None},
                },
                "preferences": {
                    "preferred_languages": ["Python"],
                    "preferred_topics": [],
                    "min_heat_threshold": 0.6,
                },
            }

            response = authenticated_client.get("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["combined_vector_status"] == "ready"
            assert data["sources"]["intent"]["vector_status"] == "ready"

    def test_update_intent_regenerates_vector_when_text_changes(self, authenticated_client):
        mock_vector = [0.2] * 256

        with patch("gim_backend.api.routes.profile.update_intent_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.intent_stack_areas = ["backend"]
            mock_profile.intent_text = "Updated intent text here"
            mock_profile.intent_experience = None
            mock_profile.intent_vector = mock_vector
            mock_profile.updated_at = datetime.now(UTC)
            mock_update.return_value = mock_profile

            response = authenticated_client.patch(
                "/profile/intent",
                json={
                    "text": "Updated intent text here",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["vector_status"] == "ready"

    def test_update_intent_regenerates_vector_when_stack_areas_change(self, authenticated_client):
        mock_vector = [0.3] * 256

        with patch("gim_backend.api.routes.profile.update_intent_service") as mock_update:
            mock_profile = MagicMock()
            mock_profile.preferred_languages = ["Python"]
            mock_profile.intent_stack_areas = ["frontend", "backend"]
            mock_profile.intent_text = "Original text"
            mock_profile.intent_experience = None
            mock_profile.intent_vector = mock_vector
            mock_profile.updated_at = datetime.now(UTC)
            mock_update.return_value = mock_profile

            response = authenticated_client.patch(
                "/profile/intent",
                json={
                    "stack_areas": ["frontend", "backend"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["vector_status"] == "ready"

    def test_delete_intent_recalculates_combined_vector(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.delete_intent_service") as mock_delete:
            mock_delete.return_value = True

            response = authenticated_client.delete("/profile/intent")

            assert response.status_code == 200
            mock_delete.assert_called_once()

    def test_combined_vector_becomes_none_when_all_sources_deleted(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.get_full_profile") as mock_get:
            mock_get.return_value = {
                "user_id": str(uuid4()),
                "optimization_percent": 0,
                "combined_vector_status": None,
                "is_calculating": False,
                "onboarding_status": "not_started",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": {
                    "intent": {"populated": False, "vector_status": None, "data": None},
                    "resume": {"populated": False, "vector_status": None, "data": None},
                    "github": {"populated": False, "vector_status": None, "data": None},
                },
                "preferences": {
                    "preferred_languages": [],
                    "preferred_topics": [],
                    "min_heat_threshold": 0.6,
                },
            }

            response = authenticated_client.get("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["combined_vector_status"] is None
            assert data["optimization_percent"] == 0


class TestIsCalculatingFlag:
    """Verifies is_calculating flag state transitions."""

    def test_profile_shows_calculating_state(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.get_full_profile") as mock_get:
            mock_get.return_value = {
                "user_id": str(uuid4()),
                "optimization_percent": 50,
                "combined_vector_status": None,
                "is_calculating": True,
                "onboarding_status": "not_started",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": {
                    "intent": {
                        "populated": True,
                        "vector_status": None,
                        "data": {
                            "languages": ["Python"],
                            "stack_areas": ["backend"],
                            "text": "Test",
                            "experience_level": None,
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    },
                    "resume": {"populated": False, "vector_status": None, "data": None},
                    "github": {"populated": False, "vector_status": None, "data": None},
                },
                "preferences": {
                    "preferred_languages": ["Python"],
                    "preferred_topics": [],
                    "min_heat_threshold": 0.6,
                },
            }

            response = authenticated_client.get("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["is_calculating"] is True

    def test_profile_shows_not_calculating_after_completion(self, authenticated_client):
        with patch("gim_backend.api.routes.profile.get_full_profile") as mock_get:
            mock_get.return_value = {
                "user_id": str(uuid4()),
                "optimization_percent": 50,
                "combined_vector_status": "ready",
                "is_calculating": False,
                "onboarding_status": "not_started",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": {
                    "intent": {
                        "populated": True,
                        "vector_status": "ready",
                        "data": {
                            "languages": ["Python"],
                            "stack_areas": ["backend"],
                            "text": "Test",
                            "experience_level": None,
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    },
                    "resume": {"populated": False, "vector_status": None, "data": None},
                    "github": {"populated": False, "vector_status": None, "data": None},
                },
                "preferences": {
                    "preferred_languages": ["Python"],
                    "preferred_topics": [],
                    "min_heat_threshold": 0.6,
                },
            }

            response = authenticated_client.get("/profile")
            data = response.json()

            assert response.status_code == 200
            assert data["is_calculating"] is False
            assert data["combined_vector_status"] == "ready"
