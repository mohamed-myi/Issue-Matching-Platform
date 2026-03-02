from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gim_backend.main import app
from gim_backend.middleware.auth import require_auth


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


class TestRecommendationEventsRoute:
    def test_returns_404_when_context_missing(self, authenticated_client):
        batch_id = uuid4()
        with patch(
            "gim_backend.api.routes.recommendations.get_recommendation_batch_context", new=AsyncMock(return_value=None)
        ):
            resp = authenticated_client.post(
                "/recommendations/events",
                json={
                    "recommendation_batch_id": str(batch_id),
                    "events": [
                        {
                            "event_id": str(uuid4()),
                            "event_type": "impression",
                            "issue_node_id": "x",
                            "position": 1,
                            "surface": "feed",
                        }
                    ],
                },
            )
        assert resp.status_code == 404

    def test_returns_503_when_redis_unavailable(self, authenticated_client):
        batch_id = uuid4()
        ctx = type("C", (), {"recommendation_batch_id": batch_id, "issue_node_ids": ["x"], "is_personalized": True})
        with patch(
            "gim_backend.api.routes.recommendations.get_recommendation_batch_context", new=AsyncMock(return_value=ctx)
        ):
            with patch(
                "gim_backend.api.routes.recommendations.enqueue_recommendation_events",
                new=AsyncMock(side_effect=RuntimeError("Redis unavailable")),
            ):
                resp = authenticated_client.post(
                    "/recommendations/events",
                    json={
                        "recommendation_batch_id": str(batch_id),
                        "events": [
                            {
                                "event_id": str(uuid4()),
                                "event_type": "impression",
                                "issue_node_id": "x",
                                "position": 1,
                                "surface": "feed",
                            }
                        ],
                    },
                )
        assert resp.status_code == 503
