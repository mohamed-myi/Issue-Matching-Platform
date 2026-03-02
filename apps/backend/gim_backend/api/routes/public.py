"""
Public API routes for unauthenticated access.
Landing page content: trending issues and platform statistics.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.services.feed_service import MAX_PAGE_SIZE, _get_trending_feed
from gim_backend.services.stats_service import get_platform_stats

router = APIRouter()


PUBLIC_TRENDING_DEFAULT = 10


class TrendingItemOutput(BaseModel):
    """Single issue in the trending feed."""

    node_id: str
    title: str
    body_preview: str
    github_url: str | None
    labels: list[str]
    q_score: float
    repo_name: str
    primary_language: str | None
    github_created_at: str


class TrendingResponse(BaseModel):
    """Public trending issues response."""

    results: list[TrendingItemOutput]
    total: int
    page: int
    page_size: int
    has_more: bool


class StatsResponse(BaseModel):
    """Platform statistics for landing page."""

    total_issues: int = Field(description="Total open issues indexed")
    total_repos: int = Field(description="Total repositories indexed")
    total_languages: int = Field(description="Distinct programming languages")
    indexed_at: str | None = Field(
        default=None,
        description="Most recent index update timestamp",
    )


@router.get("/feed/trending", response_model=TrendingResponse)
async def get_trending_route(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(
        default=PUBLIC_TRENDING_DEFAULT,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Results per page",
    ),
    languages: list[str] = Query(default=[], description="Filter by programming languages"),
    labels: list[str] = Query(default=[], description="Filter by issue labels"),
    repos: list[str] = Query(default=[], description="Filter by repository full names"),
    db: AsyncSession = Depends(get_db),
) -> TrendingResponse:
    """
    Returns trending issues for landing page preview and authenticated Browse/Dashboard.

    No authentication required.
    Returns recent open issues ordered by q_score with optional filters.
    Defaults to 10 items for backward compatibility with landing page.

    Use authenticated /feed endpoint for full personalized recommendations.
    """
    feed = await _get_trending_feed(
        db=db,
        page=page,
        page_size=page_size,
        languages=languages or None,
        labels=labels or None,
        repos=repos or None,
    )

    return TrendingResponse(
        results=[
            TrendingItemOutput(
                node_id=item.node_id,
                title=item.title,
                body_preview=item.body_preview,
                github_url=getattr(item, "github_url", None),
                labels=item.labels,
                q_score=item.q_score,
                repo_name=item.repo_name,
                primary_language=item.primary_language,
                github_created_at=item.github_created_at.isoformat(),
            )
            for item in feed.results
        ],
        total=feed.total,
        page=feed.page,
        page_size=feed.page_size,
        has_more=feed.has_more,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats_route(
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """
    Returns platform statistics for landing page.

    No authentication required.
    Statistics are cached with 1-hour TTL.

    Used for signals like "10,000+ issues indexed".
    """
    stats = await get_platform_stats(db)

    return StatsResponse(
        total_issues=stats.total_issues,
        total_repos=stats.total_repos,
        total_languages=stats.total_languages,
        indexed_at=stats.indexed_at.isoformat() if stats.indexed_at else None,
    )
