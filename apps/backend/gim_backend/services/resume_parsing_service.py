"""
Service for parsing resumes and extracting profile data.
Implements a 4 stage pipeline; Parse via Docling, Extract via GLiNER, Normalize, Embed.

For async processing via Cloud Tasks:
  - initiate_resume_processing() validates and enqueues task; returns immediately
  - process_resume() is the synchronous version for testing or fallback
  - Worker calls parse_resume_to_markdown, extract_entities, normalize_entities directly
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID

from gim_database.models.profiles import UserProfile
from gim_shared.constants import normalize_skill
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.errors import FileTooLargeError, ResumeParseError, UnsupportedFormatError
from gim_backend.services.cloud_tasks_service import enqueue_resume_task
from gim_backend.services.onboarding_service import mark_onboarding_in_progress
from gim_backend.services.profile_access import get_or_create_profile_record as _get_or_create_profile
from gim_backend.services.profile_embedding_service import (
    calculate_combined_vector,
    finalize_profile_recalculation,
    mark_profile_recalculation_started,
    reset_profile_recalculation,
)
from gim_backend.services.vector_generation import generate_resume_vector_with_retry

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ENTITY_LABELS = ["Skill", "Tool", "Framework", "Programming Language", "Job Title"]

_gliner_model = None


@dataclass
class ResumePipelineData:
    markdown: str
    skills: list[str]
    job_titles: list[str]
    raw_data: dict
    minimal_warning: str | None


def validate_file(filename: str, content_type: str | None, file_size: int) -> None:
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError("Please upload a PDF or DOCX file")

    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFormatError("Please upload a PDF or DOCX file")

    if file_size > MAX_FILE_SIZE:
        raise FileTooLargeError("Resume must be under 5MB")


def _get_gliner_model():
    global _gliner_model

    if _gliner_model is None:
        from gliner import GLiNER

        logger.info("Loading GLiNER model for resume entity extraction")
        _gliner_model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")

    return _gliner_model


def parse_resume_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Converts document to Markdown via Docling. File never touches disk."""
    from docling.datamodel.base_models import DocumentStream
    from docling.document_converter import DocumentConverter

    try:
        buf = BytesIO(file_bytes)
        source = DocumentStream(name=filename, stream=buf)
        converter = DocumentConverter()
        result = converter.convert(source)
        markdown = result.document.export_to_markdown()

        if not markdown or not markdown.strip():
            raise ResumeParseError("We couldn't read your resume. Try a different format?")

        logger.info(f"Parsed resume to {len(markdown)} chars of Markdown")
        return markdown

    except ResumeParseError:
        raise
    except Exception as e:
        logger.warning(f"Docling parse failed: {e}")
        raise ResumeParseError("We couldn't read your resume. Try a different format?")


def extract_entities(markdown_text: str) -> list[dict]:
    """Extracts named entities via GLiNER. Returns empty list on failure."""
    if not markdown_text or not markdown_text.strip():
        return []

    model = _get_gliner_model()

    try:
        entities = model.predict_entities(markdown_text, ENTITY_LABELS, threshold=0.5)
        logger.info(f"Extracted {len(entities)} entities from resume")
        return entities
    except Exception as e:
        logger.warning(f"GLiNER extraction failed: {e}")
        return []


def normalize_entities(raw_entities: list[dict]) -> tuple[list[str], list[str], dict]:
    """
    Maps raw entities to canonical forms. Unrecognized entities stored for taxonomy expansion.
    Returns (skills, job_titles, raw_data) where raw_data preserves original extraction.
    """
    skills_set: set[str] = set()
    job_titles_set: set[str] = set()
    unrecognized: list[str] = []

    for entity in raw_entities:
        raw_text = entity.get("text", "")
        if raw_text is None:
            continue
        text = raw_text.strip()
        label = entity.get("label", "")

        if not text:
            continue

        if label == "Job Title":
            job_titles_set.add(text)
            continue

        normalized = normalize_skill(text)
        if normalized:
            skills_set.add(normalized)
        else:
            unrecognized.append(text)
            skills_set.add(text)

    raw_data = {
        "entities": raw_entities,
        "unrecognized": unrecognized,
        "extracted_at": datetime.now(UTC).isoformat(),
    }

    return list(skills_set), list(job_titles_set), raw_data


async def generate_resume_vector(markdown_text: str) -> list[float] | None:
    """Generates 768 dim embedding from full Markdown text with retry support."""
    if not markdown_text or not markdown_text.strip():
        logger.warning("Cannot generate resume vector: no text content")
        return None

    logger.info(f"Generating resume vector for text length {len(markdown_text)}")
    vector = await generate_resume_vector_with_retry(markdown_text)

    if vector is None:
        logger.warning("Resume vector generation failed after retries")
        return None

    return vector


def check_minimal_data(skills_count: int) -> str | None:
    """Returns warning if fewer than 3 skills; threshold per PROFILE.md."""
    if skills_count < 3:
        return "We couldn't find many skills in your resume. For better recommendations, consider adding manual input."
    return None


def apply_resume_profile_extraction(profile: UserProfile, data: ResumePipelineData) -> None:
    profile.resume_skills = data.skills if data.skills else []
    profile.resume_job_titles = data.job_titles if data.job_titles else []
    profile.resume_raw_entities = data.raw_data
    profile.resume_uploaded_at = datetime.now(UTC)


async def finalize_resume_profile_vector(
    profile: UserProfile,
    vector: list[float] | None,
    *,
    calculate_combined_vector_fn: Callable[..., Awaitable[list[float] | None]] | None = None,
) -> None:
    profile.resume_vector = vector
    await finalize_profile_recalculation(
        profile,
        calculate_combined_vector_fn=calculate_combined_vector_fn or calculate_combined_vector,
    )


async def execute_resume_pipeline(
    *,
    file_bytes: bytes,
    filename: str,
    embed_resume_fn: Callable[[str], Awaitable[list[float] | None]],
    persist_parsed_data_fn: Callable[[ResumePipelineData], Awaitable[dict | None]],
    persist_vector_data_fn: Callable[[ResumePipelineData, list[float] | None], Awaitable[dict | None]],
    build_completion_response_fn: Callable[[ResumePipelineData, list[float] | None], dict],
    cleanup_on_error_fn: Callable[[], Awaitable[None]] | None = None,
    parse_resume_to_markdown_fn: Callable[[bytes, str], str] = parse_resume_to_markdown,
    extract_entities_fn: Callable[[str], list[dict]] = extract_entities,
    normalize_entities_fn: Callable[[list[dict]], tuple[list[str], list[str], dict]] = normalize_entities,
    check_minimal_data_fn: Callable[[int], str | None] = check_minimal_data,
    stage_logger_fn: Callable[[str], None] | None = None,
) -> dict:
    """Shared resume pipeline for service + worker adapters."""
    try:
        if stage_logger_fn:
            stage_logger_fn("parse")
        markdown = parse_resume_to_markdown_fn(file_bytes, filename)

        if stage_logger_fn:
            stage_logger_fn("extract")
        raw_entities = extract_entities_fn(markdown)

        if stage_logger_fn:
            stage_logger_fn("normalize")
        skills, job_titles, raw_data = normalize_entities_fn(raw_entities)

        data = ResumePipelineData(
            markdown=markdown,
            skills=skills,
            job_titles=job_titles,
            raw_data=raw_data,
            minimal_warning=check_minimal_data_fn(len(skills)),
        )

        early_response = await persist_parsed_data_fn(data)
        if early_response is not None:
            return early_response

        if stage_logger_fn:
            stage_logger_fn("embed")
        vector = await embed_resume_fn(markdown)

        early_response = await persist_vector_data_fn(data, vector)
        if early_response is not None:
            return early_response

        return build_completion_response_fn(data, vector)
    except Exception:
        if cleanup_on_error_fn is not None:
            await cleanup_on_error_fn()
        raise


async def initiate_resume_processing(
    db: AsyncSession,
    user_id: UUID,
    file_bytes: bytes,
    filename: str,
    content_type: str | None = None,
) -> dict:
    """
    Validates file and enqueues Cloud Task for async processing.
    Returns immediately with job_id and status 'processing'.

    The actual parsing happens in the resume worker via Cloud Tasks.
    """
    validate_file(filename, content_type, len(file_bytes))

    profile = await _get_or_create_profile(db, user_id)

    await mark_onboarding_in_progress(db, profile)

    mark_profile_recalculation_started(profile)
    await db.commit()

    try:
        job_id = await enqueue_resume_task(
            user_id=user_id,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
        )
    except Exception:
        reset_profile_recalculation(profile)
        await db.commit()
        raise

    logger.info(f"Resume processing initiated for user {user_id}, job_id {job_id}")

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Resume uploaded. Processing in background.",
    }


async def process_resume(
    db: AsyncSession,
    user_id: UUID,
    file_bytes: bytes,
    filename: str,
    content_type: str | None = None,
) -> dict:
    """
    Synchronous version: Orchestrates all 4 pipeline stages and updates profile.
    Used for testing or as fallback when Cloud Tasks is unavailable.
    """
    validate_file(filename, content_type, len(file_bytes))

    profile = await _get_or_create_profile(db, user_id)

    await mark_onboarding_in_progress(db, profile)

    async def _persist_parsed_data(data: ResumePipelineData) -> dict | None:
        apply_resume_profile_extraction(profile, data)
        mark_profile_recalculation_started(profile)
        await db.commit()
        return None

    async def _persist_vector_data(
        _data: ResumePipelineData,
        vector: list[float] | None,
    ) -> dict | None:
        await finalize_resume_profile_vector(
            profile,
            vector,
            calculate_combined_vector_fn=calculate_combined_vector,
        )
        await db.commit()
        await db.refresh(profile)
        return None

    async def _cleanup_on_error() -> None:
        if profile.is_calculating:
            reset_profile_recalculation(profile)
            await db.commit()

    def _build_response(data: ResumePipelineData, _vector: list[float] | None) -> dict:
        return {
            "status": "ready",
            "skills": profile.resume_skills or [],
            "job_titles": profile.resume_job_titles or [],
            "vector_status": "ready" if profile.resume_vector else None,
            "uploaded_at": profile.resume_uploaded_at.isoformat() if profile.resume_uploaded_at else None,
            "minimal_data_warning": data.minimal_warning,
        }

    return await execute_resume_pipeline(
        file_bytes=file_bytes,
        filename=filename,
        embed_resume_fn=generate_resume_vector,
        persist_parsed_data_fn=_persist_parsed_data,
        persist_vector_data_fn=_persist_vector_data,
        build_completion_response_fn=_build_response,
        cleanup_on_error_fn=_cleanup_on_error,
        parse_resume_to_markdown_fn=parse_resume_to_markdown,
        extract_entities_fn=extract_entities,
        normalize_entities_fn=normalize_entities,
        check_minimal_data_fn=check_minimal_data,
    )


async def get_resume_data(
    db: AsyncSession,
    user_id: UUID,
) -> dict | None:
    profile = await _get_or_create_profile(db, user_id)

    if profile.resume_skills is None:
        return None

    return {
        "status": "ready",
        "skills": profile.resume_skills or [],
        "job_titles": profile.resume_job_titles or [],
        "vector_status": "ready" if profile.resume_vector else None,
        "uploaded_at": profile.resume_uploaded_at.isoformat() if profile.resume_uploaded_at else None,
    }


async def delete_resume(
    db: AsyncSession,
    user_id: UUID,
) -> bool:
    profile = await _get_or_create_profile(db, user_id)

    if profile.resume_skills is None:
        return False

    mark_profile_recalculation_started(profile)
    await db.commit()

    try:
        profile.resume_skills = None
        profile.resume_job_titles = None
        profile.resume_raw_entities = None
        profile.resume_uploaded_at = None
        profile.resume_vector = None

        logger.info(f"Recalculating combined vector after resume deletion for {user_id}")
        await finalize_profile_recalculation(
            profile,
            calculate_combined_vector_fn=calculate_combined_vector,
        )
    finally:
        if profile.is_calculating:
            reset_profile_recalculation(profile)

    await db.commit()
    await db.refresh(profile)
    return True


def reset_gliner_for_testing() -> None:
    global _gliner_model
    _gliner_model = None


__all__ = [
    "MAX_FILE_SIZE",
    "ALLOWED_EXTENSIONS",
    "ALLOWED_CONTENT_TYPES",
    "validate_file",
    "parse_resume_to_markdown",
    "extract_entities",
    "normalize_entities",
    "generate_resume_vector",
    "check_minimal_data",
    "ResumePipelineData",
    "apply_resume_profile_extraction",
    "finalize_resume_profile_vector",
    "execute_resume_pipeline",
    "initiate_resume_processing",
    "process_resume",
    "get_resume_data",
    "delete_resume",
    "reset_gliner_for_testing",
]
