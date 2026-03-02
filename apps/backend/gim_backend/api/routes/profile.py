"""Profile API routes. All endpoints require authentication."""

from fastapi import APIRouter, Depends, HTTPException, Response
from gim_database.models.identity import Session, User
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.core.errors import (
    IntentAlreadyExistsError,
    IntentNotFoundError,
    InvalidTaxonomyValueError,
)
from gim_backend.middleware.auth import require_auth
from gim_backend.services.profile_service import (
    FullProfile,
    IntentProfile,
    ProfilePreferences,
    get_full_profile,
    get_or_create_profile,
)
from gim_backend.services.profile_service import (
    create_intent as create_intent_service,
)
from gim_backend.services.profile_service import (
    delete_intent as delete_intent_service,
)
from gim_backend.services.profile_service import (
    delete_profile as delete_profile_service,
)
from gim_backend.services.profile_service import (
    get_intent as get_intent_service,
)
from gim_backend.services.profile_service import (
    get_preferences as get_preferences_service,
)
from gim_backend.services.profile_service import (
    put_intent as put_intent_service,
)
from gim_backend.services.profile_service import (
    update_intent as update_intent_service,
)
from gim_backend.services.profile_service import (
    update_preferences as update_preferences_service,
)

router = APIRouter()


class IntentCreateInput(BaseModel):
    languages: list[str] = Field(..., min_length=1, max_length=10)
    stack_areas: list[str] = Field(..., min_length=1)
    text: str = Field(..., min_length=10, max_length=2000)
    experience_level: str | None = Field(default=None)


class IntentUpdateInput(BaseModel):
    languages: list[str] | None = Field(default=None, min_length=1, max_length=10)
    stack_areas: list[str] | None = Field(default=None, min_length=1)
    text: str | None = Field(default=None, min_length=10, max_length=2000)
    experience_level: str | None = Field(default=None)


class PreferencesUpdateInput(BaseModel):
    preferred_languages: list[str] | None = Field(default=None)
    preferred_topics: list[str] | None = Field(default=None)
    min_heat_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class ProcessingStatusOutput(BaseModel):
    is_calculating: bool
    intent_status: str
    resume_status: str
    github_status: str
    intent_vector_status: str | None
    resume_vector_status: str | None
    github_vector_status: str | None
    combined_vector_status: str | None


@router.get("", response_model=FullProfile)
async def get_profile(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> FullProfile:
    user, _ = auth
    return await get_full_profile(db, user.id)


@router.delete("")
async def delete_profile(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, _ = auth
    was_deleted = await delete_profile_service(db, user.id)

    return {
        "deleted": was_deleted,
        "message": "Profile cleared" if was_deleted else "No profile data to clear",
    }


@router.post("/intent", response_model=IntentProfile, status_code=201)
async def create_intent(
    body: IntentCreateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> IntentProfile:
    user, _ = auth

    try:
        profile = await create_intent_service(
            db=db,
            user_id=user.id,
            languages=body.languages,
            stack_areas=body.stack_areas,
            text=body.text,
            experience_level=body.experience_level,
        )
    except InvalidTaxonomyValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntentAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))

    vector_status = "ready" if profile.intent_vector else None

    return IntentProfile(
        languages=profile.preferred_languages or [],
        stack_areas=profile.intent_stack_areas or [],
        text=profile.intent_text or "",
        experience_level=profile.intent_experience,
        vector_status=vector_status,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    )


@router.get("/intent", response_model=IntentProfile)
async def get_intent(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> IntentProfile:
    user, _ = auth
    intent_data = await get_intent_service(db, user.id)

    if intent_data is None:
        raise HTTPException(status_code=404, detail="No intent data found")

    return intent_data


@router.put("/intent", response_model=IntentProfile)
async def replace_intent(
    body: IntentCreateInput,
    response: Response,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> IntentProfile:
    user, _ = auth

    try:
        profile, created = await put_intent_service(
            db=db,
            user_id=user.id,
            languages=body.languages,
            stack_areas=body.stack_areas,
            text=body.text,
            experience_level=body.experience_level,
        )
    except InvalidTaxonomyValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    response.status_code = 201 if created else 200

    vector_status = "ready" if profile.intent_vector else None

    return IntentProfile(
        languages=profile.preferred_languages or [],
        stack_areas=profile.intent_stack_areas or [],
        text=profile.intent_text or "",
        experience_level=profile.intent_experience,
        vector_status=vector_status,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    )


@router.patch("/intent", response_model=IntentProfile)
async def update_intent(
    body: IntentUpdateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> IntentProfile:
    user, _ = auth

    raw_body = body.model_dump(exclude_unset=True)
    experience_level_provided = "experience_level" in raw_body

    try:
        profile = await update_intent_service(
            db=db,
            user_id=user.id,
            languages=body.languages,
            stack_areas=body.stack_areas,
            text=body.text,
            experience_level=body.experience_level,
            _experience_level_provided=experience_level_provided,
        )
    except InvalidTaxonomyValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    vector_status = "ready" if profile.intent_vector else None

    return IntentProfile(
        languages=profile.preferred_languages or [],
        stack_areas=profile.intent_stack_areas or [],
        text=profile.intent_text or "",
        experience_level=profile.intent_experience,
        vector_status=vector_status,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    )


@router.delete("/intent")
async def delete_intent(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, _ = auth
    was_deleted = await delete_intent_service(db, user.id)

    if not was_deleted:
        raise HTTPException(status_code=404, detail="No intent data to delete")

    return {"deleted": True, "message": "Intent cleared"}


@router.get("/processing-status", response_model=ProcessingStatusOutput)
async def get_processing_status(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ProcessingStatusOutput:
    user, _ = auth
    profile = await get_or_create_profile(db, user.id)

    def _status(data_present: bool, vector_present: bool) -> str:
        if vector_present:
            return "ready"
        if profile.is_calculating and data_present:
            return "processing"
        if data_present and not profile.is_calculating:
            return "failed"
        return "not_started"

    intent_data_present = profile.intent_text is not None
    resume_data_present = profile.resume_skills is not None
    github_data_present = profile.github_username is not None

    intent_vector_present = profile.intent_vector is not None
    resume_vector_present = profile.resume_vector is not None
    github_vector_present = profile.github_vector is not None
    combined_vector_present = profile.combined_vector is not None

    return ProcessingStatusOutput(
        is_calculating=profile.is_calculating,
        intent_status=_status(intent_data_present, intent_vector_present),
        resume_status=_status(resume_data_present, resume_vector_present),
        github_status=_status(github_data_present, github_vector_present),
        intent_vector_status="ready" if intent_vector_present else None,
        resume_vector_status="ready" if resume_vector_present else None,
        github_vector_status="ready" if github_vector_present else None,
        combined_vector_status="ready" if combined_vector_present else None,
    )


@router.get("/preferences", response_model=ProfilePreferences)
async def get_preferences(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ProfilePreferences:
    user, _ = auth
    return await get_preferences_service(db, user.id)


@router.patch("/preferences", response_model=ProfilePreferences)
async def update_preferences(
    body: PreferencesUpdateInput,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ProfilePreferences:
    user, _ = auth

    try:
        profile = await update_preferences_service(
            db=db,
            user_id=user.id,
            preferred_languages=body.preferred_languages,
            preferred_topics=body.preferred_topics,
            min_heat_threshold=body.min_heat_threshold,
        )
    except InvalidTaxonomyValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ProfilePreferences(
        preferred_languages=profile.preferred_languages or [],
        preferred_topics=profile.preferred_topics or [],
        min_heat_threshold=profile.min_heat_threshold,
    )
