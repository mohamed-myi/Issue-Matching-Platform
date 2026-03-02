"""Resume profile API routes for uploading and managing resume data."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from gim_database.models.identity import Session, User
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.core.errors import (
    FileTooLargeError,
    ResumeParseError,
    UnsupportedFormatError,
    handle_profile_error,
)
from gim_backend.middleware.auth import require_auth
from gim_backend.services.resume_parsing_service import (
    MAX_FILE_SIZE,
    delete_resume,
    get_resume_data,
    initiate_resume_processing,
)

router = APIRouter()


class ResumeUploadAcceptedResponse(BaseModel):
    """Response after initiating async resume processing."""

    job_id: str
    status: str
    message: str


class ResumeDataResponse(BaseModel):
    """Response containing stored resume data."""

    status: str
    skills: list[str]
    job_titles: list[str]
    vector_status: str | None
    uploaded_at: str | None


def _handle_resume_error(e: Exception) -> HTTPException:
    """Converts resume-related exceptions to user-friendly HTTP responses."""
    if isinstance(e, UnsupportedFormatError):
        return HTTPException(status_code=400, detail="Please upload a PDF or DOCX file")
    if isinstance(e, FileTooLargeError):
        return HTTPException(status_code=413, detail="Resume must be under 5MB")
    if isinstance(e, ResumeParseError):
        return HTTPException(status_code=422, detail="We couldn't read your resume. Try a different format?")

    return handle_profile_error(e)


@router.post("/resume", status_code=202)
async def upload_resume(
    file: UploadFile = File(...),
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ResumeUploadAcceptedResponse:
    """
    Uploads a resume file and initiates async processing.

    Accepts PDF or DOCX files up to 5MB.
    File is validated immediately; parsing happens in background via Cloud Tasks.

    The original file is processed in memory and never stored.
    Only the extracted metadata and vector are persisted.

    Poll GET /profile or GET /profile/resume for processing status.
    Check is_calculating=false and vector_status='ready' for completion.

    Returns:
        202 Accepted with job_id and status 'processing'.

    Errors:
        400: Unsupported file format (not PDF or DOCX)
        413: File too large (exceeds 5MB)
    """
    user, _ = auth

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Resume must be under 5MB")

    try:
        result = await initiate_resume_processing(
            db,
            user.id,
            file_bytes,
            file.filename or "resume",
            file.content_type,
        )
    except (UnsupportedFormatError, FileTooLargeError) as e:
        raise _handle_resume_error(e)

    return ResumeUploadAcceptedResponse(
        job_id=result["job_id"],
        status=result["status"],
        message=result["message"],
    )


@router.get("/resume", response_model=ResumeDataResponse)
async def get_resume(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ResumeDataResponse:
    """
    Returns stored resume data.

    If is_calculating is true, resume is still being processed.
    Check vector_status for embedding completion status.

    Returns:
        ResumeDataResponse with extracted skills and job titles.

    Errors:
        404: No resume data found; use POST /profile/resume first.
    """
    user, _ = auth

    data = await get_resume_data(db, user.id)

    if data is None:
        raise HTTPException(status_code=404, detail="No resume data found. Upload a resume first.")

    return ResumeDataResponse(
        status=data["status"],
        skills=data["skills"],
        job_titles=data["job_titles"],
        vector_status=data["vector_status"],
        uploaded_at=data["uploaded_at"],
    )


@router.delete("/resume")
async def delete_resume_data(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Clears resume data and vector.

    Triggers combined_vector recalculation from remaining sources.

    Returns:
        Confirmation of deletion.

    Errors:
        404: No resume data to delete.
    """
    user, _ = auth

    was_deleted = await delete_resume(db, user.id)

    if not was_deleted:
        raise HTTPException(status_code=404, detail="No resume data to delete")

    return {"deleted": True, "message": "Resume data cleared"}
