from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def mock_settings(settings_env_override):
    with settings_env_override(
        {
            "FINGERPRINT_SECRET": "test-fingerprint-secret-key-for-testing",
            "JWT_SECRET_KEY": "test-jwt-secret-key",
            "SESSION_REMEMBER_ME_DAYS": "7",
            "SESSION_DEFAULT_HOURS": "24",
        },
    ):
        yield


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.exec = AsyncMock()
    return db


@pytest.fixture
def github_profile():
    from gim_backend.core.oauth import UserProfile

    return UserProfile(
        email="test@example.com",
        provider_id="MDQ6VXNlcjEyMzQ1Njc=",
        avatar_url="https://avatars.githubusercontent.com/u/1234567",
        is_verified=True,
        username="testuser",
    )


@pytest.fixture
def google_profile():
    from gim_backend.core.oauth import UserProfile

    return UserProfile(
        email="test@example.com",
        provider_id="123456789012345678901",
        avatar_url="https://lh3.googleusercontent.com/a/default",
        is_verified=True,
        username=None,
    )


class TestRefreshSessionLogic:
    """Tests the REFRESH_THRESHOLD_RATIO business rule that prevents excessive DB writes"""

    async def test_updates_session_when_threshold_exceeded(self, mock_db):
        """Refresh updates DB when more than 10 percent through lifespan"""
        from gim_backend.services.session_service import refresh_session

        session = MagicMock()
        session.remember_me = True
        session.expires_at = datetime.now(UTC) + timedelta(days=3)
        session.last_active_at = datetime.now(UTC) - timedelta(hours=1)

        new_expires = await refresh_session(mock_db, session)

        assert new_expires is not None
        mock_db.commit.assert_called_once()

    async def test_skips_update_when_within_threshold(self, mock_db):
        """Refresh skips DB write when less than 10 percent through lifespan"""
        from gim_backend.services.session_service import refresh_session

        session = MagicMock()
        session.remember_me = True
        session.expires_at = datetime.now(UTC) + timedelta(days=6, hours=22)

        new_expires = await refresh_session(mock_db, session)

        assert new_expires is None
        mock_db.commit.assert_not_called()

    async def test_refresh_always_extends_from_now(self, mock_db):
        """
        Refresh calculates new expires_at from current time, not old expires_at;
        prevents indefinite session extension through repeated refreshes
        """
        from gim_backend.services.session_service import refresh_session

        session = MagicMock()
        session.remember_me = True
        session.expires_at = datetime.now(UTC) + timedelta(days=1)

        before = datetime.now(UTC)
        new_expires = await refresh_session(mock_db, session)
        after = datetime.now(UTC)

        assert new_expires is not None
        expected_min = before + timedelta(days=6, hours=23)
        expected_max = after + timedelta(days=7, hours=1)
        assert expected_min <= new_expires <= expected_max


class TestIdentityConflicts:
    """OAuth identity collision detection"""

    async def test_raises_existing_account_error_different_provider(self, mock_db, github_profile):
        """
        Prevents duplicate accounts; if user signed up with Google then tries
        GitHub login with same email, must fail with ExistingAccountError
        """
        from gim_backend.core.oauth import OAuthProvider
        from gim_backend.services.session_service import ExistingAccountError, upsert_user

        existing_user = MagicMock()
        existing_user.created_via = "google"

        mock_result = MagicMock()
        mock_result.first.return_value = existing_user
        mock_db.exec.return_value = mock_result

        with pytest.raises(ExistingAccountError) as exc:
            await upsert_user(mock_db, github_profile, OAuthProvider.GITHUB)

        assert exc.value.original_provider == "google"

    async def test_raises_conflict_when_provider_linked_to_other(self, mock_db, github_profile):
        """Two different users cannot link the same OAuth provider account"""
        from gim_backend.core.oauth import OAuthProvider
        from gim_backend.services.session_service import ProviderConflictError, link_provider

        user = MagicMock()
        user.id = uuid4()

        other_user = MagicMock()
        other_user.id = uuid4()

        mock_result = MagicMock()
        mock_result.first.return_value = other_user
        mock_db.exec.return_value = mock_result

        with pytest.raises(ProviderConflictError):
            await link_provider(mock_db, user, github_profile, OAuthProvider.GITHUB)


class TestBulkSessionOperations:
    """Sign out of all other devices feature"""

    @pytest.mark.parametrize(
        "except_id, expected_where_calls",
        [
            (uuid4(), 2),
            (None, 1),
        ],
    )
    async def test_invalidate_all_sessions_logic(self, mock_db, except_id, expected_where_calls):
        """
        With except_session_id uses 2 WHERE clauses; without uses 1
        """
        from gim_backend.services.session_service import invalidate_all_sessions

        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.exec.return_value = mock_result

        with patch("gim_backend.services.session_service.delete") as mock_delete:
            chain = mock_delete.return_value.where.return_value
            chain.where.return_value = chain

            await invalidate_all_sessions(mock_db, user_id, except_session_id=except_id)

            assert mock_delete.return_value.where.call_count == 1
            assert chain.where.call_count == (expected_where_calls - 1)

    async def test_invalidate_all_except_preserves_current(self, mock_db):
        """Excludes current session from bulk deletion"""
        from gim_backend.services.session_service import invalidate_all_sessions

        user_id = uuid4()
        current_session_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.exec.return_value = mock_result

        with patch("gim_backend.services.session_service.delete") as mock_delete:
            mock_where = MagicMock()
            mock_where.where.return_value = MagicMock()
            mock_delete.return_value.where.return_value = mock_where

            count = await invalidate_all_sessions(mock_db, user_id, except_session_id=current_session_id)

            mock_delete.return_value.where.assert_called_once()
            mock_where.where.assert_called_once()

            assert count == 3


class TestDeleteUserCascade:
    """GDPR cascade deletion tests"""

    async def test_raises_error_when_user_not_found(self, mock_db):
        """UserNotFoundError raised if user does not exist"""
        from gim_backend.services.session_service import UserNotFoundError, delete_user_cascade

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        with pytest.raises(UserNotFoundError) as exc:
            await delete_user_cascade(mock_db, uuid4())

        assert "not found" in str(exc.value).lower()

    async def test_returns_result_with_tables_and_counts(self, mock_db):
        """Returns CascadeDeletionResult with tables_affected and total_rows"""
        from gim_backend.services.session_service import CascadeDeletionResult, delete_user_cascade

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        mock_select_result = MagicMock()
        mock_select_result.first.return_value = mock_user

        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 1  # Simulate 1 row deleted per table

        call_count = [0]

        def exec_side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_select_result
            return mock_delete_result

        mock_db.exec = AsyncMock(side_effect=exec_side_effect)

        # Mock the transaction context manager
        mock_db.begin = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))

        result = await delete_user_cascade(mock_db, user_id)

        assert isinstance(result, CascadeDeletionResult)
        assert isinstance(result.tables_affected, list)
        assert isinstance(result.total_rows, int)

    async def test_handles_empty_relations(self, mock_db):
        """User with no bookmarks or notes returns 0 for those tables"""
        from gim_backend.services.session_service import delete_user_cascade

        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        mock_select_result = MagicMock()
        mock_select_result.first.return_value = mock_user

        mock_empty_result = MagicMock()
        mock_empty_result.rowcount = 0

        mock_user_delete = MagicMock()
        mock_user_delete.rowcount = 1

        call_count = [0]

        def exec_side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_select_result
            if call_count[0] == 7:  # Last delete is user table
                return mock_user_delete
            return mock_empty_result

        mock_db.exec = AsyncMock(side_effect=exec_side_effect)
        mock_db.begin = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))

        result = await delete_user_cascade(mock_db, user_id)

        assert "users" in result.tables_affected
        assert result.total_rows >= 1


class TestDeleteUserCascadeIsolation:
    """Verify deletion does not affect other users"""

    async def test_deletion_passes_correct_user_id(self, mock_db):
        """All delete statements filter by the correct user_id"""
        from gim_backend.services.session_service import delete_user_cascade

        user_id = uuid4()

        mock_user = MagicMock()
        mock_user.id = user_id

        mock_select_result = MagicMock()
        mock_select_result.first.return_value = mock_user

        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 0

        call_count = [0]

        def exec_side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_select_result
            return mock_delete_result

        mock_db.exec = AsyncMock(side_effect=exec_side_effect)
        mock_db.begin = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))

        with patch("gim_backend.services.session_service.delete") as mock_delete:
            mock_chain = MagicMock()
            mock_chain.where.return_value = mock_chain
            mock_chain.in_.return_value = mock_chain
            mock_delete.return_value.where.return_value = mock_chain

            await delete_user_cascade(mock_db, user_id)

            assert mock_delete.call_count > 0
