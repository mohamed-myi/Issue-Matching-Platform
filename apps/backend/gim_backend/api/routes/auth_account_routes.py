from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.routes import auth as auth_mod

router = APIRouter()


@router.delete("/connect/github")
async def disconnect_github(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """
    Disconnects GitHub from profile (marks linked_account as revoked).
    Does NOT delete historical profile data; marks it as stale for recommendations.
    """
    ctx = await auth_mod.get_request_context(request)

    try:
        user, session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    was_revoked = await auth_mod.mark_revoked(db, user.id, "github")

    if not was_revoked:
        raise HTTPException(status_code=404, detail="No connected GitHub account found")

    auth_mod.log_audit_event(
        auth_mod.AuditEvent.ACCOUNT_LINKED,
        user_id=user.id,
        session_id=session.id,
        ip_address=ctx.ip_address,
        provider="github",
        metadata={"action": "disconnect_profile"},
    )

    return {"disconnected": True, "provider": "github"}


@router.get("/connect/status")
async def get_connect_status(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Returns status of connected accounts for profile features"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, _session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    github_account = await auth_mod.get_active_linked_account(db, user.id, "github")

    return {
        "github": {
            "connected": github_account is not None,
            "username": github_account.provider_user_id if github_account else None,
            "connected_at": github_account.created_at.isoformat() if github_account else None,
        }
    }


@router.get("/me")
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Returns current user info for navbar and settings pages"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, _session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "id": str(user.id),
        "email": user.email,
        "github_username": user.github_username,
        "google_id": user.google_id,
        "created_at": user.created_at.isoformat(),
        "created_via": user.created_via,
    }


@router.get("/linked-accounts")
async def get_linked_accounts_list(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Lists all connected OAuth providers for settings page"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, _session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    accounts = await auth_mod.list_linked_accounts(db, user.id)

    return {
        "accounts": [
            {
                "provider": account.provider,
                "connected": True,
                "username": account.provider_user_id,
                "connected_at": account.created_at.isoformat(),
                "scopes": account.scopes or [],
            }
            for account in accounts
        ]
    }


@router.delete("/link/{provider}")
async def unlink_provider(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Unlinks an OAuth provider from the user's account.

    Cannot unlink the provider the user originally signed up with (created_via).
    """
    try:
        oauth_provider = auth_mod.OAuthProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider")

    ctx = await auth_mod.get_request_context(request)

    try:
        user, session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if user.created_via == provider:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot unlink your primary login method ({provider}). "
            "You must always have at least one way to sign in.",
        )

    if oauth_provider == auth_mod.OAuthProvider.GITHUB:
        if user.github_node_id is None and user.github_username is None:
            raise HTTPException(status_code=404, detail="GitHub is not linked to this account")
        user.github_node_id = None
        user.github_username = None
    elif oauth_provider == auth_mod.OAuthProvider.GOOGLE:
        if user.google_id is None:
            raise HTTPException(status_code=404, detail="Google is not linked to this account")
        user.google_id = None

    await auth_mod.mark_revoked(db, user.id, provider)
    await db.commit()

    auth_mod.log_audit_event(
        auth_mod.AuditEvent.ACCOUNT_LINKED,
        user_id=user.id,
        session_id=session.id,
        ip_address=ctx.ip_address,
        provider=provider,
        metadata={"action": "unlinked"},
    )

    return {"unlinked": True, "provider": provider}


@router.delete("/account")
async def delete_account(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> Response:
    """GDPR-compliant full account deletion with cascade"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user.id

    try:
        result = await auth_mod.delete_user_cascade(db, user_id)
    except auth_mod.UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    auth_mod.log_audit_event(
        auth_mod.AuditEvent.LOGOUT_ALL,
        user_id=user_id,
        session_id=session.id,
        ip_address=ctx.ip_address,
        metadata={
            "action": "account_deleted",
            "tables_affected": result.tables_affected,
            "total_rows": result.total_rows,
        },
    )

    response = JSONResponse(
        content={
            "deleted": True,
            "message": "Account and all data permanently deleted",
        }
    )
    auth_mod.clear_session_cookie(response)
    return response
