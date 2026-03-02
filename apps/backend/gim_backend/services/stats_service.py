"""
Stats service for platform statistics.
Provides aggregated counts for landing page trust signals.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.redis import get_redis

logger = logging.getLogger(__name__)


STATS_CACHE_KEY = "platform:stats"
STATS_CACHE_TTL = 3600  # 1 hour


@dataclass
class PlatformStats:
    """Platform statistics for landing page."""

    total_issues: int
    total_repos: int
    total_languages: int
    indexed_at: datetime | None


async def get_platform_stats(db: AsyncSession) -> PlatformStats:
    """
    Returns platform statistics, cached with 1-hour TTL.

    Counts:
    - total_issues: Open issues only (consistent with user-facing surfaces)
    - total_repos: All indexed repositories
    - total_languages: Distinct primary languages
    - indexed_at: Most recent repository scrape timestamp
    """
    # Try cache first
    redis = await get_redis()
    if redis:
        try:
            cached = await redis.hgetall(STATS_CACHE_KEY)
            if cached:
                logger.debug("Stats cache hit")
                return PlatformStats(
                    total_issues=int(cached.get(b"total_issues", cached.get("total_issues", 0))),
                    total_repos=int(cached.get(b"total_repos", cached.get("total_repos", 0))),
                    total_languages=int(cached.get(b"total_languages", cached.get("total_languages", 0))),
                    indexed_at=datetime.fromisoformat(
                        (cached.get(b"indexed_at") or cached.get("indexed_at", b"")).decode()
                        if isinstance(cached.get(b"indexed_at", cached.get("indexed_at")), bytes)
                        else cached.get("indexed_at", "")
                    )
                    if cached.get(b"indexed_at") or cached.get("indexed_at")
                    else None,
                )
        except Exception as e:
            logger.warning(f"Stats cache read failed: {e}")

    # Query database
    stats = await _query_stats(db)

    # Cache results
    if redis and stats:
        try:
            cache_data = {
                "total_issues": str(stats.total_issues),
                "total_repos": str(stats.total_repos),
                "total_languages": str(stats.total_languages),
                "indexed_at": stats.indexed_at.isoformat() if stats.indexed_at else "",
            }
            await redis.hset(STATS_CACHE_KEY, mapping=cache_data)
            await redis.expire(STATS_CACHE_KEY, STATS_CACHE_TTL)
            logger.debug("Stats cached")
        except Exception as e:
            logger.warning(f"Stats cache write failed: {e}")

    return stats


async def _query_stats(db: AsyncSession) -> PlatformStats:
    """Execute statistics queries against database."""

    # Count open issues
    issue_sql = """
    SELECT COUNT(*) as total
    FROM ingestion.issue
    WHERE state = 'open'
    """
    issue_result = await db.execute(text(issue_sql))
    total_issues = issue_result.scalar() or 0

    # Count repositories
    repo_sql = """
    SELECT COUNT(*) as total
    FROM ingestion.repository
    """
    repo_result = await db.execute(text(repo_sql))
    total_repos = repo_result.scalar() or 0

    # Count distinct languages
    lang_sql = """
    SELECT COUNT(DISTINCT primary_language) as total
    FROM ingestion.repository
    WHERE primary_language IS NOT NULL
    """
    lang_result = await db.execute(text(lang_sql))
    total_languages = lang_result.scalar() or 0

    # Get most recent scrape time
    scrape_sql = """
    SELECT MAX(last_scraped_at) as latest
    FROM ingestion.repository
    """
    scrape_result = await db.execute(text(scrape_sql))
    indexed_at = scrape_result.scalar()

    logger.info(f"Stats queried: {total_issues} issues, {total_repos} repos, {total_languages} languages")

    return PlatformStats(
        total_issues=total_issues,
        total_repos=total_repos,
        total_languages=total_languages,
        indexed_at=indexed_at,
    )


__all__ = [
    "PlatformStats",
    "get_platform_stats",
    "STATS_CACHE_TTL",
]
