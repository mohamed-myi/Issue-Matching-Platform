"""
Integration tests for taxonomy API routes.
Tests /taxonomy/languages and /taxonomy/stack-areas without authentication.
"""

import pytest
from fastapi.testclient import TestClient
from gim_shared.constants import PROFILE_LANGUAGES, STACK_AREAS

from gim_backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestLanguagesRoute:
    """Tests for GET /taxonomy/languages."""

    def test_languages_returns_200_without_auth(self, client):
        """Languages endpoint works without authentication."""
        response = client.get("/taxonomy/languages")
        assert response.status_code == 200

    def test_languages_returns_expected_structure(self, client):
        """Response has 'languages' field."""
        response = client.get("/taxonomy/languages")
        data = response.json()
        assert "languages" in data

    def test_languages_is_list(self, client):
        """Languages field is a list."""
        response = client.get("/taxonomy/languages")
        data = response.json()
        assert isinstance(data["languages"], list)

    def test_languages_contains_python(self, client):
        """Python is in the language list."""
        response = client.get("/taxonomy/languages")
        data = response.json()
        assert "Python" in data["languages"]

    def test_languages_contains_typescript(self, client):
        """TypeScript is in the language list."""
        response = client.get("/taxonomy/languages")
        data = response.json()
        assert "TypeScript" in data["languages"]

    def test_languages_count_matches_source(self, client):
        """Count matches PROFILE_LANGUAGES."""
        response = client.get("/taxonomy/languages")
        data = response.json()
        assert len(data["languages"]) == len(PROFILE_LANGUAGES)

    def test_languages_matches_source(self, client):
        """Languages match PROFILE_LANGUAGES exactly."""
        response = client.get("/taxonomy/languages")
        data = response.json()
        assert data["languages"] == list(PROFILE_LANGUAGES)


class TestStackAreasRoute:
    """Tests for GET /taxonomy/stack-areas."""

    def test_stack_areas_returns_200_without_auth(self, client):
        """Stack areas endpoint works without authentication."""
        response = client.get("/taxonomy/stack-areas")
        assert response.status_code == 200

    def test_stack_areas_returns_expected_structure(self, client):
        """Response has 'stack_areas' field."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        assert "stack_areas" in data

    def test_stack_areas_is_list(self, client):
        """Stack areas field is a list."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        assert isinstance(data["stack_areas"], list)

    def test_stack_areas_count_matches_source(self, client):
        """Count matches STACK_AREAS."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        assert len(data["stack_areas"]) == len(STACK_AREAS)

    def test_stack_areas_have_id(self, client):
        """Each area has an id."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        for area in data["stack_areas"]:
            assert "id" in area
            assert area["id"]

    def test_stack_areas_have_label(self, client):
        """Each area has a label."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        for area in data["stack_areas"]:
            assert "label" in area
            assert area["label"]

    def test_stack_areas_have_description(self, client):
        """Each area has a description."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        for area in data["stack_areas"]:
            assert "description" in area
            assert area["description"]

    def test_backend_exists(self, client):
        """Backend stack area exists."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        ids = [a["id"] for a in data["stack_areas"]]
        assert "backend" in ids

    def test_frontend_exists(self, client):
        """Frontend stack area exists."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        ids = [a["id"] for a in data["stack_areas"]]
        assert "frontend" in ids

    def test_backend_has_correct_description(self, client):
        """Backend has correct description from source."""
        response = client.get("/taxonomy/stack-areas")
        data = response.json()
        backend = next(a for a in data["stack_areas"] if a["id"] == "backend")
        assert backend["description"] == STACK_AREAS["backend"]
