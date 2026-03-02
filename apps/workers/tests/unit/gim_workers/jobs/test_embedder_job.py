"""Unit tests for embedder job persistence delegation."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_persist_issue_delegates_to_streaming_persistence(monkeypatch):
    from gim_workers.jobs import embedder_job

    mock_persistence = MagicMock()
    mock_persistence.upsert_staged_issue = AsyncMock()
    mock_ctor = MagicMock(return_value=mock_persistence)
    monkeypatch.setattr(embedder_job, "StreamingPersistence", mock_ctor)

    session = AsyncMock()
    issue = {
        "node_id": "I_123",
        "repo_id": "R_456",
        "title": "Bug report",
        "body_text": "Description",
        "labels": ["bug"],
        "github_created_at": "2026-02-25T12:00:00Z",
        "content_hash": "abc123",
    }
    embedding = [0.1] * 256

    await embedder_job._persist_issue(session, issue, embedding)

    mock_ctor.assert_called_once_with(session)
    mock_persistence.upsert_staged_issue.assert_awaited_once_with(issue, embedding)
