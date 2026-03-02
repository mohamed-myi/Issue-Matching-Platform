from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gim_backend.main import app
from gim_backend.middleware.auth import require_auth
from gim_backend.services.feed_service import FeedItem, FeedPage
from gim_backend.services.why_this_service import WhyThisItem


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authenticated_client(client):
    user = type("U", (), {"id": uuid4()})
    session = type("S", (), {"id": uuid4(), "user_id": user.id})

    def _mock_require_auth():
        return (user, session)

    app.dependency_overrides[require_auth] = _mock_require_auth
    yield client
    app.dependency_overrides.clear()


def _create_mock_feed(is_personalized: bool) -> FeedPage:
    item = FeedItem(
        node_id="issue_1",
        title="t",
        body_preview="b",
        labels=[],
        q_score=0.8,
        repo_name="r",
        primary_language="Python",
        repo_topics=[],
        github_created_at=datetime.now(UTC),
        similarity_score=0.9 if is_personalized else None,
        why_this=[WhyThisItem(entity="Python", score=3.0)] if is_personalized else None,
        freshness=None,
        final_score=None,
    )
    return FeedPage(
        results=[item],
        total=1,
        page=1,
        page_size=20,
        has_more=False,
        is_personalized=is_personalized,
        profile_cta=None,
    )


def test_feed_includes_why_this_only_when_personalized(authenticated_client):
    with patch("gim_backend.api.routes.feed.get_feed", return_value=_create_mock_feed(is_personalized=True)):
        resp = authenticated_client.get("/feed")
    assert resp.status_code == 200
    payload = resp.json()
    assert "recommendation_batch_id" in payload
    assert payload["results"][0]["why_this"][0]["entity"] == "Python"

    with patch("gim_backend.api.routes.feed.get_feed", return_value=_create_mock_feed(is_personalized=False)):
        resp2 = authenticated_client.get("/feed")
    assert resp2.status_code == 200
    payload2 = resp2.json()
    assert payload2["results"][0].get("why_this") is None
