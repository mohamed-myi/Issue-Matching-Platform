"""
Taxonomy service for reference data APIs.
Thin wrapper around constants for API consistency.
"""

from dataclasses import dataclass

from gim_shared.constants import PROFILE_LANGUAGES, STACK_AREAS


@dataclass
class StackAreaInfo:
    """Stack area with display label and description."""

    id: str
    label: str
    description: str


def get_languages() -> list[str]:
    """Returns valid language list from PROFILE_LANGUAGES."""
    return list(PROFILE_LANGUAGES)


def get_stack_areas() -> list[StackAreaInfo]:
    """Returns stack areas with id, label, description."""
    return [
        StackAreaInfo(
            id=key,
            label=key.replace("_", " ").title(),
            description=desc,
        )
        for key, desc in STACK_AREAS.items()
    ]


__all__ = [
    "StackAreaInfo",
    "get_languages",
    "get_stack_areas",
]
