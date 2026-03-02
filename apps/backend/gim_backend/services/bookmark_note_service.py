"""Note CRUD and ownership checks for bookmarked issues."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from gim_database.models.persistence import BookmarkedIssue, PersonalNote
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)


class NoteSchema(BaseModel):
    id: UUID
    bookmark_id: UUID
    content: str
    updated_at: datetime


async def _get_owned_bookmark(
    db: AsyncSession,
    user_id: UUID,
    bookmark_id: UUID,
) -> BookmarkedIssue | None:
    """Returns the bookmark only if it belongs to the user."""
    bm_stmt = select(BookmarkedIssue).where(
        BookmarkedIssue.id == bookmark_id,
        BookmarkedIssue.user_id == user_id,
    )
    return (await db.exec(bm_stmt)).first()


async def create_note(
    db: AsyncSession,
    user_id: UUID,
    bookmark_id: UUID,
    content: str,
) -> NoteSchema | None:
    bookmark = await _get_owned_bookmark(db, user_id, bookmark_id)
    if bookmark is None:
        return None

    note = PersonalNote(
        bookmark_id=bookmark.id,
        content=content,
    )

    db.add(note)
    await db.commit()
    await db.refresh(note)

    logger.info(f"Created note {note.id} on bookmark {bookmark_id}")
    return NoteSchema(
        id=note.id,
        bookmark_id=note.bookmark_id,
        content=note.content,
        updated_at=note.updated_at,
    )


async def list_notes(
    db: AsyncSession,
    user_id: UUID,
    bookmark_id: UUID,
) -> list[NoteSchema] | None:
    if await _get_owned_bookmark(db, user_id, bookmark_id) is None:
        return None

    stmt = select(PersonalNote).where(PersonalNote.bookmark_id == bookmark_id).order_by(PersonalNote.updated_at.desc())
    result = await db.exec(stmt)
    rows = result.all()

    return [
        NoteSchema(
            id=n.id,
            bookmark_id=n.bookmark_id,
            content=n.content,
            updated_at=n.updated_at,
        )
        for n in rows
    ]


async def get_note_with_ownership_check(
    db: AsyncSession,
    user_id: UUID,
    note_id: UUID,
) -> PersonalNote | None:
    """Verifies ownership via join to parent bookmark."""
    stmt = (
        select(PersonalNote)
        .join(BookmarkedIssue, PersonalNote.bookmark_id == BookmarkedIssue.id)
        .where(
            PersonalNote.id == note_id,
            BookmarkedIssue.user_id == user_id,
        )
    )
    result = await db.exec(stmt)
    return result.first()


async def update_note(
    db: AsyncSession,
    user_id: UUID,
    note_id: UUID,
    content: str,
) -> NoteSchema | None:
    note = await get_note_with_ownership_check(db, user_id, note_id)
    if note is None:
        return None

    note.content = content
    note.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(note)

    logger.info(f"Updated note {note_id}")
    return NoteSchema(
        id=note.id,
        bookmark_id=note.bookmark_id,
        content=note.content,
        updated_at=note.updated_at,
    )


async def delete_note(
    db: AsyncSession,
    user_id: UUID,
    note_id: UUID,
) -> bool:
    note = await get_note_with_ownership_check(db, user_id, note_id)
    if note is None:
        return False

    db.delete(note)
    await db.commit()

    logger.info(f"Deleted note {note_id}")
    return True


async def get_notes_count_for_bookmark(
    db: AsyncSession,
    bookmark_id: UUID,
) -> int:
    stmt = select(func.count()).select_from(PersonalNote).where(PersonalNote.bookmark_id == bookmark_id)
    result = await db.exec(stmt)
    return result.one()


__all__ = [
    "NoteSchema",
    "create_note",
    "list_notes",
    "update_note",
    "delete_note",
    "get_notes_count_for_bookmark",
]
