from datetime import UTC, datetime, timedelta
from uuid import UUID

from gim_database.models.identity import LinkedAccount, Session, User
from gim_database.models.persistence import BookmarkedIssue, PersonalNote
from gim_database.models.profiles import UserProfile as UserProfileModel
from pydantic import BaseModel
from sqlalchemy import delete, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.config import get_settings
from gim_backend.core.oauth import OAuthProvider, UserProfile
from gim_backend.core.security import generate_session_id

USER_AGENT_MAX_LENGTH = 512
REFRESH_THRESHOLD_RATIO = 0.1


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExistingAccountError(Exception):
    """Contains original_provider for UI messaging"""

    def __init__(self, original_provider: str):
        self.original_provider = original_provider
        super().__init__(f"Account exists, Please sign in with {original_provider}")


class ProviderConflictError(Exception):
    """Provider ID already associated with different user"""

    pass


async def upsert_user(
    db: AsyncSession,
    profile: UserProfile,
    provider: OAuthProvider,
) -> User:
    """
    For UNAUTHENTICATED login flow only;
    1 Email not exist creates new user; 2 Email exists AND provider matches returns existing;
    3 Email exists AND provider differs raises ExistingAccountError
    """
    statement = select(User).where(User.email == profile.email)
    result = await db.exec(statement)
    existing_user = result.first()

    if existing_user is None:
        new_user = User(
            email=profile.email,
            created_via=provider.value,
        )

        if provider == OAuthProvider.GITHUB:
            new_user.github_node_id = profile.provider_id
            new_user.github_username = profile.username
        elif provider == OAuthProvider.GOOGLE:
            new_user.google_id = profile.provider_id

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    if existing_user.created_via != provider.value:
        raise ExistingAccountError(existing_user.created_via)

    if provider == OAuthProvider.GITHUB:
        if existing_user.github_node_id != profile.provider_id:
            existing_user.github_node_id = profile.provider_id
        if existing_user.github_username != profile.username:
            existing_user.github_username = profile.username
    elif provider == OAuthProvider.GOOGLE:
        if existing_user.google_id != profile.provider_id:
            existing_user.google_id = profile.provider_id

    await db.commit()
    await db.refresh(existing_user)
    return existing_user


async def link_provider(
    db: AsyncSession,
    user: User,
    profile: UserProfile,
    provider: OAuthProvider,
) -> User:
    """For authenticated account linking only; raises ProviderConflictError if provider_id linked to different user"""
    if provider == OAuthProvider.GITHUB:
        statement = select(User).where(User.github_node_id == profile.provider_id, User.id != user.id)
    else:
        statement = select(User).where(User.google_id == profile.provider_id, User.id != user.id)

    result = await db.exec(statement)
    conflict_user = result.first()

    if conflict_user is not None:
        raise ProviderConflictError(f"{provider.value} account is already linked to another user")

    if provider == OAuthProvider.GITHUB:
        user.github_node_id = profile.provider_id
        user.github_username = profile.username
    elif provider == OAuthProvider.GOOGLE:
        user.google_id = profile.provider_id

    await db.commit()
    await db.refresh(user)
    return user


async def create_session(
    db: AsyncSession,
    user_id: UUID,
    fingerprint_hash: str | None,
    remember_me: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    os_family: str | None = None,
    ua_family: str | None = None,
    asn: str | None = None,
    country_code: str | None = None,
) -> tuple[Session, datetime]:
    settings = get_settings()
    now = _utc_now()

    if remember_me:
        expires_at = now + timedelta(days=settings.session_remember_me_days)
    else:
        expires_at = now + timedelta(hours=settings.session_default_hours)

    truncated_user_agent = None
    if user_agent:
        truncated_user_agent = user_agent[:USER_AGENT_MAX_LENGTH]

    session = Session(
        user_id=user_id,
        fingerprint=fingerprint_hash,
        jti=generate_session_id(),
        expires_at=expires_at,
        remember_me=remember_me,
        created_at=now,
        last_active_at=now,
        ip_address=ip_address,
        user_agent_string=truncated_user_agent,
        os_family=os_family,
        ua_family=ua_family,
        asn=asn,
        country_code=country_code,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    return session, expires_at


async def refresh_session(
    db: AsyncSession,
    session: Session,
) -> datetime | None:
    """Only updates DB if session is over 10% through lifespan; reduces DB writes"""
    settings = get_settings()
    now = _utc_now()

    if session.remember_me:
        total_lifespan = timedelta(days=settings.session_remember_me_days)
    else:
        total_lifespan = timedelta(hours=settings.session_default_hours)

    session_expires = session.expires_at
    if session_expires.tzinfo is None:
        session_expires = session_expires.replace(tzinfo=UTC)

    time_remaining = session_expires - now
    elapsed = total_lifespan - time_remaining

    if elapsed < (total_lifespan * REFRESH_THRESHOLD_RATIO):
        return None

    new_expires_at = now + total_lifespan
    session.expires_at = new_expires_at
    session.last_active_at = now

    await db.commit()
    await db.refresh(session)

    return new_expires_at


async def get_session_by_id(
    db: AsyncSession,
    session_id: UUID,
) -> Session | None:
    """Fetches session by ID if not expired"""
    now = _utc_now()

    statement = select(Session).where(
        Session.id == session_id,
        Session.expires_at > now,
    )
    result = await db.exec(statement)
    return result.first()


async def invalidate_session(
    db: AsyncSession,
    session_id: UUID,
) -> bool:
    statement = delete(Session).where(Session.id == session_id)
    result = await db.exec(statement)
    await db.commit()

    return result.rowcount > 0


async def invalidate_all_sessions(
    db: AsyncSession,
    user_id: UUID,
    except_session_id: UUID | None = None,
) -> int:
    """Uses bulk DELETE for efficiency"""
    statement = delete(Session).where(Session.user_id == user_id)

    if except_session_id is not None:
        statement = statement.where(Session.id != except_session_id)

    result = await db.exec(statement)
    await db.commit()

    return result.rowcount


class SessionInfo(BaseModel):
    """Sanitized session metadata for API response"""

    id: str
    fingerprint_partial: str
    created_at: datetime
    last_active_at: datetime
    user_agent: str | None
    ip_address: str | None
    is_current: bool


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
    count: int


async def list_sessions(
    db: AsyncSession,
    user_id: UUID,
    current_session_id: UUID | None = None,
) -> list[SessionInfo]:
    """Returns all active sessions for user with sanitized metadata"""
    now = _utc_now()

    statement = (
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.expires_at > now,
        )
        .order_by(Session.last_active_at.desc())
    )

    result = await db.exec(statement)
    sessions = result.all()

    return [
        SessionInfo(
            id=str(session.id),
            fingerprint_partial=session.fingerprint[:8] if session.fingerprint else "",
            created_at=session.created_at,
            last_active_at=session.last_active_at,
            user_agent=session.user_agent_string,
            ip_address=session.ip_address,
            is_current=(current_session_id is not None and session.id == current_session_id),
        )
        for session in sessions
    ]


async def count_sessions(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """Returns count of active sessions for user"""
    now = _utc_now()

    statement = (
        select(func.count())
        .select_from(Session)
        .where(
            Session.user_id == user_id,
            Session.expires_at > now,
        )
    )

    result = await db.exec(statement)
    return result.one()


class UserNotFoundError(Exception):
    pass


class CascadeDeletionResult(BaseModel):
    tables_affected: list[str]
    total_rows: int


async def delete_user_cascade(
    db: AsyncSession,
    user_id: UUID,
) -> CascadeDeletionResult:
    """
    GDPR-compliant cascade deletion of user and all related data.
    Uses manual transaction to ensure atomicity; rolls back on any failure.
    Deletion order: personal_notes -> bookmarked_issues -> linked_accounts ->
                    user_profiles -> sessions -> users
    """
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.exec(user_stmt)
    user = user_result.first()

    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")

    tables_affected = []
    total_rows = 0

    async with db.begin():
        bookmark_ids_subq = select(BookmarkedIssue.id).where(BookmarkedIssue.user_id == user_id).scalar_subquery()

        notes_stmt = delete(PersonalNote).where(PersonalNote.bookmark_id.in_(bookmark_ids_subq))
        notes_result = await db.exec(notes_stmt)
        if notes_result.rowcount > 0:
            tables_affected.append("personal_notes")
            total_rows += notes_result.rowcount

        bookmarks_stmt = delete(BookmarkedIssue).where(BookmarkedIssue.user_id == user_id)
        bookmarks_result = await db.exec(bookmarks_stmt)
        if bookmarks_result.rowcount > 0:
            tables_affected.append("bookmarked_issues")
            total_rows += bookmarks_result.rowcount

        accounts_stmt = delete(LinkedAccount).where(LinkedAccount.user_id == user_id)
        accounts_result = await db.exec(accounts_stmt)
        if accounts_result.rowcount > 0:
            tables_affected.append("linked_accounts")
            total_rows += accounts_result.rowcount

        profiles_stmt = delete(UserProfileModel).where(UserProfileModel.user_id == user_id)
        profiles_result = await db.exec(profiles_stmt)
        if profiles_result.rowcount > 0:
            tables_affected.append("user_profiles")
            total_rows += profiles_result.rowcount

        sessions_stmt = delete(Session).where(Session.user_id == user_id)
        sessions_result = await db.exec(sessions_stmt)
        if sessions_result.rowcount > 0:
            tables_affected.append("sessions")
            total_rows += sessions_result.rowcount

        user_stmt = delete(User).where(User.id == user_id)
        user_result = await db.exec(user_stmt)
        if user_result.rowcount > 0:
            tables_affected.append("users")
            total_rows += user_result.rowcount

    return CascadeDeletionResult(
        tables_affected=tables_affected,
        total_rows=total_rows,
    )
