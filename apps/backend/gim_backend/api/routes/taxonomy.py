"""
Taxonomy API routes for reference data.
All endpoints are public (no authentication required).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from gim_backend.services.taxonomy_service import (
    get_languages,
    get_stack_areas,
)

router = APIRouter()


class LanguagesResponse(BaseModel):
    """Valid programming languages for profile and filters."""

    languages: list[str]


class StackAreaOutput(BaseModel):
    """Single stack area with label and description."""

    id: str
    label: str
    description: str


class StackAreasResponse(BaseModel):
    """Valid stack areas for intent form."""

    stack_areas: list[StackAreaOutput]


@router.get("/languages", response_model=LanguagesResponse)
async def get_languages_route() -> LanguagesResponse:
    """
    Returns valid language values for forms and filters.

    No authentication required. Static data.
    Used for intent form, preferences, and search filters.
    """
    languages = get_languages()
    return LanguagesResponse(languages=languages)


@router.get("/stack-areas", response_model=StackAreasResponse)
async def get_stack_areas_route() -> StackAreasResponse:
    """
    Returns valid stack area values for intent form.

    No authentication required. Static data.
    Used for Quick Start cards in onboarding.
    """
    areas = get_stack_areas()
    return StackAreasResponse(
        stack_areas=[StackAreaOutput(id=a.id, label=a.label, description=a.description) for a in areas]
    )
