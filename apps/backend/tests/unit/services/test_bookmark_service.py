"""Unit tests for bookmark service CRUD operations."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
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
from gim_backend.services.bookmark_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    BookmarkSchema,
    create_bookmark,
    delete_bookmark,
    get_bookmark,
    list_bookmarks,
    update_bookmark,
)


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.exec = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def bookmark_id():
    return uuid4()


@pytest.fixture
def note_id():
    return uuid4()


@pytest.fixture
def sample_bookmark(user_id, bookmark_id):
    bookmark = MagicMock()
    bookmark.id = bookmark_id
    bookmark.user_id = user_id
    bookmark.issue_node_id = "I_abc123"
    bookmark.github_url = "https://github.com/org/repo/issues/1"
    bookmark.title_snapshot = "Bug in feature"
    bookmark.body_snapshot = "Steps to reproduce..."
    bookmark.is_resolved = False
    bookmark.created_at = datetime.now(UTC)
    return bookmark


@pytest.fixture
def sample_note(bookmark_id, note_id):
    note = MagicMock()
    note.id = note_id
    note.bookmark_id = bookmark_id
    note.content = "My notes here"
    note.updated_at = datetime.now(UTC)
    return note


class TestCreateBookmark:
    async def test_creates_bookmark_successfully(self, mock_db, user_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        async def refresh_side_effect(bookmark):
            bookmark.id = uuid4()
            bookmark.created_at = datetime.now(UTC)

        mock_db.refresh.side_effect = refresh_side_effect

        bookmark = await create_bookmark(
            db=mock_db,
            user_id=user_id,
            issue_node_id="I_abc123",
            github_url="https://github.com/org/repo/issues/1",
            title_snapshot="Bug title",
            body_snapshot="Bug body",
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert bookmark.issue_node_id == "I_abc123"

    async def test_raises_error_for_duplicate_bookmark(self, mock_db, user_id, sample_bookmark):
        mock_result = MagicMock()
        mock_result.first.return_value = sample_bookmark
        mock_db.exec.return_value = mock_result

        with pytest.raises(BookmarkAlreadyExistsError):
            await create_bookmark(
                db=mock_db,
                user_id=user_id,
                issue_node_id=sample_bookmark.issue_node_id,
                github_url=sample_bookmark.github_url,
                title_snapshot="Title",
                body_snapshot="Body",
            )


class TestListBookmarks:
    async def test_returns_bookmarks_with_pagination(self, mock_db, user_id, sample_bookmark):
        count_result = MagicMock()
        count_result.one.return_value = 5

        list_result = MagicMock()
        list_result.all.return_value = [(sample_bookmark, 2)]

        mock_db.exec.side_effect = [count_result, list_result]

        bookmarks, total, has_more = await list_bookmarks(
            db=mock_db,
            user_id=user_id,
            page=1,
            page_size=2,
        )

        assert len(bookmarks) == 1
        assert total == 5
        assert has_more is True
        assert isinstance(bookmarks[0], BookmarkSchema)
        assert bookmarks[0].notes_count == 2

    async def test_returns_empty_list_for_no_bookmarks(self, mock_db, user_id):
        count_result = MagicMock()
        count_result.one.return_value = 0

        list_result = MagicMock()
        list_result.all.return_value = []

        mock_db.exec.side_effect = [count_result, list_result]

        bookmarks, total, has_more = await list_bookmarks(
            db=mock_db,
            user_id=user_id,
            page=1,
            page_size=20,
        )

        assert bookmarks == []
        assert total == 0
        assert has_more is False

    async def test_clamps_page_to_minimum_1(self, mock_db, user_id):
        count_result = MagicMock()
        count_result.one.return_value = 0

        list_result = MagicMock()
        list_result.all.return_value = []

        mock_db.exec.side_effect = [count_result, list_result]

        await list_bookmarks(db=mock_db, user_id=user_id, page=0, page_size=20)

        assert mock_db.exec.call_count == 2

    async def test_clamps_page_size_to_max(self, mock_db, user_id):
        count_result = MagicMock()
        count_result.one.return_value = 0

        list_result = MagicMock()
        list_result.all.return_value = []

        mock_db.exec.side_effect = [count_result, list_result]

        await list_bookmarks(db=mock_db, user_id=user_id, page=1, page_size=100)

        assert mock_db.exec.call_count == 2

    async def test_has_more_false_on_last_page(self, mock_db, user_id, sample_bookmark):
        count_result = MagicMock()
        count_result.one.return_value = 1

        list_result = MagicMock()
        list_result.all.return_value = [(sample_bookmark, 1)]

        mock_db.exec.side_effect = [count_result, list_result]

        bookmarks, total, has_more = await list_bookmarks(
            db=mock_db,
            user_id=user_id,
            page=1,
            page_size=20,
        )

        assert has_more is False


class TestGetBookmark:
    async def test_returns_bookmark_if_owned(self, mock_db, user_id, sample_bookmark):
        mock_result = MagicMock()
        mock_result.first.return_value = (sample_bookmark, 5)
        mock_db.exec.return_value = mock_result

        bookmark = await get_bookmark(
            db=mock_db,
            user_id=user_id,
            bookmark_id=sample_bookmark.id,
        )

        assert isinstance(bookmark, BookmarkSchema)
        assert bookmark.id == sample_bookmark.id
        assert bookmark.notes_count == 5

    async def test_returns_none_if_not_found(self, mock_db, user_id, bookmark_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        bookmark = await get_bookmark(
            db=mock_db,
            user_id=user_id,
            bookmark_id=bookmark_id,
        )

        assert bookmark is None

class TestUpdateBookmark:
    async def test_updates_is_resolved_status(self, mock_db, user_id, sample_bookmark):
        find_result = MagicMock()
        find_result.first.return_value = sample_bookmark

        get_result = MagicMock()
        get_result.first.return_value = (sample_bookmark, 1)

        mock_db.exec.side_effect = [find_result, get_result]

        bookmark = await update_bookmark(
            db=mock_db,
            user_id=user_id,
            bookmark_id=sample_bookmark.id,
            is_resolved=True,
        )

        assert bookmark.is_resolved is True
        assert mock_db.commit.called
        assert mock_db.refresh.called
        assert isinstance(bookmark, BookmarkSchema)

    async def test_returns_none_if_not_found(self, mock_db, user_id, bookmark_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        result = await update_bookmark(
            db=mock_db,
            user_id=user_id,
            bookmark_id=bookmark_id,
            is_resolved=True,
        )

        assert result is None


class TestDeleteBookmark:
    async def test_deletes_bookmark_and_notes(self, mock_db, user_id, sample_bookmark):
        mock_result = MagicMock()
        mock_result.first.return_value = sample_bookmark
        mock_db.exec.return_value = mock_result

        result = await delete_bookmark(
            db=mock_db,
            user_id=user_id,
            bookmark_id=sample_bookmark.id,
        )

        assert result is True
        assert mock_db.exec.call_count == 2
        assert mock_db.delete.called
        assert mock_db.commit.called

    async def test_returns_false_if_not_found(self, mock_db, user_id, bookmark_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        result = await delete_bookmark(
            db=mock_db,
            user_id=user_id,
            bookmark_id=bookmark_id,
        )

        assert result is False


class TestCreateNote:
    async def test_creates_note_on_owned_bookmark(self, mock_db, user_id, sample_bookmark):
        check_result = MagicMock()
        check_result.first.return_value = sample_bookmark
        mock_db.exec.return_value = check_result

        async def refresh_side_effect(note):
            note.id = uuid4()
            note.updated_at = datetime.now(UTC)

        mock_db.refresh.side_effect = refresh_side_effect

        note = await create_note(
            db=mock_db,
            user_id=user_id,
            bookmark_id=sample_bookmark.id,
            content="My note content",
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert note.content == "My note content"
        assert isinstance(note, NoteSchema)

    async def test_returns_none_if_bookmark_not_owned(self, mock_db, user_id, bookmark_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        note = await create_note(
            db=mock_db,
            user_id=user_id,
            bookmark_id=bookmark_id,
            content="My note",
        )

        assert note is None


class TestListNotes:
    async def test_returns_notes_for_owned_bookmark(self, mock_db, user_id, sample_bookmark, sample_note):
        bookmark_result = MagicMock()
        bookmark_result.first.return_value = sample_bookmark

        notes_result = MagicMock()
        notes_result.all.return_value = [sample_note]

        mock_db.exec.side_effect = [bookmark_result, notes_result]

        notes = await list_notes(
            db=mock_db,
            user_id=user_id,
            bookmark_id=sample_bookmark.id,
        )

        assert len(notes) == 1
        assert notes[0].id == sample_note.id
        assert isinstance(notes[0], NoteSchema)

    async def test_returns_none_if_bookmark_not_owned(self, mock_db, user_id, bookmark_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        notes = await list_notes(
            db=mock_db,
            user_id=user_id,
            bookmark_id=bookmark_id,
        )

        assert notes is None

    async def test_returns_empty_list_for_bookmark_with_no_notes(self, mock_db, user_id, sample_bookmark):
        bookmark_result = MagicMock()
        bookmark_result.first.return_value = sample_bookmark

        notes_result = MagicMock()
        notes_result.all.return_value = []

        mock_db.exec.side_effect = [bookmark_result, notes_result]

        notes = await list_notes(
            db=mock_db,
            user_id=user_id,
            bookmark_id=sample_bookmark.id,
        )

        assert notes == []


class TestUpdateNote:
    async def test_updates_note_content(self, mock_db, user_id, sample_note):
        mock_result = MagicMock()
        mock_result.first.return_value = sample_note
        mock_db.exec.return_value = mock_result

        note = await update_note(
            db=mock_db,
            user_id=user_id,
            note_id=sample_note.id,
            content="Updated content",
        )

        assert note.content == "Updated content"
        assert mock_db.commit.called
        assert mock_db.refresh.called
        assert isinstance(note, NoteSchema)

    async def test_returns_none_if_not_found_or_not_owned(self, mock_db, user_id, note_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        result = await update_note(
            db=mock_db,
            user_id=user_id,
            note_id=note_id,
            content="New content",
        )

        assert result is None


class TestDeleteNote:
    async def test_deletes_note_successfully(self, mock_db, user_id, sample_note):
        mock_result = MagicMock()
        mock_result.first.return_value = sample_note
        mock_db.exec.return_value = mock_result

        result = await delete_note(
            db=mock_db,
            user_id=user_id,
            note_id=sample_note.id,
        )

        assert result is True
        assert mock_db.delete.called
        assert mock_db.commit.called

    async def test_returns_false_if_not_found(self, mock_db, user_id, note_id):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.exec.return_value = mock_result

        result = await delete_note(
            db=mock_db,
            user_id=user_id,
            note_id=note_id,
        )

        assert result is False


class TestGetNotesCountForBookmark:
    async def test_returns_count(self, mock_db, bookmark_id):
        mock_result = MagicMock()
        mock_result.one.return_value = 5
        mock_db.exec.return_value = mock_result

        count = await get_notes_count_for_bookmark(
            db=mock_db,
            bookmark_id=bookmark_id,
        )

        assert count == 5


class TestConstants:
    def test_default_page_size_is_20(self):
        assert DEFAULT_PAGE_SIZE == 20

    def test_max_page_size_is_50(self):
        assert MAX_PAGE_SIZE == 50
