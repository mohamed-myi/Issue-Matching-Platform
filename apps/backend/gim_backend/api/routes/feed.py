"""
Feed API route for personalized issue recommendations.
Uses combined_vector for similarity; falls back to trending when no profile.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from gim_database.models.identity import Session, User
from pydantic import Field
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.middleware.auth import require_auth
from gim_backend.services.feed_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    FeedPage,
    get_feed,
)
from gim_backend.services.recommendation_event_service import (
    generate_recommendation_batch_id,
    store_recommendation_batch_context,
)

router = APIRouter()


class FeedResponse(FeedPage):
    """Paginated feed response with personalization metadata."""

    recommendation_batch_id: str = Field(
        description="Server generated identifier for logging impressions and clicks for this response.",
    )


@router.get("", response_model=FeedResponse)
async def get_feed_route(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Results per page",
    ),
    languages: list[str] = Query(
        default=[], description="Filter by programming languages (overrides profile preferences)"
    ),
    labels: list[str] = Query(default=[], description="Filter by issue labels"),
    repos: list[str] = Query(default=[], description="Filter by repository full names"),
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    """
    Returns personalized issue recommendations based on user profile.

    When the user has a combined_vector (from intent, resume, or GitHub data),
    issues are ranked by vector similarity with preference filters applied.

    When no profile data exists, returns trending issues (high quality, recent)
    with a call to action to complete the profile.

    Pagination:
        page: 1-indexed page number
        page_size: results per page (max 50)

    Filters:
        languages, labels, repos: When provided, override profile preferences for this request

    Response includes:
        is_personalized: true if using profile-based ranking
        profile_cta: message shown when using trending fallback
        similarity_score: cosine similarity for personalized results (null for trending)
    """
    user, _ = auth

    feed = await get_feed(
        db=db,
        user_id=user.id,
        page=page,
        page_size=page_size,
        languages=languages or None,
        labels=labels or None,
        repos=repos or None,
    )

    recommendation_batch_id = generate_recommendation_batch_id()
    served_at = datetime.now(UTC)
    issue_node_ids = [item.node_id for item in feed.results]
    await store_recommendation_batch_context(
        recommendation_batch_id=recommendation_batch_id,
        issue_node_ids=issue_node_ids,
        page=feed.page,
        page_size=feed.page_size,
        is_personalized=feed.is_personalized,
        served_at=served_at,
    )

    return FeedResponse(
        recommendation_batch_id=str(recommendation_batch_id),
        **feed.model_dump(),
    )
