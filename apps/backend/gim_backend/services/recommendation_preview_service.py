"""
Recommendation preview service for onboarding flow.
"""

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.services.embedding_service import assert_vector_dim
from gim_backend.services.profile_service import get_or_create_profile

PREVIEW_LIMIT = 3
VALID_SOURCES = {"intent", "resume", "github"}


class InvalidSourceError(Exception):
    """Raised when an invalid source parameter is provided."""

    pass


class PreviewIssue(BaseModel):
    node_id: str
    title: str
    repo_name: str
    primary_language: str | None
    q_score: float


async def get_preview_recommendations(
    db: AsyncSession,
    user_id: UUID,
    source: str | None = None,
) -> list[PreviewIssue]:
    """Returns up to 3 issues using the specified source vector; falls back to trending if no vector."""
    if source is not None and source not in VALID_SOURCES:
        raise InvalidSourceError(f"Invalid source: '{source}'. Valid options: {', '.join(sorted(VALID_SOURCES))}")

    profile = await get_or_create_profile(db, user_id)

    source_vector = None
    if source == "intent":
        source_vector = profile.intent_vector
    elif source == "resume":
        source_vector = profile.resume_vector
    elif source == "github":
        source_vector = profile.github_vector

    if source_vector is not None:
        return await _query_by_vector_similarity(db, source_vector)

    return await _query_trending_issues(db)


async def _query_by_vector_similarity(
    db: AsyncSession,
    source_vector: list[float],
) -> list[PreviewIssue]:
    assert_vector_dim(source_vector, context="preview source_vector")
    sql = """
    SELECT
        i.node_id,
        i.title,
        r.full_name AS repo_name,
        r.primary_language,
        i.q_score
    FROM ingestion.issue i
    JOIN ingestion.repository r ON i.repo_id = r.node_id
    WHERE i.embedding IS NOT NULL AND i.state = 'open'
    ORDER BY i.embedding <=> CAST(:source_vec AS vector)
    LIMIT :limit
    """

    result = await db.execute(
        text(sql),
        {"source_vec": str(source_vector), "limit": PREVIEW_LIMIT},
    )
    rows = result.fetchall()

    return [
        PreviewIssue(
            node_id=row.node_id,
            title=row.title,
            repo_name=row.repo_name,
            primary_language=row.primary_language,
            q_score=float(row.q_score),
        )
        for row in rows
    ]


async def _query_trending_issues(
    db: AsyncSession,
) -> list[PreviewIssue]:
    """Trending defined as high q_score and recent github_created_at."""
    sql = """
    SELECT
        i.node_id,
        i.title,
        r.full_name AS repo_name,
        r.primary_language,
        i.q_score
    FROM ingestion.issue i
    JOIN ingestion.repository r ON i.repo_id = r.node_id
    WHERE i.q_score >= 0.6 AND i.state = 'open'
    ORDER BY i.q_score DESC, i.github_created_at DESC
    LIMIT :limit
    """

    result = await db.execute(text(sql), {"limit": PREVIEW_LIMIT})
    rows = result.fetchall()

    return [
        PreviewIssue(
            node_id=row.node_id,
            title=row.title,
            repo_name=row.repo_name,
            primary_language=row.primary_language,
            q_score=float(row.q_score),
        )
        for row in rows
    ]


__all__ = [
    "PreviewIssue",
    "InvalidSourceError",
    "get_preview_recommendations",
    "PREVIEW_LIMIT",
    "VALID_SOURCES",
]
