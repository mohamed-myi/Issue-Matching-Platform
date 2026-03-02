"""API routes for issue discovery and detail endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.services.issue_service import (
    DEFAULT_SIMILAR_LIMIT,
    MAX_SIMILAR_LIMIT,
    IssueDetail,
    SimilarIssue,
    get_issue_by_node_id,
    get_similar_issues,
)

router = APIRouter()


class SimilarIssuesResponse(BaseModel):
    """List of similar issues."""

    issues: list[SimilarIssue]



@router.get("/{node_id}", response_model=IssueDetail)
async def get_issue_detail(
    node_id: str,
    db: AsyncSession = Depends(get_db),
) -> IssueDetail:
    """
    Returns full issue detail by node_id.

    Used for issue detail views, deep-linking, and bookmark cards.
    """
    issue = await get_issue_by_node_id(db, node_id)

    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    return issue


@router.get("/{node_id}/similar", response_model=SimilarIssuesResponse)
async def get_similar_issues_endpoint(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=MAX_SIMILAR_LIMIT)] = DEFAULT_SIMILAR_LIMIT,
) -> SimilarIssuesResponse:
    """
    Returns similar open issues based on vector similarity.

    Returns empty list if:
    - Source issue has no embedding yet
    - No similar issues above similarity threshold
    - All similar issues are closed
    """
    similar = await get_similar_issues(db, node_id, limit=limit)

    if similar is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    return SimilarIssuesResponse(issues=similar)
