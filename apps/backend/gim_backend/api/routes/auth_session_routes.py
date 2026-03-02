from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.api.routes import auth as auth_mod

router = APIRouter()


@router.get("/sessions", response_model=auth_mod.SessionListResponse)
async def get_sessions(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> auth_mod.SessionListResponse:
    """Returns all active sessions for authenticated user"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sessions = await auth_mod.list_sessions(db, user.id, session.id)

    return auth_mod.SessionListResponse(
        sessions=sessions,
        count=len(sessions),
    )


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Revokes a specific session; must belong to authenticated user"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, current_session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        target_session_id = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    target_session = await auth_mod.get_session_by_id(db, target_session_id)

    if target_session is None or target_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    is_current = target_session_id == current_session.id

    await auth_mod.invalidate_session(db, target_session_id)

    auth_mod.log_audit_event(
        auth_mod.AuditEvent.SESSION_REVOKED,
        user_id=user.id,
        session_id=target_session_id,
        ip_address=request.client.host if request.client else None,
        metadata={"was_current": is_current},
    )

    response_data = {"revoked": True, "was_current": is_current}

    if is_current:
        response = JSONResponse(content=response_data)
        auth_mod.clear_session_cookie(response)
        return response

    return response_data


@router.delete("/sessions")
async def revoke_all_sessions(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Revokes all sessions except current"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, current_session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    revoked_count = await auth_mod.invalidate_all_sessions(db, user.id, except_session_id=current_session.id)

    return {"revoked_count": revoked_count}


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> Response:
    """Invalidates current session; always returns success even if session expired"""
    session_id_str = request.cookies.get("session_id")
    session_uuid = None

    if session_id_str:
        try:
            session_uuid = UUID(session_id_str)
            await auth_mod.invalidate_session(db, session_uuid)
        except ValueError:
            pass

    auth_mod.log_audit_event(
        auth_mod.AuditEvent.LOGOUT,
        session_id=session_uuid,
        ip_address=request.client.host if request.client else None,
    )

    response = JSONResponse(content={"logged_out": True})
    auth_mod.clear_session_cookie(response)
    return response


@router.post("/logout/all")
async def logout_all(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> Response:
    """Invalidates all sessions including current"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, current_session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    revoked_count = await auth_mod.invalidate_all_sessions(db, user.id, except_session_id=None)

    auth_mod.log_audit_event(
        auth_mod.AuditEvent.LOGOUT_ALL,
        user_id=user.id,
        session_id=current_session.id,
        ip_address=request.client.host if request.client else None,
        metadata={"revoked_count": revoked_count},
    )

    response = JSONResponse(content={"revoked_count": revoked_count, "logged_out": True})
    auth_mod.clear_session_cookie(response)
    return response


@router.get("/sessions/count")
async def get_sessions_count(
    request: Request,
    db: AsyncSession = Depends(auth_mod.get_db),
) -> dict:
    """Returns count of active sessions for user"""
    ctx = await auth_mod.get_request_context(request)

    try:
        user, _session = await auth_mod.require_authenticated_user_session(request, db, ctx)
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")

    count = await auth_mod.count_sessions(db, user.id)

    return {"count": count}
