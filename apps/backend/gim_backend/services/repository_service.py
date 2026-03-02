"""
Repository service for repository listing and filtering.
Used for search filter dropdowns and repository discovery.
"""

import logging

from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class RepositoryItem(BaseModel):
    """Repository summary with issue count."""

    name: str  # full_name like "facebook/react"
    primary_language: str | None
    issue_count: int


def _escape_like_pattern(value: str) -> str:
    """
    Escapes SQL LIKE/ILIKE special characters to treat them as literals.
    Prevents wildcard injection (%, _).
    """
    # Escape backslash first, then the special characters
    value = value.replace("\\", "\\\\")
    value = value.replace("%", "\\%")
    value = value.replace("_", "\\_")
    return value


async def list_repositories(
    db: AsyncSession,
    language: str | None = None,
    search_query: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[RepositoryItem]:
    """
    Lists repositories with optional language and search filters.

    Args:
        db: Database session
        language: Filter by primary_language (case-insensitive)
        search_query: Search in full_name (case-insensitive, wildcards escaped)
        limit: Max results (clamped to MAX_LIMIT)

    Returns:
        List of repositories ordered by stargazer_count DESC
    """
    if limit < 1:
        limit = DEFAULT_LIMIT
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    # Build dynamic WHERE clause
    conditions = []
    params: dict = {"limit": limit}

    if language:
        # Case-insensitive language match
        conditions.append("LOWER(r.primary_language) = LOWER(:language)")
        params["language"] = language

    if search_query:
        # Escape special characters and use ILIKE for case-insensitive search
        escaped_query = _escape_like_pattern(search_query)
        conditions.append("r.full_name ILIKE :search_pattern ESCAPE '\\\\'")
        params["search_pattern"] = f"%{escaped_query}%"

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Use subquery for issue_count to optimize performance
    # Only counts open issues for relevance
    sql = f"""
    SELECT
        r.full_name AS name,
        r.primary_language,
        COALESCE(ic.issue_count, 0) AS issue_count
    FROM ingestion.repository r
    LEFT JOIN (
        SELECT repo_id, COUNT(*) AS issue_count
        FROM ingestion.issue
        WHERE state = 'open'
        GROUP BY repo_id
    ) ic ON ic.repo_id = r.node_id
    {where_clause}
    ORDER BY r.stargazer_count DESC, r.full_name ASC
    LIMIT :limit
    """

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return [
        RepositoryItem(
            name=row.name,
            primary_language=row.primary_language,
            issue_count=int(row.issue_count),
        )
        for row in rows
    ]


__all__ = [
    "RepositoryItem",
    "list_repositories",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
]
