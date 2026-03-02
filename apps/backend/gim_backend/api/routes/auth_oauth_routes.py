import secrets
from collections.abc import Awaitable, Callable
from enum import StrEnum
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.routes import auth as auth_mod

router = APIRouter()

STATE_COOKIE_NAME = "oauth_state"
STATE_COOKIE_MAX_AGE = 300


class AuthIntent(StrEnum):
    LOGIN = "login"
    LINK = "link"
    CONNECT = "connect"


def _get_state_cookie_params(settings) -> dict:
    is_production = settings.environment == "production"
    params: dict = {
        "httponly": True,
        "secure": is_production,
        "samesite": "lax",
        "max_age": STATE_COOKIE_MAX_AGE,
        "path": "/",
    }
    domain = auth_mod._cookie_domain_or_none()
    if domain:
        params["domain"] = domain
    return params


def _delete_state_cookie(response) -> None:
    """Delete the OAuth state cookie with matching attributes so the browser clears it."""
    kwargs: dict = {"key": STATE_COOKIE_NAME, "path": "/"}
    domain = auth_mod._cookie_domain_or_none()
    if domain:
        kwargs["domain"] = domain
    response.delete_cookie(**kwargs)


def _build_error_redirect(error_code: str, provider: str | None = None) -> str:
    settings = auth_mod.get_settings()
    params = {"error": error_code}
    if provider:
        params["provider"] = provider
    return f"{settings.frontend_base_url}/login?{urlencode(params)}"


def _build_settings_redirect(error_code: str | None = None) -> str:
    settings = auth_mod.get_settings()
    base = f"{settings.frontend_base_url}/settings/accounts"
    if error_code:
        return f"{base}?{urlencode({'error': error_code})}"
    return base


def _build_profile_redirect(error_code: str | None = None, success: bool = False) -> str:
    """Builds redirect URL to profile onboarding page"""
    settings = auth_mod.get_settings()
    base = f"{settings.frontend_base_url}/profile/onboarding"
    if error_code:
        return f"{base}?{urlencode({'error': error_code})}"
    if success:
        return f"{base}?{urlencode({'connected': 'github'})}"
    return base


@router.get("/init", status_code=204)
async def init_login_flow() -> Response:
    """Sets X-Login-Flow-ID cookie for rate limiting compound key"""
    flow_id = secrets.token_urlsafe(16)
    response = Response(status_code=204)
    auth_mod.create_login_flow_cookie(response, flow_id)
    return response


@router.get("/login/{provider}")
async def login(
    provider: str,
    request: Request,
    remember_me: bool = Query(default=False),
    _: None = Depends(auth_mod.check_auth_rate_limit),
) -> RedirectResponse:
    try:
        oauth_provider = auth_mod.OAuthProvider(provider)
    except ValueError:
        return RedirectResponse(
            url=_build_error_redirect("invalid_provider"),
            status_code=302,
        )

    settings = auth_mod.get_settings()
    state_token = secrets.token_urlsafe(32)
    state_value = f"{AuthIntent.LOGIN.value}:{state_token}:{1 if remember_me else 0}"

    redirect_uri = f"{settings.api_base_url}/auth/callback/{provider}"
    auth_url = auth_mod.get_authorization_url(oauth_provider, redirect_uri, state_value)
    response = RedirectResponse(url=auth_url, status_code=302)

    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state_token,
        **_get_state_cookie_params(settings),
    )

    return response


@router.get("/callback/{provider}")
async def callback(
    provider: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    fingerprint_hash: str | None = Depends(auth_mod.optional_fingerprint),
    ctx: auth_mod.RequestContext = Depends(auth_mod.get_request_context),
    db: AsyncSession = Depends(auth_mod.get_db),
    client: httpx.AsyncClient = Depends(auth_mod.get_http_client),
    _: None = Depends(auth_mod.check_auth_rate_limit),
) -> RedirectResponse:
    settings = auth_mod.get_settings()

    if error:
        return RedirectResponse(
            url=_build_error_redirect("consent_denied"),
            status_code=302,
        )

    try:
        oauth_provider = auth_mod.OAuthProvider(provider)
    except ValueError:
        return RedirectResponse(
            url=_build_error_redirect("invalid_provider"),
            status_code=302,
        )

    if not state or not code:
        return RedirectResponse(
            url=_build_error_redirect("missing_code"),
            status_code=302,
        )

    try:
        state_parts = state.split(":", 2)
        intent = state_parts[0]
        state_token = state_parts[1]
        extra = state_parts[2] if len(state_parts) > 2 else None
    except Exception:
        return RedirectResponse(
            url=_build_error_redirect("csrf_failed"),
            status_code=302,
        )

    stored_token = request.cookies.get(STATE_COOKIE_NAME)

    if not stored_token or stored_token != state_token:
        if intent == AuthIntent.LINK.value:
            return RedirectResponse(url=_build_settings_redirect("csrf_failed"), status_code=302)
        if intent == AuthIntent.CONNECT.value:
            return RedirectResponse(url=_build_profile_redirect("csrf_failed"), status_code=302)

        return RedirectResponse(
            url=_build_error_redirect("csrf_failed"),
            status_code=302,
        )

    redirect_uri = f"{settings.api_base_url}/auth/callback/{provider}"

    if intent == AuthIntent.LOGIN.value:
        remember_me = extra == "1"
        return await _handle_login_callback(
            code,
            redirect_uri,
            oauth_provider,
            remember_me,
            fingerprint_hash,
            ctx,
            db,
            client,
            request,
            settings,
        )

    if intent == AuthIntent.LINK.value:
        return await _handle_link_callback(code, redirect_uri, oauth_provider, ctx, db, client, request)

    if intent == AuthIntent.CONNECT.value:
        return await _handle_connect_callback(code, redirect_uri, oauth_provider, ctx, db, client, request)

    return RedirectResponse(url=_build_error_redirect("invalid_request"), status_code=302)


@router.get("/link/{provider}")
async def link(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
    _: None = Depends(auth_mod.check_auth_rate_limit),
) -> RedirectResponse:
    """Initiates OAuth flow to link additional provider to authenticated user"""
    try:
        oauth_provider = auth_mod.OAuthProvider(provider)
    except ValueError:
        return RedirectResponse(
            url=_build_settings_redirect("invalid_provider"),
            status_code=302,
        )

    ctx = await auth_mod.get_request_context(request)

    try:
        _ = await auth_mod.get_current_session(request, ctx, db)
    except Exception:
        return RedirectResponse(
            url=_build_error_redirect("not_authenticated"),
            status_code=302,
        )

    settings = auth_mod.get_settings()
    state_token = secrets.token_urlsafe(32)
    state_value = f"{AuthIntent.LINK.value}:{state_token}"
    redirect_uri = f"{settings.api_base_url}/auth/callback/{provider}"

    auth_url = auth_mod.get_authorization_url(oauth_provider, redirect_uri, state_value)
    response = RedirectResponse(url=auth_url, status_code=302)

    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state_token,
        **_get_state_cookie_params(settings),
    )

    return response


@router.get("/connect/github")
async def connect_github(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
    _: None = Depends(auth_mod.check_auth_rate_limit),
) -> RedirectResponse:
    """
    Initiates GitHub OAuth flow for profile data access.
    Uses different scopes than login (includes repo access for activity data).
    Requires authenticated session.
    """
    ctx = await auth_mod.get_request_context(request)

    try:
        _, _session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        return RedirectResponse(
            url=_build_error_redirect("not_authenticated"),
            status_code=302,
        )

    settings = auth_mod.get_settings()
    state_token = secrets.token_urlsafe(32)
    state_value = f"{AuthIntent.CONNECT.value}:{state_token}"
    redirect_uri = f"{settings.api_base_url}/auth/callback/github"

    auth_url = auth_mod.get_profile_authorization_url(auth_mod.OAuthProvider.GITHUB, redirect_uri, state_value)
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state_token,
        **_get_state_cookie_params(settings),
    )
    return response


async def _execute_oauth_callback(
    *,
    code: str,
    redirect_uri: str,
    oauth_provider: auth_mod.OAuthProvider,
    client: httpx.AsyncClient,
    on_success: Callable[[auth_mod.OAuthToken, auth_mod.UserProfile], Awaitable[RedirectResponse]],
    on_error: Callable[[Exception], Awaitable[RedirectResponse]],
) -> RedirectResponse:
    """Shared callback template: exchange code, fetch provider profile, then execute flow-specific logic."""
    try:
        token = await auth_mod.exchange_code_for_token(oauth_provider, code, redirect_uri, client)
        profile = await auth_mod.fetch_user_profile(oauth_provider, token, client)
        return await on_success(token, profile)
    except (
        auth_mod.InvalidCodeError,
        auth_mod.EmailNotVerifiedError,
        auth_mod.NoEmailError,
        auth_mod.ExistingAccountError,
        auth_mod.ProviderConflictError,
        auth_mod.OAuthStateError,
        auth_mod.OAuthError,
    ) as exc:
        return await on_error(exc)


def _settings_callback_error_redirect(exc: Exception) -> RedirectResponse:
    if isinstance(exc, auth_mod.InvalidCodeError):
        return RedirectResponse(url=_build_settings_redirect("code_expired"), status_code=302)
    if isinstance(exc, auth_mod.EmailNotVerifiedError):
        return RedirectResponse(url=_build_settings_redirect("email_not_verified"), status_code=302)
    if isinstance(exc, auth_mod.NoEmailError):
        return RedirectResponse(url=_build_settings_redirect("no_email"), status_code=302)
    if isinstance(exc, auth_mod.ProviderConflictError):
        return RedirectResponse(url=_build_settings_redirect("provider_conflict"), status_code=302)
    if isinstance(exc, auth_mod.OAuthError):
        return RedirectResponse(url=_build_settings_redirect("oauth_unavailable"), status_code=302)
    raise exc


def _profile_connect_callback_error_redirect(
    exc: Exception,
    *,
    user_id,
    ctx: auth_mod.RequestContext,
) -> RedirectResponse:
    if isinstance(exc, auth_mod.InvalidCodeError):
        auth_mod.log_audit_event(
            auth_mod.AuditEvent.ACCOUNT_LINKED,
            user_id=user_id,
            ip_address=ctx.ip_address,
            provider="github",
            metadata={"action": "connect_failed", "reason": "code_expired"},
        )
        return RedirectResponse(url=_build_profile_redirect("code_expired"), status_code=302)
    if isinstance(exc, auth_mod.EmailNotVerifiedError):
        return RedirectResponse(url=_build_profile_redirect("email_not_verified"), status_code=302)
    if isinstance(exc, auth_mod.NoEmailError):
        return RedirectResponse(url=_build_profile_redirect("no_email"), status_code=302)
    if isinstance(exc, auth_mod.OAuthError):
        return RedirectResponse(url=_build_profile_redirect("oauth_unavailable"), status_code=302)
    raise exc


def _login_callback_error_redirect(
    exc: Exception,
    *,
    oauth_provider: auth_mod.OAuthProvider,
    ctx: auth_mod.RequestContext,
) -> RedirectResponse:
    if isinstance(exc, auth_mod.InvalidCodeError):
        auth_mod.log_audit_event(
            auth_mod.AuditEvent.LOGIN_FAILED,
            ip_address=ctx.ip_address,
            provider=oauth_provider.value,
            metadata={"reason": "code_expired"},
        )
        return RedirectResponse(url=_build_error_redirect("code_expired"), status_code=302)

    if isinstance(exc, auth_mod.EmailNotVerifiedError):
        auth_mod.log_audit_event(
            auth_mod.AuditEvent.LOGIN_FAILED,
            ip_address=ctx.ip_address,
            provider=oauth_provider.value,
            metadata={"reason": "email_not_verified"},
        )
        return RedirectResponse(
            url=_build_error_redirect("email_not_verified", oauth_provider.value),
            status_code=302,
        )

    if isinstance(exc, auth_mod.NoEmailError):
        auth_mod.log_audit_event(
            auth_mod.AuditEvent.LOGIN_FAILED,
            ip_address=ctx.ip_address,
            provider=oauth_provider.value,
            metadata={"reason": "no_email"},
        )
        return RedirectResponse(
            url=_build_error_redirect("no_email", oauth_provider.value),
            status_code=302,
        )

    if isinstance(exc, auth_mod.ExistingAccountError):
        auth_mod.log_audit_event(
            auth_mod.AuditEvent.LOGIN_FAILED,
            ip_address=ctx.ip_address,
            provider=oauth_provider.value,
            metadata={"reason": "existing_account", "original_provider": exc.original_provider},
        )
        return RedirectResponse(
            url=_build_error_redirect("existing_account", exc.original_provider),
            status_code=302,
        )

    if isinstance(exc, auth_mod.OAuthStateError):
        return RedirectResponse(url=_build_error_redirect("csrf_failed"), status_code=302)

    if isinstance(exc, auth_mod.OAuthError):
        auth_mod.log_audit_event(
            auth_mod.AuditEvent.LOGIN_FAILED,
            ip_address=ctx.ip_address,
            provider=oauth_provider.value,
            metadata={"reason": "oauth_unavailable", "error": str(exc)},
        )
        return RedirectResponse(url=_build_error_redirect("oauth_unavailable"), status_code=302)

    raise exc


async def _handle_login_callback(
    code: str,
    redirect_uri: str,
    oauth_provider: auth_mod.OAuthProvider,
    remember_me: bool,
    fingerprint_hash: str,
    ctx: auth_mod.RequestContext,
    db: AsyncSession,
    client: httpx.AsyncClient,
    request: Request,
    settings,
) -> RedirectResponse:
    async def _on_success(token: auth_mod.OAuthToken, profile: auth_mod.UserProfile) -> RedirectResponse:
        user = await auth_mod.upsert_user(db, profile, oauth_provider)

        session, expires_at = await auth_mod.create_session(
            db=db,
            user_id=user.id,
            fingerprint_hash=fingerprint_hash,
            remember_me=remember_me,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            os_family=ctx.os_family,
            ua_family=ctx.ua_family,
            asn=ctx.asn,
            country_code=ctx.country_code,
        )

        auth_mod.log_audit_event(
            auth_mod.AuditEvent.LOGIN_SUCCESS,
            user_id=user.id,
            session_id=session.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            provider=oauth_provider.value,
        )

        response = RedirectResponse(
            url=f"{settings.frontend_base_url}/dashboard",
            status_code=302,
        )
        _delete_state_cookie(response)
        auth_mod.create_session_cookie(response, str(session.id), expires_at)

        return response

    async def _on_error(exc: Exception) -> RedirectResponse:
        return _login_callback_error_redirect(exc, oauth_provider=oauth_provider, ctx=ctx)

    return await _execute_oauth_callback(
        code=code,
        redirect_uri=redirect_uri,
        oauth_provider=oauth_provider,
        client=client,
        on_success=_on_success,
        on_error=_on_error,
    )


async def _handle_link_callback(
    code: str,
    redirect_uri: str,
    oauth_provider: auth_mod.OAuthProvider,
    ctx: auth_mod.RequestContext,
    db: AsyncSession,
    client: httpx.AsyncClient,
    request: Request,
) -> RedirectResponse:
    try:
        user, session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        return RedirectResponse(url=_build_error_redirect("not_authenticated"), status_code=302)

    async def _on_success(token: auth_mod.OAuthToken, profile: auth_mod.UserProfile) -> RedirectResponse:
        await auth_mod.link_provider(db, user, profile, oauth_provider)

        auth_mod.log_audit_event(
            auth_mod.AuditEvent.ACCOUNT_LINKED,
            user_id=user.id,
            session_id=session.id,
            ip_address=ctx.ip_address,
            provider=oauth_provider.value,
        )

        response = RedirectResponse(url=_build_settings_redirect(), status_code=302)
        _delete_state_cookie(response)
        return response

    async def _on_error(exc: Exception) -> RedirectResponse:
        return _settings_callback_error_redirect(exc)

    return await _execute_oauth_callback(
        code=code,
        redirect_uri=redirect_uri,
        oauth_provider=oauth_provider,
        client=client,
        on_success=_on_success,
        on_error=_on_error,
    )


async def _handle_connect_callback(
    code: str,
    redirect_uri: str,
    oauth_provider: auth_mod.OAuthProvider,
    ctx: auth_mod.RequestContext,
    db: AsyncSession,
    client: httpx.AsyncClient,
    request: Request,
) -> RedirectResponse:
    try:
        user, session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        return RedirectResponse(url=_build_error_redirect("not_authenticated"), status_code=302)

    async def _on_success(token: auth_mod.OAuthToken, profile: auth_mod.UserProfile) -> RedirectResponse:
        scopes = token.scope.split(",") if token.scope else auth_mod.GITHUB_PROFILE_SCOPES.split(" ")

        await auth_mod.store_linked_account(
            db=db,
            user_id=user.id,
            provider="github",
            provider_user_id=profile.provider_id,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            scopes=scopes,
            expires_at=None,
        )

        auth_mod.log_audit_event(
            auth_mod.AuditEvent.ACCOUNT_LINKED,
            user_id=user.id,
            session_id=session.id,
            ip_address=ctx.ip_address,
            provider="github",
            metadata={"action": "connect_profile", "scopes": scopes},
        )

        response = RedirectResponse(url=_build_profile_redirect(success=True), status_code=302)
        _delete_state_cookie(response)
        return response

    async def _on_error(exc: Exception) -> RedirectResponse:
        return _profile_connect_callback_error_redirect(exc, user_id=user.id, ctx=ctx)

    return await _execute_oauth_callback(
        code=code,
        redirect_uri=redirect_uri,
        oauth_provider=oauth_provider,
        client=client,
        on_success=_on_success,
        on_error=_on_error,
    )
