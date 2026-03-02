"""
Unit tests for stats service.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.services.stats_service import (
    STATS_CACHE_KEY,
    STATS_CACHE_TTL,
    PlatformStats,
    _query_stats,
    get_platform_stats,
)


class MockScalarResult:
    """Mock for database scalar results."""

    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = MagicMock(spec=AsyncSession)
    return db


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    return redis


class TestQueryStats:
    """Tests for _query_stats function."""

    @pytest.mark.asyncio
    async def test_returns_platform_stats(self, mock_db):
        """Returns PlatformStats dataclass."""
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(1000),  # issues
                MockScalarResult(50),  # repos
                MockScalarResult(10),  # languages
                MockScalarResult(datetime(2026, 1, 9, 12, 0, 0, tzinfo=UTC)),  # indexed_at
            ]
        )

        result = await _query_stats(mock_db)

        assert isinstance(result, PlatformStats)
        assert result.total_issues == 1000
        assert result.total_repos == 50
        assert result.total_languages == 10
        assert result.indexed_at is not None

    @pytest.mark.asyncio
    async def test_handles_empty_database(self, mock_db):
        """Handles empty database gracefully."""
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(0),  # issues
                MockScalarResult(0),  # repos
                MockScalarResult(0),  # languages
                MockScalarResult(None),  # indexed_at
            ]
        )

        result = await _query_stats(mock_db)

        assert result.total_issues == 0
        assert result.total_repos == 0
        assert result.total_languages == 0
        assert result.indexed_at is None

    @pytest.mark.asyncio
    async def test_handles_null_scalars(self, mock_db):
        """Handles null scalar results."""
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(None),  # issues
                MockScalarResult(None),  # repos
                MockScalarResult(None),  # languages
                MockScalarResult(None),  # indexed_at
            ]
        )

        result = await _query_stats(mock_db)

        assert result.total_issues == 0
        assert result.total_repos == 0
        assert result.total_languages == 0


class TestGetPlatformStats:
    """Tests for get_platform_stats with caching."""

    @pytest.mark.asyncio
    async def test_returns_stats_without_redis(self, mock_db):
        """Works when Redis is unavailable."""
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(100),
                MockScalarResult(10),
                MockScalarResult(5),
                MockScalarResult(None),
            ]
        )

        with patch("gim_backend.services.stats_service.get_redis", return_value=None):
            result = await get_platform_stats(mock_db)

        assert result.total_issues == 100
        assert result.total_repos == 10
        assert result.total_languages == 5

    @pytest.mark.asyncio
    async def test_uses_cache_when_available(self, mock_db, mock_redis):
        """Returns cached data when available."""
        cached_data = {
            "total_issues": "500",
            "total_repos": "25",
            "total_languages": "8",
            "indexed_at": "2026-01-09T10:00:00+00:00",
        }
        mock_redis.hgetall = AsyncMock(return_value=cached_data)

        with patch("gim_backend.services.stats_service.get_redis", return_value=mock_redis):
            result = await get_platform_stats(mock_db)

        assert result.total_issues == 500
        assert result.total_repos == 25
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_caches_results_after_query(self, mock_db, mock_redis):
        """Caches results after querying database."""
        mock_redis.hgetall = AsyncMock(return_value={})  # Cache miss
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(200),
                MockScalarResult(20),
                MockScalarResult(6),
                MockScalarResult(datetime(2026, 1, 9, 12, 0, 0, tzinfo=UTC)),
            ]
        )

        with patch("gim_backend.services.stats_service.get_redis", return_value=mock_redis):
            await get_platform_stats(mock_db)

        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once_with(STATS_CACHE_KEY, STATS_CACHE_TTL)

    @pytest.mark.asyncio
    async def test_handles_cache_read_error(self, mock_db, mock_redis):
        """Falls back to DB when cache read fails."""
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis error"))
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(100),
                MockScalarResult(10),
                MockScalarResult(5),
                MockScalarResult(None),
            ]
        )

        with patch("gim_backend.services.stats_service.get_redis", return_value=mock_redis):
            result = await get_platform_stats(mock_db)

        assert result.total_issues == 100

    @pytest.mark.asyncio
    async def test_handles_cache_write_error(self, mock_db, mock_redis):
        """Continues when cache write fails."""
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.hset = AsyncMock(side_effect=Exception("Redis error"))
        mock_db.execute = AsyncMock(
            side_effect=[
                MockScalarResult(100),
                MockScalarResult(10),
                MockScalarResult(5),
                MockScalarResult(None),
            ]
        )

        with patch("gim_backend.services.stats_service.get_redis", return_value=mock_redis):
            result = await get_platform_stats(mock_db)

        assert result.total_issues == 100
