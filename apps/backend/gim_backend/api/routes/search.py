"""
Search API routes with tiered rate limiting.
Unknown users: 10 req/min
Authenticated users: 60 req/min
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.core.audit import AuditEvent, log_audit_event
from gim_backend.middleware.context import RequestContext, get_request_context
from gim_backend.middleware.rate_limit import get_rate_limiter
from gim_backend.services.search_cache import (
    cache_search_context,
    cache_search_response,
    get_cached_search,
    get_cached_search_context,
)
from gim_backend.services.search_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    hybrid_search,
)

router = APIRouter()



ANON_SEARCH_LIMIT = 10
AUTH_SEARCH_LIMIT = 60
RATE_LIMIT_WINDOW = 60  # secs


class SearchFiltersInput(BaseModel):
    """API input model for search filters."""

    languages: list[str] = Field(default_factory=list, max_length=10)
    labels: list[str] = Field(default_factory=list, max_length=20)
    repos: list[str] = Field(default_factory=list, max_length=10)


class SearchRequestInput(BaseModel):
    """API input model for search request."""

    query: str = Field(..., min_length=1, max_length=500)
    filters: SearchFiltersInput = Field(default_factory=SearchFiltersInput)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


async def _get_optional_user_id(request: Request, db: AsyncSession) -> UUID | None:
    """
    Attempts to extract user_id from session cookie.
    Returns None if not authenticated, no error raised.
    """
    from gim_backend.core.cookies import SESSION_COOKIE_NAME
    from gim_backend.services.session_service import get_session_by_id

    session_id_str = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id_str:
        return None

    try:
        session_uuid = UUID(session_id_str)
        session = await get_session_by_id(db, session_uuid)
        if session:
            return session.user_id
    except (ValueError, Exception):
        pass

    return None


async def check_search_rate_limit(
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> UUID | None:
    """
    Tiered rate limiting for search:
    - Unknown: 10 req/min (keyed by IP)
    - Authenticated: 60 req/min (keyed by user_id)

    Returns user_id if authenticated, None otherwise.
    """
    limiter = await get_rate_limiter()
    user_id = await _get_optional_user_id(request, db)

    if user_id:
        key = f"search:user:{user_id}"
        max_requests = AUTH_SEARCH_LIMIT
    else:
        key = f"search:ip:{ctx.ip_address}"
        max_requests = ANON_SEARCH_LIMIT

    is_limited, retry_after = await limiter.is_rate_limited(
        key=key,
        max_requests=max_requests,
        window_seconds=RATE_LIMIT_WINDOW,
    )

    if is_limited:
        log_audit_event(
            AuditEvent.RATE_LIMITED,
            user_id=user_id,
            ip_address=ctx.ip_address,
            metadata={
                "endpoint": "search",
                "retry_after": retry_after,
                "key": key,
            },
        )
        raise HTTPException(
            status_code=429,
            detail="Too many search requests",
            headers={"Retry-After": str(retry_after)},
        )

    return user_id


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequestInput,
    user_id: UUID | None = Depends(check_search_rate_limit),
    db: AsyncSession = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> SearchResponse:
    """
    Hybrid search combining vector similarity and BM25 full-text search.
    Results are ranked using Reciprocal Rank Fusion (RRF).
    """
    filters = SearchFilters(
        languages=body.filters.languages,
        labels=body.filters.labels,
        repos=body.filters.repos,
    )

    request = SearchRequest(
        query=body.query,
        filters=filters,
        page=body.page,
        page_size=body.page_size,
    )

    cached_response = await get_cached_search(request)
    if cached_response:
        response = cached_response
        cache_hit = True
    else:
        response = await hybrid_search(db, request)
        await cache_search_response(request, response)
        cache_hit = False

    log_audit_event(
        AuditEvent.SEARCH,
        user_id=user_id,
        ip_address=ctx.ip_address,
        metadata={
            "search_id": str(response.search_id),
            "query": body.query,
            "result_count": len(response.results),
            "filters": body.filters.model_dump(),
            "cache_hit": cache_hit,
        },
    )

    # Store validated search context for interaction logging
    # so /search/interact doesn't need to trust client-provided fields.
    await cache_search_context(
        search_id=response.search_id,
        query_text=body.query,
        filters_json=body.filters.model_dump(),
        result_count=response.total,
        page=body.page,
        page_size=body.page_size,
        page_node_ids=[result.node_id for result in response.results],
    )

    return response


class InteractionInput(BaseModel):
    """API input for logging search result interactions."""

    search_id: str = Field(..., description="UUID from search response")
    selected_node_id: str = Field(..., description="Issue node_id that was clicked")
    position: int = Field(..., ge=1, description="1-indexed position in results")


@router.post("/interact", status_code=204)
async def log_interaction(
    body: InteractionInput,
    user_id: UUID | None = Depends(check_search_rate_limit),
    db: AsyncSession = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> Response:
    """
    Log a search result interaction for the golden dataset.
    Used to train and evaluate future ranking models.

    The search_id must be from a recent search (within cache TTL).
    """
    try:
        search_uuid = UUID(body.search_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid search_id format")

    context = await get_cached_search_context(search_uuid)
    if context is None:
        raise HTTPException(status_code=404, detail="Unknown or expired search_id")

    query_text = context.get("query_text")
    filters_json = context.get("filters_json")
    result_count = context.get("result_count")
    page = context.get("page")
    page_size = context.get("page_size")
    page_node_ids = context.get("page_node_ids")

    if not isinstance(query_text, str) or not query_text.strip():
        raise HTTPException(status_code=400, detail="Invalid search context query_text")
    if not isinstance(filters_json, dict):
        raise HTTPException(status_code=400, detail="Invalid search context filters_json")
    if not isinstance(result_count, int) or result_count < 0:
        raise HTTPException(status_code=400, detail="Invalid search context result_count")
    if not isinstance(page, int) or page < 1:
        raise HTTPException(status_code=400, detail="Invalid search context page")
    if not isinstance(page_size, int) or page_size < 1:
        raise HTTPException(status_code=400, detail="Invalid search context page_size")
    if not isinstance(page_node_ids, list) or not all(isinstance(x, str) for x in page_node_ids):
        raise HTTPException(status_code=400, detail="Invalid search context page_node_ids")

    if result_count == 0:
        raise HTTPException(status_code=400, detail="Invalid interaction position for empty result set")

    min_pos = (page - 1) * page_size + 1
    max_pos = min(page * page_size, result_count)

    if body.position < min_pos or body.position > max_pos:
        raise HTTPException(status_code=400, detail="Invalid interaction position")

    page_index = body.position - min_pos
    if page_index >= len(page_node_ids):
        raise HTTPException(status_code=400, detail="Invalid search context page_node_ids")
    if page_node_ids[page_index] != body.selected_node_id:
        raise HTTPException(status_code=400, detail="Invalid selected_node_id for position")

    sql = text("""
        INSERT INTO analytics.search_interactions
        (search_id, user_id, query_text, filters_json, result_count, selected_node_id, position)
        VALUES (
            :search_id,
            :user_id,
            :query_text,
            CAST(:filters_json AS jsonb),
            :result_count,
            :selected_node_id,
            :position
        )
    """)

    try:
        await db.execute(
            sql,
            {
                "search_id": search_uuid,
                "user_id": user_id,
                "query_text": query_text,
                "filters_json": json.dumps(filters_json),
                "result_count": result_count,
                "selected_node_id": body.selected_node_id,
                "position": body.position,
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        log_audit_event(
            AuditEvent.SEARCH_INTERACTION,
            user_id=user_id,
            ip_address=ctx.ip_address,
            metadata={
                "search_id": body.search_id,
                "selected_node_id": body.selected_node_id,
                "position": body.position,
                "error": str(e),
            },
        )
        return Response(status_code=204)

    log_audit_event(
        AuditEvent.SEARCH_INTERACTION,
        user_id=user_id,
        ip_address=ctx.ip_address,
        metadata={
            "search_id": body.search_id,
            "selected_node_id": body.selected_node_id,
            "position": body.position,
        },
    )

    return Response(status_code=204)
