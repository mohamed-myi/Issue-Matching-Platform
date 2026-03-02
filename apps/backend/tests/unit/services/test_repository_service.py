"""Unit tests for repository_service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gim_backend.services.repository_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    RepositoryItem,
    _escape_like_pattern,
    list_repositories,
)


class TestEscapeLikePattern:
    """Tests for SQL LIKE pattern escaping."""

    def test_escapes_percent_wildcard(self):
        """Should escape % to prevent wildcard matching."""
        result = _escape_like_pattern("%")
        assert result == "\\%"

    def test_escapes_underscore_wildcard(self):
        """Should escape _ to prevent single-char wildcard matching."""
        result = _escape_like_pattern("_")
        assert result == "\\_"

    def test_escapes_backslash(self):
        """Should escape backslash first."""
        result = _escape_like_pattern("\\")
        assert result == "\\\\"

    def test_escapes_mixed_special_chars(self):
        """Should handle mixed special characters."""
        result = _escape_like_pattern("50% off_sale\\end")
        assert result == "50\\% off\\_sale\\\\end"

    def test_preserves_normal_text(self):
        """Should preserve normal text unchanged."""
        result = _escape_like_pattern("react")
        assert result == "react"

    def test_sql_injection_attempt(self):
        """Should treat SQL injection attempts as literal strings."""
        result = _escape_like_pattern("'; DROP TABLE--")
        assert result == "'; DROP TABLE--"


class TestListRepositories:
    """Tests for list_repositories function."""

    @pytest.mark.asyncio
    async def test_returns_repositories_list(self):
        """Should return list of repository items."""
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.name = "facebook/react"
        mock_row.primary_language = "JavaScript"
        mock_row.issue_count = 1250

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        result = await list_repositories(mock_db)

        assert len(result) == 1
        assert isinstance(result[0], RepositoryItem)
        assert result[0].name == "facebook/react"
        assert result[0].issue_count == 1250

    @pytest.mark.asyncio
    async def test_filters_by_language(self):
        """Should filter by primary_language when provided."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, language="Python")

        params = mock_db.execute.call_args[0][1]
        assert "language" in params
        assert params["language"] == "Python"

    @pytest.mark.asyncio
    async def test_language_case_insensitive(self):
        """Language filtering should be case-insensitive."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, language="typescript")

        call_args = mock_db.execute.call_args
        sql_query = str(call_args[0][0])
        assert "LOWER" in sql_query

    @pytest.mark.asyncio
    async def test_filters_by_search_query(self):
        """Should filter by search query in repository name."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, search_query="react")

        params = mock_db.execute.call_args[0][1]
        assert "search_pattern" in params
        assert "%react%" in params["search_pattern"]

    @pytest.mark.asyncio
    async def test_escapes_wildcard_in_search(self):
        """Should escape SQL wildcards in search query."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, search_query="%")

        params = mock_db.execute.call_args[0][1]
        assert "%\\%%" in params["search_pattern"]

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self):
        """Should respect limit parameter."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, limit=25)

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == 25

    @pytest.mark.asyncio
    async def test_clamps_limit_to_max(self):
        """Should clamp limit to MAX_LIMIT."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, limit=500)

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == MAX_LIMIT

    @pytest.mark.asyncio
    async def test_handles_negative_limit(self):
        """Should handle negative limit by using default."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, limit=-5)

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == DEFAULT_LIMIT

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_repos(self):
        """Should return empty list when no repositories found."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = await list_repositories(mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_handles_null_primary_language(self):
        """Should handle repositories with null primary_language."""
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.name = "owner/repo"
        mock_row.primary_language = None
        mock_row.issue_count = 10

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        result = await list_repositories(mock_db)

        assert len(result) == 1
        assert result[0].primary_language is None

    @pytest.mark.asyncio
    async def test_combines_language_and_search_filters(self):
        """Should combine both language and search filters."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await list_repositories(mock_db, language="JavaScript", search_query="react")

        params = mock_db.execute.call_args[0][1]
        assert "language" in params
        assert "search_pattern" in params


class TestConstants:
    """Tests for module constants."""

    def test_default_limit(self):
        """DEFAULT_LIMIT should be reasonable."""
        assert DEFAULT_LIMIT == 50

    def test_max_limit(self):
        """MAX_LIMIT should be reasonable."""
        assert MAX_LIMIT == 100
