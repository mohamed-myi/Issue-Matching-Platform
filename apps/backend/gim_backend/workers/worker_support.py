"""Shared helpers for Cloud Tasks-backed worker services."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from gim_database.models.profiles import UserProfile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


def verify_cloud_tasks_token(
    x_cloudtasks_taskname: str | None,
    authorization: str | None,
    *,
    audience: str | None,
    settings: Any,
    verify_oidc_bearer_token_fn,
) -> bool:
    """Verifies Cloud Tasks header presence plus OIDC token in production."""
    if settings.environment == "development":
        return True

    if not x_cloudtasks_taskname:
        return False

    return verify_oidc_bearer_token_fn(authorization, audience)


def expected_cloud_tasks_service_account(settings: Any) -> str | None:
    """Computes the expected Cloud Tasks service account email."""
    if settings.cloud_tasks_service_account_email:
        return settings.cloud_tasks_service_account_email
    if settings.gcp_project:
        return f"{settings.gcp_project}@appspot.gserviceaccount.com"
    return None


def verify_oidc_bearer_token(
    authorization: str | None,
    audience: str | None,
    *,
    settings: Any,
    logger: logging.Logger,
) -> bool:
    """Validates Cloud Tasks OIDC bearer token and issuer/email claims."""
    if not authorization:
        return False
    if not audience:
        logger.error("Cloud Tasks OIDC verification failed: audience not configured")
        return False

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError:
        logger.error("google-auth is required for Cloud Tasks OIDC verification")
        return False

    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=audience,
        )
    except Exception as e:
        logger.warning(f"Cloud Tasks OIDC verification failed: {e}")
        return False

    issuer = claims.get("iss")
    if issuer not in ("https://accounts.google.com", "accounts.google.com"):
        return False

    expected_email = expected_cloud_tasks_service_account(settings)
    token_email = claims.get("email")
    if expected_email and token_email != expected_email:
        return False

    email_verified = claims.get("email_verified")
    if email_verified not in (True, "true", "True", None):
        return False

    return True


def build_worker_audience(base_url: str | None, path: str) -> str | None:
    """Builds a Cloud Tasks OIDC audience for a worker endpoint path."""
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}{path}"


async def get_profile_by_user_id(db: AsyncSession, user_id: UUID) -> UserProfile | None:
    """Fetches a user profile by user ID for worker pipelines."""
    statement = select(UserProfile).where(UserProfile.user_id == user_id)
    result = await db.exec(statement)
    return result.first()


def build_health_response(service: str) -> dict[str, str]:
    """Standard worker health endpoint payload."""
    return {"status": "ok", "service": service}
