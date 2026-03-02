"""Bookmark CRUD/check service.

Note operations live in ``bookmark_note_service`` and are re-exported here
temporarily for backward compatibility with existing callers.
"""

import logging
from datetime import datetime
from uuid import UUID

from gim_database.models.persistence import BookmarkedIssue, PersonalNote
from pydantic import BaseModel
from sqlalchemy import delete, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.errors import BookmarkAlreadyExistsError
from gim_backend.services.bookmark_note_service import (
    NoteSchema,
    create_note,
    delete_note,
    get_notes_count_for_bookmark,
    list_notes,
    update_note,
)

logger = logging.getLogger(__name__)


DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 50


class BookmarkSchema(BaseModel):
    id: UUID
    issue_node_id: str
    github_url: str
    title_snapshot: str
    body_snapshot: str
    is_resolved: bool
    created_at: datetime
    notes_count: int = 0


async def create_bookmark(
    db: AsyncSession,
    user_id: UUID,
    issue_node_id: str,
    github_url: str,
    title_snapshot: str,
    body_snapshot: str,
) -> BookmarkSchema:
    existing_stmt = select(BookmarkedIssue).where(
        BookmarkedIssue.user_id == user_id,
        BookmarkedIssue.issue_node_id == issue_node_id,
    )
    result = await db.exec(existing_stmt)
    if result.first() is not None:
        raise BookmarkAlreadyExistsError()

    bookmark = BookmarkedIssue(
        user_id=user_id,
        issue_node_id=issue_node_id,
        github_url=github_url,
        title_snapshot=title_snapshot,
        body_snapshot=body_snapshot,
        is_resolved=False,
    )

    db.add(bookmark)
    await db.commit()
    await db.refresh(bookmark)

    logger.info(f"Created bookmark {bookmark.id} for user {user_id}")
    return BookmarkSchema(
        id=bookmark.id,
        issue_node_id=bookmark.issue_node_id,
        github_url=bookmark.github_url,
        title_snapshot=bookmark.title_snapshot,
        body_snapshot=bookmark.body_snapshot,
        is_resolved=bookmark.is_resolved,
        created_at=bookmark.created_at,
        notes_count=0,
    )


async def list_bookmarks(
    db: AsyncSession,
    user_id: UUID,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[BookmarkSchema], int, bool]:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = DEFAULT_PAGE_SIZE
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    offset = (page - 1) * page_size

    count_stmt = select(func.count()).select_from(BookmarkedIssue).where(BookmarkedIssue.user_id == user_id)
    count_result = await db.exec(count_stmt)
    total = count_result.one()

    list_stmt = (
        select(BookmarkedIssue, func.count(PersonalNote.id))
        .outerjoin(PersonalNote, BookmarkedIssue.id == PersonalNote.bookmark_id)
        .where(BookmarkedIssue.user_id == user_id)
        .group_by(BookmarkedIssue.id)
        .order_by(BookmarkedIssue.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.exec(list_stmt)
    rows = result.all()

    bookmarks = [
        BookmarkSchema(
            id=row[0].id,
            issue_node_id=row[0].issue_node_id,
            github_url=row[0].github_url,
            title_snapshot=row[0].title_snapshot,
            body_snapshot=row[0].body_snapshot,
            is_resolved=row[0].is_resolved,
            created_at=row[0].created_at,
            notes_count=row[1],
        )
        for row in rows
    ]

    has_more = (offset + len(bookmarks)) < total

    return bookmarks, total, has_more


async def get_bookmark(
    db: AsyncSession,
    user_id: UUID,
    bookmark_id: UUID,
) -> BookmarkSchema | None:
    stmt = (
        select(BookmarkedIssue, func.count(PersonalNote.id))
        .outerjoin(PersonalNote, BookmarkedIssue.id == PersonalNote.bookmark_id)
        .where(
            BookmarkedIssue.id == bookmark_id,
            BookmarkedIssue.user_id == user_id,
        )
        .group_by(BookmarkedIssue.id)
    )
    result = await db.exec(stmt)
    row = result.first()

    if row is None:
        return None

    bookmark, count = row
    return BookmarkSchema(
        id=bookmark.id,
        issue_node_id=bookmark.issue_node_id,
        github_url=bookmark.github_url,
        title_snapshot=bookmark.title_snapshot,
        body_snapshot=bookmark.body_snapshot,
        is_resolved=bookmark.is_resolved,
        created_at=bookmark.created_at,
        notes_count=count,
    )


async def update_bookmark(
    db: AsyncSession,
    user_id: UUID,
    bookmark_id: UUID,
    is_resolved: bool,
) -> BookmarkSchema | None:
    stmt = select(BookmarkedIssue).where(
        BookmarkedIssue.id == bookmark_id,
        BookmarkedIssue.user_id == user_id,
    )
    result = await db.exec(stmt)
    bookmark = result.first()

    if bookmark is None:
        return None

    bookmark.is_resolved = is_resolved

    await db.commit()
    await db.refresh(bookmark)

    return await get_bookmark(db, user_id, bookmark_id)


async def delete_bookmark(
    db: AsyncSession,
    user_id: UUID,
    bookmark_id: UUID,
) -> bool:
    """Cascade deletes associated notes before removing bookmark."""
    stmt = select(BookmarkedIssue).where(
        BookmarkedIssue.id == bookmark_id,
        BookmarkedIssue.user_id == user_id,
    )
    result = await db.exec(stmt)
    bookmark = result.first()

    if bookmark is None:
        return False

    delete_notes_stmt = delete(PersonalNote).where(PersonalNote.bookmark_id == bookmark_id)
    await db.exec(delete_notes_stmt)

    db.delete(bookmark)
    await db.commit()

    logger.info(f"Deleted bookmark {bookmark_id} and associated notes for user {user_id}")
    return True


async def check_bookmark(
    db: AsyncSession,
    user_id: UUID,
    issue_node_id: str,
) -> tuple[bool, UUID | None]:
    """
    Checks if user has bookmarked a specific issue.

    Returns:
        (bookmarked: bool, bookmark_id: UUID | None)
    """
    stmt = select(BookmarkedIssue.id).where(
        BookmarkedIssue.user_id == user_id,
        BookmarkedIssue.issue_node_id == issue_node_id,
    )
    result = await db.exec(stmt)
    bookmark_id = result.first()

    if bookmark_id is not None:
        return True, bookmark_id
    return False, None


async def check_bookmarks_batch(
    db: AsyncSession,
    user_id: UUID,
    issue_node_ids: list[str],
) -> dict[str, UUID | None]:
    """
    Batch check if user has bookmarked multiple issues.
    Handles duplicates by deduping input.

    Args:
        issue_node_ids: List of issue node IDs (duplicates allowed, will be deduped)

    Returns:
        Dict mapping issue_node_id -> bookmark_id (or None if not bookmarked)
    """
    if not issue_node_ids:
        return {}

    unique_ids = list(set(issue_node_ids))

    result_map: dict[str, UUID | None] = {node_id: None for node_id in unique_ids}

    stmt = select(BookmarkedIssue.issue_node_id, BookmarkedIssue.id).where(
        BookmarkedIssue.user_id == user_id,
        BookmarkedIssue.issue_node_id.in_(unique_ids),
    )
    result = await db.exec(stmt)
    rows = result.all()

    for row in rows:
        result_map[row.issue_node_id] = row.id

    return result_map


__all__ = [
    # Bookmark aggregate API
    "create_bookmark",
    "list_bookmarks",
    "get_bookmark",
    "update_bookmark",
    "delete_bookmark",
    # Compatibility re-exports from bookmark_note_service (TKT-V019)
    "create_note",
    "list_notes",
    "update_note",
    "delete_note",
    "get_notes_count_for_bookmark",
    "check_bookmark",
    "check_bookmarks_batch",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
]
