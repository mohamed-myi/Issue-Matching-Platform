"""API routes for repository listing and filtering."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.services.repository_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    RepositoryItem,
    list_repositories,
)

router = APIRouter()



class RepositoriesResponse(BaseModel):
    """List of repositories."""

    repositories: list[RepositoryItem]



@router.get("", response_model=RepositoriesResponse)
async def list_repositories_endpoint(
    db: AsyncSession = Depends(get_db),
    language: Annotated[str | None, Query(description="Filter by primary language")] = None,
    q: Annotated[str | None, Query(description="Search in repository name")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> RepositoriesResponse:
    """
    Lists available repositories for filter suggestions.

    No authentication required - public endpoint for search dropdowns.
    Supports filtering by language and search query.
    Results ordered by stargazer count (popularity).
    """
    repos = await list_repositories(
        db,
        language=language,
        search_query=q,
        limit=limit,
    )

    return RepositoriesResponse(repositories=repos)
