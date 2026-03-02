"""
Onboarding service for tracking user onboarding progress and state transitions.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from gim_database.models.profiles import UserProfile
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.errors import CannotCompleteOnboardingError, OnboardingAlreadyCompletedError
from gim_backend.services.profile_access import get_or_create_profile_record as _get_or_create_profile

ALL_STEPS = ["welcome", "intent", "github", "resume", "preferences"]


@dataclass
class OnboardingState:
    status: str
    completed_steps: list[str]
    available_steps: list[str]
    can_complete: bool


@dataclass
class OnboardingStartResult:
    state: OnboardingState
    action: str


def _get_completed_steps(profile: UserProfile) -> list[str]:
    completed = []

    if profile.onboarding_status != "not_started":
        completed.append("welcome")

    if profile.intent_text is not None:
        completed.append("intent")

    if profile.github_username is not None:
        completed.append("github")

    if profile.resume_skills is not None:
        completed.append("resume")

    if profile.preferred_languages is not None:
        completed.append("preferences")

    return completed


def _get_available_steps(completed_steps: list[str]) -> list[str]:
    return [step for step in ALL_STEPS if step not in completed_steps]


def _can_complete(profile: UserProfile) -> bool:
    """Skip is handled separately and does not require sources."""
    return profile.intent_text is not None or profile.resume_skills is not None or profile.github_username is not None


def compute_onboarding_state(profile: UserProfile) -> OnboardingState:
    completed_steps = _get_completed_steps(profile)
    available_steps = _get_available_steps(completed_steps)
    can_complete = _can_complete(profile)

    return OnboardingState(
        status=profile.onboarding_status,
        completed_steps=completed_steps,
        available_steps=available_steps,
        can_complete=can_complete,
    )


async def get_onboarding_status(
    db: AsyncSession,
    user_id: UUID,
) -> OnboardingState:
    profile = await _get_or_create_profile(db, user_id)
    return compute_onboarding_state(profile)


async def complete_onboarding(
    db: AsyncSession,
    user_id: UUID,
) -> OnboardingState:
    """Requires at least one source; raises CannotCompleteOnboardingError otherwise."""
    profile = await _get_or_create_profile(db, user_id)

    if profile.onboarding_status in ("completed", "skipped"):
        raise OnboardingAlreadyCompletedError(f"Onboarding already {profile.onboarding_status}")

    if not _can_complete(profile):
        raise CannotCompleteOnboardingError("Cannot complete onboarding without at least one profile source")

    profile.onboarding_status = "completed"
    profile.onboarding_completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(profile)

    return compute_onboarding_state(profile)


async def skip_onboarding(
    db: AsyncSession,
    user_id: UUID,
) -> OnboardingState:
    """Can be called without any profile sources."""
    profile = await _get_or_create_profile(db, user_id)

    if profile.onboarding_status in ("completed", "skipped"):
        raise OnboardingAlreadyCompletedError(f"Onboarding already {profile.onboarding_status}")

    profile.onboarding_status = "skipped"
    profile.onboarding_completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(profile)

    return compute_onboarding_state(profile)


async def start_onboarding(
    db: AsyncSession,
    user_id: UUID,
) -> OnboardingStartResult:
    profile = await _get_or_create_profile(db, user_id)
    current = profile.onboarding_status

    if current == "completed":
        raise OnboardingAlreadyCompletedError("Onboarding already completed")

    if current == "in_progress":
        return OnboardingStartResult(
            state=compute_onboarding_state(profile),
            action="noop",
        )

    if current == "skipped":
        profile.onboarding_status = "in_progress"
        profile.onboarding_completed_at = None
        await db.commit()
        await db.refresh(profile)
        return OnboardingStartResult(
            state=compute_onboarding_state(profile),
            action="restarted",
        )

    profile.onboarding_status = "in_progress"
    await db.commit()
    await db.refresh(profile)
    return OnboardingStartResult(
        state=compute_onboarding_state(profile),
        action="started",
    )


async def mark_onboarding_in_progress(
    db: AsyncSession,
    profile: UserProfile,
) -> None:
    if profile.onboarding_status == "not_started":
        profile.onboarding_status = "in_progress"
        return

    if profile.onboarding_status == "skipped":
        profile.onboarding_status = "in_progress"
        profile.onboarding_completed_at = None


__all__ = [
    "OnboardingState",
    "OnboardingStartResult",
    "ALL_STEPS",
    "compute_onboarding_state",
    "get_onboarding_status",
    "complete_onboarding",
    "skip_onboarding",
    "start_onboarding",
    "mark_onboarding_in_progress",
]
