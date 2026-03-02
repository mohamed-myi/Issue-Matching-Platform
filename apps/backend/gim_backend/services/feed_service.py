"""
Feed service for personalized issue recommendations.
Uses combined_vector for similarity search; falls back to trending when no profile.
"""

import logging
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.config import get_settings
from gim_backend.services.embedding_service import assert_vector_dim
from gim_backend.services.profile_service import get_or_create_profile
from gim_backend.services.why_this_service import WhyThisItem, compute_why_this

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 50
CANDIDATE_LIMIT: int = 200

TRENDING_CTA = "These are trending issues. Complete your profile for personalized recommendations."


async def _count_feed_total(db: AsyncSession, where_clause: str, params: dict) -> int:
    count_sql = f"""
    SELECT COUNT(*) as total
    FROM ingestion.issue i
    JOIN ingestion.repository r ON i.repo_id = r.node_id
    WHERE {where_clause}
    """
    count_result = await db.execute(text(count_sql), params)
    return int(count_result.scalar() or 0)


def _build_feed_filters(
    *,
    min_q_score: float,
    languages: list[str] | None = None,
    labels: list[str] | None = None,
    repos: list[str] | None = None,
    require_embedding: bool = False,
) -> tuple[str, dict]:
    """Builds shared WHERE clause fragments and params for feed/trending queries."""
    filter_conditions = ["i.state = 'open'"]
    if require_embedding:
        filter_conditions.insert(0, "i.embedding IS NOT NULL")

    params: dict = {"min_q_score": min_q_score}
    filter_conditions.append("i.q_score >= :min_q_score")

    if languages:
        filter_conditions.append("r.primary_language = ANY(:langs)")
        params["langs"] = languages

    if labels:
        filter_conditions.append("i.labels && :labels")
        params["labels"] = labels

    if repos:
        filter_conditions.append("r.full_name = ANY(:repos)")
        params["repos"] = repos

    return " AND ".join(filter_conditions), params


class FeedItem(BaseModel):
    node_id: str
    title: str
    body_preview: str
    github_url: str | None = None
    labels: list[str]
    q_score: float
    repo_name: str
    primary_language: str | None
    repo_topics: list[str]
    github_created_at: datetime
    similarity_score: float | None
    why_this: list[WhyThisItem] | None = None
    freshness: float | None = None
    final_score: float | None = None


def _to_optional_float(value) -> float | None:
    return float(value) if value is not None else None


def _row_to_feed_item(row, *, include_personalized_scores: bool) -> FeedItem:
    """Shared row->DTO mapper used by personalized and trending feed paths."""
    return FeedItem(
        node_id=row.node_id,
        title=row.title,
        body_preview=row.body_text[:500] if row.body_text else "",
        github_url=row.github_url,
        labels=row.labels or [],
        q_score=float(row.q_score),
        repo_name=row.repo_name,
        primary_language=row.primary_language,
        repo_topics=list(row.repo_topics or []),
        github_created_at=row.github_created_at,
        similarity_score=(
            _to_optional_float(getattr(row, "similarity_score", None))
            if include_personalized_scores
            else None
        ),
        freshness=(
            _to_optional_float(getattr(row, "freshness", None))
            if include_personalized_scores
            else None
        ),
        final_score=(
            _to_optional_float(getattr(row, "final_score", None))
            if include_personalized_scores
            else None
        ),
        why_this=None,
    )


def freshness_decay(
    *,
    age_days: float,
    half_life_days: float,
    floor: float,
) -> float:
    if half_life_days <= 0:
        return max(0.0, min(1.0, floor))
    if age_days <= 0:
        return 1.0
    base = pow(0.5, age_days / half_life_days)
    return max(floor, float(base))


class FeedPage(BaseModel):
    results: list[FeedItem]
    total: int
    page: int
    page_size: int
    has_more: bool
    is_personalized: bool
    profile_cta: str | None


async def get_feed(
    db: AsyncSession,
    user_id: UUID,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    languages: list[str] | None = None,
    labels: list[str] | None = None,
    repos: list[str] | None = None,
) -> FeedPage:
    """
    Returns personalized feed using combined_vector; falls back to trending.
    Applies preferred_languages and min_heat_threshold filters when personalized.

    Filter params override profile preferences when provided.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = DEFAULT_PAGE_SIZE
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    profile = await get_or_create_profile(db, user_id)

    if profile.combined_vector is not None:
        return await _get_personalized_feed(
            db=db,
            profile=profile,
            combined_vector=profile.combined_vector,
            preferred_languages=languages or profile.preferred_languages,
            min_heat_threshold=profile.min_heat_threshold,
            page=page,
            page_size=page_size,
            labels=labels,
            repos=repos,
        )

    return await _get_trending_feed(
        db=db,
        page=page,
        page_size=page_size,
        languages=languages,
        labels=labels,
        repos=repos,
    )


async def _get_personalized_feed(
    db: AsyncSession,
    profile,
    combined_vector: list[float],
    preferred_languages: list[str] | None,
    min_heat_threshold: float,
    page: int,
    page_size: int,
    labels: list[str] | None = None,
    repos: list[str] | None = None,
) -> FeedPage:
    """Vector similarity search against issue embeddings with preference filters."""
    settings = get_settings()
    offset = (page - 1) * page_size
    assert_vector_dim(combined_vector, context="personalized feed combined_vector")

    params: dict = {
        "combined_vec": str(combined_vector),
        "limit": CANDIDATE_LIMIT,
        "offset": offset,
        "page_size": page_size,
        "freshness_half_life_days": float(settings.feed_freshness_half_life_days),
        "freshness_floor": float(settings.feed_freshness_floor),
        "freshness_weight": float(settings.feed_freshness_weight),
    }
    where_clause, filter_params = _build_feed_filters(
        min_q_score=min_heat_threshold,
        languages=preferred_languages,
        labels=labels,
        repos=repos,
        require_embedding=True,
    )
    params.update(filter_params)

    sql = f"""
    SELECT
        i.node_id,
        i.title,
        i.body_text,
        i.github_url,
        i.labels,
        i.q_score,
        i.github_created_at,
        r.full_name AS repo_name,
        r.primary_language,
        r.topics AS repo_topics,
        1 - (i.embedding <=> CAST(:combined_vec AS vector)) AS similarity_score,
        GREATEST(
            :freshness_floor,
            POWER(
                0.5,
                (
                    EXTRACT(EPOCH FROM (NOW() - GREATEST(i.ingested_at, i.github_created_at))) / 86400.0
                ) / :freshness_half_life_days
            )
        ) AS freshness,
        (
            (1 - (i.embedding <=> CAST(:combined_vec AS vector))) +
            (:freshness_weight * GREATEST(
                :freshness_floor,
                POWER(
                    0.5,
                    (
                        EXTRACT(EPOCH FROM (NOW() - GREATEST(i.ingested_at, i.github_created_at))) / 86400.0
                    ) / :freshness_half_life_days
                )
            ))
        ) AS final_score,
        COUNT(*) OVER() AS total_count
    FROM ingestion.issue i
    JOIN ingestion.repository r ON i.repo_id = r.node_id
    WHERE {where_clause}
    ORDER BY final_score DESC, i.q_score DESC, i.node_id ASC
    LIMIT :page_size
    OFFSET :offset
    """

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    if not rows:
        total = 0 if page == 1 else await _count_feed_total(db, where_clause, params)
        return FeedPage(
            results=[],
            total=total,
            page=page,
            page_size=page_size,
            has_more=False,
            is_personalized=True,
            profile_cta=None,
        )

    total = int(rows[0].total_count or 0)

    results = [_row_to_feed_item(row, include_personalized_scores=True) for row in rows]

    for item in results:
        item.why_this = compute_why_this(
            profile=profile,
            issue_title=item.title,
            issue_body_preview=item.body_preview,
            issue_labels=item.labels,
            repo_primary_language=item.primary_language,
            repo_topics=item.repo_topics,
            top_k=3,
        )
        if not settings.feed_debug_freshness:
            item.freshness = None
            item.final_score = None

    has_more = (offset + len(results)) < total

    logger.info(f"Personalized feed: user has combined_vector, returned {len(results)} of {total}")

    return FeedPage(
        results=results,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        is_personalized=True,
        profile_cta=None,
    )


async def _get_trending_feed(
    db: AsyncSession,
    page: int,
    page_size: int,
    languages: list[str] | None = None,
    labels: list[str] | None = None,
    repos: list[str] | None = None,
) -> FeedPage:
    """Trending issues: high q_score, recent, open, with optional filters."""
    offset = (page - 1) * page_size
    min_q_score = 0.6

    params: dict = {
        "limit": CANDIDATE_LIMIT,
        "offset": offset,
        "page_size": page_size,
    }
    where_clause, filter_params = _build_feed_filters(
        min_q_score=min_q_score,
        languages=languages,
        labels=labels,
        repos=repos,
    )
    params.update(filter_params)

    sql = f"""
    SELECT
        i.node_id,
        i.title,
        i.body_text,
        i.github_url,
        i.labels,
        i.q_score,
        i.github_created_at,
        r.full_name AS repo_name,
        r.primary_language,
        r.topics AS repo_topics,
        COUNT(*) OVER() AS total_count
    FROM ingestion.issue i
    JOIN ingestion.repository r ON i.repo_id = r.node_id
    WHERE {where_clause}
    ORDER BY i.q_score DESC, i.github_created_at DESC
    LIMIT :page_size
    OFFSET :offset
    """

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    if not rows:
        total = 0 if page == 1 else await _count_feed_total(db, where_clause, params)
        return FeedPage(
            results=[],
            total=total,
            page=page,
            page_size=page_size,
            has_more=False,
            is_personalized=False,
            profile_cta=TRENDING_CTA,
        )

    total = int(rows[0].total_count or 0)

    results = [_row_to_feed_item(row, include_personalized_scores=False) for row in rows]

    has_more = (offset + len(results)) < total

    logger.info(
        f"Trending feed: returned {len(results)} of {total}, "
        f"filters: langs={bool(languages)}, labels={bool(labels)}, repos={bool(repos)}"
    )

    return FeedPage(
        results=results,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        is_personalized=False,
        profile_cta=TRENDING_CTA,
    )


__all__ = [
    "FeedItem",
    "FeedPage",
    "get_feed",
    "freshness_decay",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "TRENDING_CTA",
]
