"""GitHub profile API routes for fetching and managing GitHub activity data."""

from fastapi import APIRouter, Depends, HTTPException
from gim_database.models.identity import Session, User
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.core.errors import (
    GitHubNotConnectedError,
    RefreshRateLimitError,
    handle_profile_error,
)
from gim_backend.ingestion.github_client import (
    GitHubAPIError,
)
from gim_backend.ingestion.github_client import (
    GitHubAuthError as ClientAuthError,
)
from gim_backend.ingestion.github_client import (
    GitHubRateLimitError as ClientRateLimitError,
)
from gim_backend.middleware.auth import require_auth
from gim_backend.services.github_profile_service import (
    delete_github,
    get_github_data,
    initiate_github_fetch,
)

router = APIRouter()


class GitHubAcceptedResponse(BaseModel):
    """Response after initiating async GitHub profile fetch."""

    job_id: str
    status: str
    message: str


class GitHubDataResponse(BaseModel):
    """Response containing stored GitHub profile data."""

    status: str
    username: str
    starred_count: int
    contributed_repos: int
    languages: list[str]
    topics: list[str]
    vector_status: str | None
    fetched_at: str | None


def _handle_github_error(e: Exception) -> HTTPException:
    """Converts GitHub-related exceptions to user-friendly HTTP responses."""
    if isinstance(e, GitHubNotConnectedError):
        return HTTPException(status_code=400, detail="Please connect GitHub first")
    if isinstance(e, RefreshRateLimitError):
        minutes = max(1, e.seconds_remaining // 60)
        return HTTPException(
            status_code=429, detail=f"GitHub refresh available in {minutes} minute{'s' if minutes > 1 else ''}"
        )
    if isinstance(e, ClientAuthError):
        return HTTPException(status_code=400, detail="Please reconnect your GitHub account")
    if isinstance(e, ClientRateLimitError):
        return HTTPException(status_code=503, detail="GitHub is busy. We'll try again shortly.")
    if isinstance(e, GitHubAPIError):
        return HTTPException(status_code=503, detail="Unable to reach GitHub. Please try again.")

    return handle_profile_error(e)


@router.post("/github", status_code=202)
async def initiate_github_fetch_route(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> GitHubAcceptedResponse:
    """
    Initiates async GitHub profile data fetch.

    Requires a connected GitHub account via /auth/connect/github.
    Validates connection immediately; fetching happens in background via Cloud Tasks.

    Poll GET /profile or GET /profile/github for processing status.
    Check is_calculating=false and vector_status='ready' for completion.

    Returns:
        202 Accepted with job_id and status 'processing'.

    Errors:
        400: GitHub not connected or authentication failed
        429: Refresh rate limit exceeded
    """
    user, _ = auth

    try:
        result = await initiate_github_fetch(db, user.id, is_refresh=False)
    except (
        GitHubNotConnectedError,
        RefreshRateLimitError,
    ) as e:
        raise _handle_github_error(e)

    return GitHubAcceptedResponse(
        job_id=result["job_id"],
        status=result["status"],
        message=result["message"],
    )


@router.get("/github", response_model=GitHubDataResponse)
async def get_github(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> GitHubDataResponse:
    """
    Returns stored GitHub profile data.

    If is_calculating is true, GitHub fetch is still in progress.
    Check vector_status for embedding completion status.

    Returns:
        GitHubDataResponse with extracted languages, topics, and repo counts.

    Errors:
        404: No GitHub data found; use POST /profile/github first.
    """
    user, _ = auth

    data = await get_github_data(db, user.id)

    if data is None:
        raise HTTPException(status_code=404, detail="No GitHub data found. Connect GitHub first.")

    return GitHubDataResponse(
        status=data["status"],
        username=data["username"],
        starred_count=data["starred_count"],
        contributed_repos=data["contributed_repos"],
        languages=data["languages"],
        topics=data["topics"],
        vector_status=data["vector_status"],
        fetched_at=data["fetched_at"],
    )


@router.post("/github/refresh", status_code=202)
async def refresh_github(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> GitHubAcceptedResponse:
    """
    Re-fetches GitHub profile data asynchronously.

    Rate limited to 1 request per hour to avoid GitHub API limits.
    Validates rate limit immediately; fetching happens in background.

    Poll GET /profile or GET /profile/github for processing status.

    Returns:
        202 Accepted with job_id and status 'processing'.

    Errors:
        400: GitHub not connected or authentication failed
        429: Refresh rate limit exceeded; try again later
    """
    user, _ = auth

    try:
        result = await initiate_github_fetch(db, user.id, is_refresh=True)
    except (
        GitHubNotConnectedError,
        RefreshRateLimitError,
    ) as e:
        raise _handle_github_error(e)

    return GitHubAcceptedResponse(
        job_id=result["job_id"],
        status=result["status"],
        message=result["message"],
    )


@router.delete("/github")
async def delete_github_data(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Clears GitHub profile data and vector.

    Does NOT revoke OAuth token; use DELETE /auth/connect/github for that.
    Triggers combined_vector recalculation from remaining sources.

    Returns:
        Confirmation of deletion.

    Errors:
        404: No GitHub data to delete.
    """
    user, _ = auth

    was_deleted = await delete_github(db, user.id)

    if not was_deleted:
        raise HTTPException(status_code=404, detail="No GitHub data to delete")

    return {"deleted": True, "message": "GitHub data cleared"}
