"""Bookmarks and Notes API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from gim_database.models.identity import Session, User
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.core.errors import (
    BookmarkAlreadyExistsError,
)
from gim_backend.middleware.auth import require_auth
from gim_backend.services.bookmark_service import (
    DEFAULT_PAGE_SIZE,
    BookmarkSchema,
    NoteSchema,
)
from gim_backend.services.bookmark_service import (
    check_bookmark as check_bookmark_service,
)
from gim_backend.services.bookmark_service import (
    check_bookmarks_batch as check_bookmarks_batch_service,
)
from gim_backend.services.bookmark_service import (
    create_bookmark as create_bookmark_service,
)
from gim_backend.services.bookmark_service import (
    create_note as create_note_service,
)
from gim_backend.services.bookmark_service import (
    delete_bookmark as delete_bookmark_service,
)
from gim_backend.services.bookmark_service import (
    delete_note as delete_note_service,
)
from gim_backend.services.bookmark_service import (
    get_bookmark as get_bookmark_service,
)
from gim_backend.services.bookmark_service import (
    list_bookmarks as list_bookmarks_service,
)
from gim_backend.services.bookmark_service import (
    list_notes as list_notes_service,
)
from gim_backend.services.bookmark_service import (
    update_bookmark as update_bookmark_service,
)
from gim_backend.services.bookmark_service import (
    update_note as update_note_service,
)

router = APIRouter()


class BookmarkCreateInput(BaseModel):
    issue_node_id: str = Field(..., min_length=1)
    github_url: str = Field(..., pattern=r"^https://github\.com/.+")
    title_snapshot: str = Field(..., min_length=1, max_length=500)
    body_snapshot: str = Field(..., max_length=5000)


class BookmarkUpdateInput(BaseModel):
    is_resolved: bool


class NoteCreateInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class NoteUpdateInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class BookmarkListOutput(BaseModel):
    results: list[BookmarkSchema]
    total: int
    page: int
    page_size: int
    has_more: bool


class NoteListOutput(BaseModel):
    results: list[NoteSchema]


class BookmarkCheckOutput(BaseModel):
    """Single bookmark check response."""

    bookmarked: bool
    bookmark_id: str | None


class BookmarkBatchCheckInput(BaseModel):
    """Batch bookmark check request."""

    issue_node_ids: list[str] = Field(..., min_length=1, max_length=50)


class BookmarkBatchCheckOutput(BaseModel):
    """Batch bookmark check response."""

    bookmarks: dict[str, str | None]  # issue_node_id -> bookmark_id or null


@router.post("", response_model=BookmarkSchema, status_code=201)
async def create_bookmark(
    body: BookmarkCreateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> BookmarkSchema:
    user, _ = auth

    try:
        bookmark = await create_bookmark_service(
            db=db,
            user_id=user.id,
            issue_node_id=body.issue_node_id,
            github_url=body.github_url,
            title_snapshot=body.title_snapshot,
            body_snapshot=body.body_snapshot,
        )
    except BookmarkAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=e.user_message)

    return bookmark


@router.get("", response_model=BookmarkListOutput)
async def list_bookmarks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=50),
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> BookmarkListOutput:
    user, _ = auth

    bookmarks, total, has_more = await list_bookmarks_service(
        db=db,
        user_id=user.id,
        page=page,
        page_size=page_size,
    )

    results = bookmarks

    return BookmarkListOutput(
        results=results,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/{bookmark_id}", response_model=BookmarkSchema)
async def get_bookmark(
    bookmark_id: UUID,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> BookmarkSchema:
    user, _ = auth

    bookmark = await get_bookmark_service(
        db=db,
        user_id=user.id,
        bookmark_id=bookmark_id,
    )

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return bookmark


@router.patch("/{bookmark_id}", response_model=BookmarkSchema)
async def update_bookmark(
    bookmark_id: UUID,
    body: BookmarkUpdateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> BookmarkSchema:
    user, _ = auth

    bookmark = await update_bookmark_service(
        db=db,
        user_id=user.id,
        bookmark_id=bookmark_id,
        is_resolved=body.is_resolved,
    )

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return bookmark


@router.delete("/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: UUID,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, _ = auth

    was_deleted = await delete_bookmark_service(
        db=db,
        user_id=user.id,
        bookmark_id=bookmark_id,
    )

    if not was_deleted:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return {"deleted": True, "message": "Bookmark and notes deleted"}



@router.get("/check/{issue_node_id}", response_model=BookmarkCheckOutput)
async def check_bookmark(
    issue_node_id: str,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> BookmarkCheckOutput:
    """Quick check if user has bookmarked a specific issue."""
    user, _ = auth

    bookmarked, bookmark_id = await check_bookmark_service(
        db=db,
        user_id=user.id,
        issue_node_id=issue_node_id,
    )

    return BookmarkCheckOutput(
        bookmarked=bookmarked,
        bookmark_id=str(bookmark_id) if bookmark_id else None,
    )


@router.post("/check", response_model=BookmarkBatchCheckOutput)
async def check_bookmarks_batch(
    body: BookmarkBatchCheckInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> BookmarkBatchCheckOutput:
    """
    Batch check if user has bookmarked multiple issues.

    Efficiently checks up to 50 issues in a single request.
    Duplicates in input are automatically deduped.
    """
    user, _ = auth

    result_map = await check_bookmarks_batch_service(
        db=db,
        user_id=user.id,
        issue_node_ids=body.issue_node_ids,
    )

    bookmarks = {node_id: str(bookmark_id) if bookmark_id else None for node_id, bookmark_id in result_map.items()}

    return BookmarkBatchCheckOutput(bookmarks=bookmarks)


@router.post("/{bookmark_id}/notes", response_model=NoteSchema, status_code=201)
async def create_note(
    bookmark_id: UUID,
    body: NoteCreateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> NoteSchema:
    user, _ = auth

    note = await create_note_service(
        db=db,
        user_id=user.id,
        bookmark_id=bookmark_id,
        content=body.content,
    )

    if note is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return note


@router.get("/{bookmark_id}/notes", response_model=NoteListOutput)
async def list_notes(
    bookmark_id: UUID,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> NoteListOutput:
    user, _ = auth

    notes = await list_notes_service(
        db=db,
        user_id=user.id,
        bookmark_id=bookmark_id,
    )

    if notes is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    results = notes
    return NoteListOutput(results=results)


@router.patch("/notes/{note_id}", response_model=NoteSchema)
async def update_note(
    note_id: UUID,
    body: NoteUpdateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> NoteSchema:
    user, _ = auth

    note = await update_note_service(
        db=db,
        user_id=user.id,
        note_id=note_id,
        content=body.content,
    )

    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return note


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: UUID,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, _ = auth

    was_deleted = await delete_note_service(
        db=db,
        user_id=user.id,
        note_id=note_id,
    )

    if not was_deleted:
        raise HTTPException(status_code=404, detail="Note not found")

    return {"deleted": True, "message": "Note deleted"}
