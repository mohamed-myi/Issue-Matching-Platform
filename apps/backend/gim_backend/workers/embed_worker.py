"""
Embed Worker: Cloud Run service for vector generation tasks.
Handles embedding requests from Cloud Tasks for profile vectors.
"""

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from gim_database.session import async_session_factory
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.config import get_settings
from gim_backend.services.embedding_service import close_embedder, embed_document
from gim_backend.services.profile_embedding_service import (
    calculate_combined_vector,
    finalize_profile_recalculation,
    reset_profile_recalculation,
)
from gim_backend.workers.worker_support import (
    build_health_response as _build_health_response,
)
from gim_backend.workers.worker_support import (
    build_worker_audience as _build_worker_audience_shared,
)
from gim_backend.workers.worker_support import (
    expected_cloud_tasks_service_account as _expected_cloud_tasks_service_account_shared,
)
from gim_backend.workers.worker_support import (
    get_profile_by_user_id as _get_profile_by_user_id,
)
from gim_backend.workers.worker_support import (
    verify_cloud_tasks_token as _verify_cloud_tasks_token_shared,
)
from gim_backend.workers.worker_support import (
    verify_oidc_bearer_token as _verify_oidc_bearer_token_shared,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Embed worker starting up")
    yield
    await close_embedder()
    logger.info("Embed worker shut down")


app = FastAPI(
    title="IssueIndex Embed Worker",
    description="Cloud Tasks worker for vector generation",
    version="0.1.0",
    lifespan=lifespan,
)


class EmbedResumeRequest(BaseModel):
    """Request payload for resume embedding task."""

    job_id: str
    user_id: str
    markdown_text: str


class EmbedGitHubRequest(BaseModel):
    """Request payload for GitHub embedding task."""

    job_id: str
    user_id: str
    formatted_text: str


class GitHubFetchRequest(BaseModel):
    """Request payload for GitHub fetch task."""

    job_id: str
    user_id: str
    created_at: str


def _verify_cloud_tasks_token(
    x_cloudtasks_taskname: str | None = Header(None),
    authorization: str | None = Header(None),
    *,
    audience: str | None = None,
) -> bool:
    return _verify_cloud_tasks_token_shared(
        x_cloudtasks_taskname,
        authorization,
        audience=audience,
        settings=settings,
        verify_oidc_bearer_token_fn=_verify_oidc_bearer_token,
    )


def _expected_cloud_tasks_service_account() -> str | None:
    return _expected_cloud_tasks_service_account_shared(settings)


def _verify_oidc_bearer_token(
    authorization: str | None,
    audience: str | None,
) -> bool:
    return _verify_oidc_bearer_token_shared(
        authorization,
        audience,
        settings=settings,
        logger=logger,
    )


def _embed_worker_audience(path: str) -> str | None:
    return _build_worker_audience_shared(settings.embed_worker_url, path)


async def _get_profile(db: AsyncSession, user_id: UUID):
    """Fetches profile by user ID."""
    return await _get_profile_by_user_id(db, user_id)


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return _build_health_response("embed-worker")


@app.post("/tasks/embed/resume")
async def embed_resume(
    request: EmbedResumeRequest,
    x_cloudtasks_taskname: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Generates resume vector from markdown text.
    Called after Docling and GLiNER processing completes.
    Updates profile with resume_vector and recalculates combined_vector.
    """
    if not _verify_cloud_tasks_token(
        x_cloudtasks_taskname,
        authorization,
        audience=_embed_worker_audience("/tasks/embed/resume"),
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    user_id = UUID(request.user_id)
    logger.info(f"Processing resume embedding for job {request.job_id}, user {user_id}")

    try:
        vector = await embed_document(request.markdown_text)

        if vector is None:
            logger.error(f"Resume embedding failed for job {request.job_id}")
            raise HTTPException(status_code=500, detail="Embedding generation failed")

        async with async_session_factory() as db:
            profile = await _get_profile(db, user_id)

            if profile is None:
                logger.warning(f"Profile not found for user {user_id}; job {request.job_id} abandoned")
                return {"status": "abandoned", "reason": "profile_not_found"}

            profile.resume_vector = vector

            await finalize_profile_recalculation(
                profile,
                calculate_combined_vector_fn=calculate_combined_vector,
            )

            await db.commit()

        logger.info(f"Resume embedding completed for job {request.job_id}")
        return {"status": "completed", "job_id": request.job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Resume embedding failed for job {request.job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/embed/github")
async def embed_github(
    request: EmbedGitHubRequest,
    x_cloudtasks_taskname: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Generates GitHub vector from formatted text.
    Updates profile with github_vector and recalculates combined_vector.
    """
    if not _verify_cloud_tasks_token(
        x_cloudtasks_taskname,
        authorization,
        audience=_embed_worker_audience("/tasks/embed/github"),
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    user_id = UUID(request.user_id)
    logger.info(f"Processing GitHub embedding for job {request.job_id}, user {user_id}")

    try:
        vector = await embed_document(request.formatted_text)

        if vector is None:
            logger.error(f"GitHub embedding failed for job {request.job_id}")
            raise HTTPException(status_code=500, detail="Embedding generation failed")

        async with async_session_factory() as db:
            profile = await _get_profile(db, user_id)

            if profile is None:
                logger.warning(f"Profile not found for user {user_id}; job {request.job_id} abandoned")
                return {"status": "abandoned", "reason": "profile_not_found"}

            profile.github_vector = vector

            await finalize_profile_recalculation(
                profile,
                calculate_combined_vector_fn=calculate_combined_vector,
            )

            await db.commit()

        logger.info(f"GitHub embedding completed for job {request.job_id}")
        return {"status": "completed", "job_id": request.job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"GitHub embedding failed for job {request.job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/github/fetch")
async def fetch_github(
    request: GitHubFetchRequest,
    x_cloudtasks_taskname: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Executes full GitHub profile fetch and embedding.
    This is the main entry point for GitHub async processing.
    """
    if not _verify_cloud_tasks_token(
        x_cloudtasks_taskname,
        authorization,
        audience=_embed_worker_audience("/tasks/github/fetch"),
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    user_id = UUID(request.user_id)
    logger.info(f"Processing GitHub fetch for job {request.job_id}, user {user_id}")

    try:
        from gim_backend.services.github_profile_service import execute_github_fetch

        async with async_session_factory() as db:
            result = await execute_github_fetch(db, user_id)

        logger.info(f"GitHub fetch completed for job {request.job_id}")
        return {"status": "completed", "job_id": request.job_id, "result": result}

    except Exception as e:
        logger.exception(f"GitHub fetch failed for job {request.job_id}: {e}")

        async with async_session_factory() as db:
            profile = await _get_profile(db, user_id)
            if profile:
                reset_profile_recalculation(profile)
                await db.commit()

        raise HTTPException(status_code=500, detail=str(e))
