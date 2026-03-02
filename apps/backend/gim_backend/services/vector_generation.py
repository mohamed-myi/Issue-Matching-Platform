"""
Vector generation wrapper with retry support.
Provides synchronous retry with exponential backoff for embedding operations.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from gim_backend.services.embedding_service import embed_document
from gim_backend.services.profile_embedding_service import generate_intent_vector as _generate_intent_vector

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1


async def _generate_vector_with_retry(
    *,
    operation_label: str,
    retry_label: str,
    operation: Callable[[], Awaitable[list[float] | None]],
    max_retries: int,
) -> list[float] | None:
    """Shared retry loop for vector generation wrappers."""
    for attempt in range(max_retries):
        try:
            vector = await operation()
            if vector is not None:
                return vector

            logger.warning(f"{operation_label} vector returned None on attempt {attempt + 1}/{max_retries}")

        except Exception as e:
            logger.warning(f"{operation_label} vector generation failed on attempt {attempt + 1}/{max_retries}: {e}")

        if attempt < max_retries - 1:
            backoff = BASE_BACKOFF_SECONDS * (2**attempt)
            logger.info(f"Retrying {retry_label} vector in {backoff}s")
            await asyncio.sleep(backoff)

    logger.error(f"{operation_label} vector generation permanently failed after {max_retries} attempts")
    return None


async def generate_intent_vector_with_retry(
    stack_areas: list[str],
    text: str,
    max_retries: int = MAX_RETRIES,
) -> list[float] | None:
    """
    Generates intent vector with exponential backoff retry.
    Returns None if all retries fail; logs error but does not raise.
    """
    return await _generate_vector_with_retry(
        operation_label="Intent",
        retry_label="intent",
        operation=lambda: _generate_intent_vector(stack_areas, text),
        max_retries=max_retries,
    )


async def generate_resume_vector_with_retry(
    markdown_text: str,
    max_retries: int = MAX_RETRIES,
) -> list[float] | None:
    """
    Generates resume vector with exponential backoff retry.
    Returns None if all retries fail; logs error but does not raise.
    """
    return await _generate_vector_with_retry(
        operation_label="Resume",
        retry_label="resume",
        operation=lambda: embed_document(markdown_text),
        max_retries=max_retries,
    )


async def generate_github_vector_with_retry(
    text: str,
    max_retries: int = MAX_RETRIES,
) -> list[float] | None:
    """
    Generates GitHub vector with exponential backoff retry.
    Returns None if all retries fail; logs error but does not raise.
    """
    return await _generate_vector_with_retry(
        operation_label="GitHub",
        retry_label="GitHub",
        operation=lambda: embed_document(text),
        max_retries=max_retries,
    )


__all__ = [
    "generate_intent_vector_with_retry",
    "generate_resume_vector_with_retry",
    "generate_github_vector_with_retry",
    "MAX_RETRIES",
    "BASE_BACKOFF_SECONDS",
]
