"""
Resume Worker: Cloud Run service for resume parsing tasks.
Handles full resume pipeline: Docling parse, GLiNER extract, normalize, embed.
"""

import base64
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
    reset_profile_recalculation,
)
from gim_backend.services.resume_parsing_service import (
    ResumePipelineData,
    apply_resume_profile_extraction,
    check_minimal_data,
    execute_resume_pipeline,
    extract_entities,
    finalize_resume_profile_vector,
    normalize_entities,
    parse_resume_to_markdown,
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
    logger.info("Resume worker starting up")
    yield
    await close_embedder()
    logger.info("Resume worker shut down")


app = FastAPI(
    title="IssueIndex Resume Worker",
    description="Cloud Tasks worker for resume parsing pipeline",
    version="0.1.0",
    lifespan=lifespan,
)


class ResumeParseRequest(BaseModel):
    """Request payload for resume parsing task from Cloud Tasks."""

    job_id: str
    user_id: str
    filename: str
    content_type: str | None
    file_bytes_b64: str
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


def _resume_worker_audience(path: str) -> str | None:
    return _build_worker_audience_shared(settings.resume_worker_url, path)


async def _get_profile(db: AsyncSession, user_id: UUID):
    """Fetches profile by user ID."""
    return await _get_profile_by_user_id(db, user_id)


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return _build_health_response("resume-worker")


@app.post("/tasks/resume/parse")
async def parse_resume(
    request: ResumeParseRequest,
    x_cloudtasks_taskname: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Executes full resume parsing pipeline:
    1. Docling: Parse PDF/DOCX to Markdown
    2. GLiNER: Extract entities (skills, job titles)
    3. Normalize: Map to taxonomy
    4. Embed: Generate 256-dim vector
    5. Update: Store results in profile

    File bytes are base64 encoded in the request.
    """
    if not _verify_cloud_tasks_token(
        x_cloudtasks_taskname,
        authorization,
        audience=_resume_worker_audience("/tasks/resume/parse"),
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    user_id = UUID(request.user_id)
    logger.info(f"Processing resume parse for job {request.job_id}, user {user_id}")

    try:
        file_bytes = base64.b64decode(request.file_bytes_b64)

        def _stage_logger(stage: str) -> None:
            if stage == "parse":
                logger.info(f"Stage 1: Docling parse for job {request.job_id}")
            elif stage == "extract":
                logger.info(f"Stage 2: GLiNER extract for job {request.job_id}")
            elif stage == "normalize":
                logger.info(f"Stage 3: Normalize entities for job {request.job_id}")
            elif stage == "embed":
                logger.info(f"Stage 4: Generate embedding for job {request.job_id}")

        async def _persist_parsed_data(data: ResumePipelineData) -> dict | None:
            if data.minimal_warning:
                logger.info(f"Minimal data warning for job {request.job_id}: {data.minimal_warning}")

            async with async_session_factory() as db:
                profile = await _get_profile(db, user_id)

                if profile is None:
                    logger.warning(f"Profile not found for user {user_id}; job {request.job_id} abandoned")
                    return {"status": "abandoned", "reason": "profile_not_found"}

                apply_resume_profile_extraction(profile, data)
                await db.commit()

            return None

        async def _persist_vector_data(
            _data: ResumePipelineData,
            vector: list[float] | None,
        ) -> dict | None:
            async with async_session_factory() as db:
                profile = await _get_profile(db, user_id)

                if profile is None:
                    logger.warning(f"Profile deleted during processing; job {request.job_id} abandoned")
                    return {"status": "abandoned", "reason": "profile_deleted"}

                await finalize_resume_profile_vector(
                    profile,
                    vector,
                    calculate_combined_vector_fn=calculate_combined_vector,
                )
                await db.commit()

            return None

        async def _cleanup_on_error() -> None:
            try:
                async with async_session_factory() as db:
                    profile = await _get_profile(db, user_id)
                    if profile:
                        reset_profile_recalculation(profile)
                        await db.commit()
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup is_calculating flag: {cleanup_error}")

        def _build_response(data: ResumePipelineData, vector: list[float] | None) -> dict:
            return {
                "status": "completed",
                "job_id": request.job_id,
                "skills_count": len(data.skills),
                "job_titles_count": len(data.job_titles),
                "vector_generated": vector is not None,
                "minimal_data_warning": data.minimal_warning,
            }

        result = await execute_resume_pipeline(
            file_bytes=file_bytes,
            filename=request.filename,
            embed_resume_fn=embed_document,
            persist_parsed_data_fn=_persist_parsed_data,
            persist_vector_data_fn=_persist_vector_data,
            build_completion_response_fn=_build_response,
            cleanup_on_error_fn=_cleanup_on_error,
            parse_resume_to_markdown_fn=parse_resume_to_markdown,
            extract_entities_fn=extract_entities,
            normalize_entities_fn=normalize_entities,
            check_minimal_data_fn=check_minimal_data,
            stage_logger_fn=_stage_logger,
        )

        if result.get("status") == "completed":
            logger.info(f"Resume parse completed for job {request.job_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Resume parse failed for job {request.job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
