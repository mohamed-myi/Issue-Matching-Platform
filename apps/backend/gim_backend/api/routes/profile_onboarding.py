"""Onboarding API routes for tracking onboarding progress."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from gim_database.models.identity import Session, User
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.dependencies import get_db
from gim_backend.core.errors import InvalidTaxonomyValueError
from gim_backend.middleware.auth import require_auth
from gim_backend.services.onboarding_service import (
    CannotCompleteOnboardingError,
    OnboardingAlreadyCompletedError,
    complete_onboarding,
    get_onboarding_status,
    skip_onboarding,
    start_onboarding,
)
from gim_backend.services.profile_service import (
    put_intent as put_intent_service,
)
from gim_backend.services.profile_service import (
    update_preferences as update_preferences_service,
)
from gim_backend.services.recommendation_preview_service import (
    InvalidSourceError,
    PreviewIssue,
    get_preview_recommendations,
)

router = APIRouter()

OnboardingServiceFn = Callable[..., Awaitable[Any]]
OnboardingServiceResolver = Callable[[], OnboardingServiceFn]
OnboardingArgsBuilder = Callable[[AsyncSession, User, BaseModel | None], dict[str, Any]]
OnboardingResponseTransformer = Callable[[Any], dict[str, Any]]
OnboardingPayloadValidator = Callable[[BaseModel], None]


@dataclass(frozen=True)
class OnboardingStepHandler:
    payload_model: type[BaseModel] | None
    service_fn_resolver: OnboardingServiceResolver
    build_service_kwargs: OnboardingArgsBuilder
    response_transformer: OnboardingResponseTransformer
    invalid_payload_detail: str | None = None
    payload_validator: OnboardingPayloadValidator | None = None
    error_status_by_exception: dict[type[Exception], int] = field(default_factory=dict)


class OnboardingStatusResponse(BaseModel):
    status: str
    completed_steps: list[str]
    available_steps: list[str]
    can_complete: bool


class OnboardingStartResponse(OnboardingStatusResponse):
    action: str


class OnboardingStepIntentInput(BaseModel):
    languages: list[str] = Field(..., min_length=1, max_length=10)
    stack_areas: list[str] = Field(..., min_length=1)
    text: str = Field(..., min_length=10, max_length=2000)
    experience_level: str | None = Field(default=None)


class OnboardingStepPreferencesInput(BaseModel):
    preferred_languages: list[str] | None = Field(default=None)
    preferred_topics: list[str] | None = Field(default=None)
    min_heat_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class OnboardingStepResponse(OnboardingStatusResponse):
    step: str
    payload: dict[str, Any]


class PreviewRecommendationsResponse(BaseModel):
    source: str | None
    issues: list[PreviewIssue]


def _translate_step_service_error(exc: Exception, handler: OnboardingStepHandler) -> HTTPException | None:
    for exc_type, status_code in handler.error_status_by_exception.items():
        if isinstance(exc, exc_type):
            return HTTPException(status_code=status_code, detail=str(exc))
    return None


async def _parse_step_payload(request: Request, handler: OnboardingStepHandler) -> BaseModel | None:
    if handler.payload_model is None:
        return None

    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        payload = handler.payload_model.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=handler.invalid_payload_detail or "Invalid payload") from exc

    if handler.payload_validator is not None:
        handler.payload_validator(payload)

    return payload


async def _execute_onboarding_step_handler(
    *,
    handler: OnboardingStepHandler,
    request: Request,
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    payload_model = await _parse_step_payload(request, handler)
    service_kwargs = handler.build_service_kwargs(db, user, payload_model)
    service_fn = handler.service_fn_resolver()

    try:
        service_result = await service_fn(**service_kwargs)
    except Exception as exc:
        translated = _translate_step_service_error(exc, handler)
        if translated is not None:
            raise translated from exc
        raise

    return handler.response_transformer(service_result)


def _build_welcome_step_kwargs(db: AsyncSession, user: User, payload: BaseModel | None) -> dict[str, Any]:
    del payload
    return {"db": db, "user_id": user.id}


def _build_intent_step_kwargs(db: AsyncSession, user: User, payload: BaseModel | None) -> dict[str, Any]:
    if not isinstance(payload, OnboardingStepIntentInput):
        raise HTTPException(status_code=422, detail="Invalid intent payload")
    return {
        "db": db,
        "user_id": user.id,
        "languages": payload.languages,
        "stack_areas": payload.stack_areas,
        "text": payload.text,
        "experience_level": payload.experience_level,
    }


def _build_preferences_step_kwargs(db: AsyncSession, user: User, payload: BaseModel | None) -> dict[str, Any]:
    if not isinstance(payload, OnboardingStepPreferencesInput):
        raise HTTPException(status_code=422, detail="Invalid preferences payload")
    return {
        "db": db,
        "user_id": user.id,
        "preferred_languages": payload.preferred_languages,
        "preferred_topics": payload.preferred_topics,
        "min_heat_threshold": payload.min_heat_threshold,
    }


def _validate_preferences_step_payload(payload: BaseModel) -> None:
    if not isinstance(payload, OnboardingStepPreferencesInput):
        raise HTTPException(status_code=422, detail="Invalid preferences payload")
    if not payload.model_dump(exclude_unset=True):
        raise HTTPException(status_code=400, detail="No preferences fields provided")


def _transform_welcome_step_payload(result: Any) -> dict[str, Any]:
    return {"action": result.action}


def _transform_intent_step_payload(result: Any) -> dict[str, Any]:
    profile, created = result
    return {
        "created": created,
        "intent": {
            "languages": profile.preferred_languages or [],
            "stack_areas": profile.intent_stack_areas or [],
            "text": profile.intent_text or "",
            "experience_level": profile.intent_experience,
            "vector_status": "ready" if profile.intent_vector else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        },
    }


def _transform_preferences_step_payload(profile: Any) -> dict[str, Any]:
    return {
        "preferences": {
            "preferred_languages": profile.preferred_languages or [],
            "preferred_topics": profile.preferred_topics or [],
            "min_heat_threshold": profile.min_heat_threshold,
        }
    }


def _resolve_start_onboarding_service() -> OnboardingServiceFn:
    return start_onboarding


def _resolve_put_intent_service() -> OnboardingServiceFn:
    return put_intent_service


def _resolve_update_preferences_service() -> OnboardingServiceFn:
    return update_preferences_service


ONBOARDING_STEP_HANDLERS: dict[str, OnboardingStepHandler] = {
    "welcome": OnboardingStepHandler(
        payload_model=None,
        service_fn_resolver=_resolve_start_onboarding_service,
        build_service_kwargs=_build_welcome_step_kwargs,
        response_transformer=_transform_welcome_step_payload,
        error_status_by_exception={OnboardingAlreadyCompletedError: 409},
    ),
    "intent": OnboardingStepHandler(
        payload_model=OnboardingStepIntentInput,
        service_fn_resolver=_resolve_put_intent_service,
        build_service_kwargs=_build_intent_step_kwargs,
        response_transformer=_transform_intent_step_payload,
        invalid_payload_detail="Invalid intent payload",
        error_status_by_exception={InvalidTaxonomyValueError: 400},
    ),
    "preferences": OnboardingStepHandler(
        payload_model=OnboardingStepPreferencesInput,
        service_fn_resolver=_resolve_update_preferences_service,
        build_service_kwargs=_build_preferences_step_kwargs,
        response_transformer=_transform_preferences_step_payload,
        invalid_payload_detail="Invalid preferences payload",
        payload_validator=_validate_preferences_step_payload,
        error_status_by_exception={InvalidTaxonomyValueError: 400},
    ),
}


@router.get("/onboarding", response_model=OnboardingStatusResponse)
async def get_onboarding(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    user, _ = auth
    state = await get_onboarding_status(db, user.id)

    return OnboardingStatusResponse(
        status=state.status,
        completed_steps=state.completed_steps,
        available_steps=state.available_steps,
        can_complete=state.can_complete,
    )


@router.post("/onboarding/start", response_model=OnboardingStartResponse)
async def start_onboarding_route(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStartResponse:
    user, _ = auth

    try:
        result = await start_onboarding(db, user.id)
    except OnboardingAlreadyCompletedError as e:
        raise HTTPException(status_code=409, detail=str(e))

    state = result.state
    return OnboardingStartResponse(
        status=state.status,
        completed_steps=state.completed_steps,
        available_steps=state.available_steps,
        can_complete=state.can_complete,
        action=result.action,
    )


@router.patch("/onboarding/step/{step}", response_model=OnboardingStepResponse)
async def save_onboarding_step(
    step: str,
    request: Request,
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStepResponse:
    user, _ = auth

    handler = ONBOARDING_STEP_HANDLERS.get(step)
    if handler is None:
        raise HTTPException(status_code=400, detail="Invalid onboarding step")

    payload = await _execute_onboarding_step_handler(
        handler=handler,
        request=request,
        db=db,
        user=user,
    )

    state = await get_onboarding_status(db, user.id)
    return OnboardingStepResponse(
        status=state.status,
        completed_steps=state.completed_steps,
        available_steps=state.available_steps,
        can_complete=state.can_complete,
        step=step,
        payload=payload,
    )


@router.post("/onboarding/complete", response_model=OnboardingStatusResponse)
async def complete_onboarding_route(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    user, _ = auth

    try:
        state = await complete_onboarding(db, user.id)
    except CannotCompleteOnboardingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OnboardingAlreadyCompletedError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return OnboardingStatusResponse(
        status=state.status,
        completed_steps=state.completed_steps,
        available_steps=state.available_steps,
        can_complete=state.can_complete,
    )


@router.post("/onboarding/skip", response_model=OnboardingStatusResponse)
async def skip_onboarding_route(
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    user, _ = auth

    try:
        state = await skip_onboarding(db, user.id)
    except OnboardingAlreadyCompletedError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return OnboardingStatusResponse(
        status=state.status,
        completed_steps=state.completed_steps,
        available_steps=state.available_steps,
        can_complete=state.can_complete,
    )


@router.get("/preview-recommendations", response_model=PreviewRecommendationsResponse)
async def get_preview_recommendations_route(
    source: str | None = Query(
        default=None,
        description="Source vector to use: intent, resume, or github. If not provided, returns trending issues.",
    ),
    auth: tuple[User, Session] = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> PreviewRecommendationsResponse:
    user, _ = auth

    try:
        issues = await get_preview_recommendations(db, user.id, source)
    except InvalidSourceError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PreviewRecommendationsResponse(
        source=source,
        issues=issues,
    )
