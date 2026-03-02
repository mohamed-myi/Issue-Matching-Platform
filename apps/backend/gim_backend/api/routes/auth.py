"""Auth router aggregator and stable patch surface for auth route tests."""
from fastapi import APIRouter

from gim_backend.api.dependencies import get_db, get_http_client
from gim_backend.core.audit import AuditEvent, log_audit_event
from gim_backend.core.config import get_settings
from gim_backend.core.cookies import (
    _cookie_domain_or_none,
    clear_session_cookie,
    create_login_flow_cookie,
    create_session_cookie,
)
from gim_backend.core.oauth import (
    GITHUB_PROFILE_SCOPES,
    EmailNotVerifiedError,
    InvalidCodeError,
    NoEmailError,
    OAuthError,
    OAuthProvider,
    OAuthStateError,
    OAuthToken,
    UserProfile,
    exchange_code_for_token,
    fetch_user_profile,
    get_authorization_url,
    get_profile_authorization_url,
)
from gim_backend.middleware.auth import (
    get_current_session,
    optional_fingerprint,
    require_authenticated_user_session,
)
from gim_backend.middleware.context import RequestContext, get_request_context
from gim_backend.middleware.rate_limit import check_auth_rate_limit
from gim_backend.services.linked_account_service import (
    get_active_linked_account,
    list_linked_accounts,
    mark_revoked,
    store_linked_account,
)
from gim_backend.services.session_service import (
    ExistingAccountError,
    ProviderConflictError,
    SessionListResponse,
    UserNotFoundError,
    count_sessions,
    create_session,
    delete_user_cascade,
    get_session_by_id,
    invalidate_all_sessions,
    invalidate_session,
    link_provider,
    list_sessions,
    upsert_user,
)

# Imported for type annotations in route modules and for test patch compatibility.
__all__ = [
    "AuditEvent",
    "EmailNotVerifiedError",
    "ExistingAccountError",
    "GITHUB_PROFILE_SCOPES",
    "InvalidCodeError",
    "NoEmailError",
    "OAuthError",
    "OAuthProvider",
    "OAuthStateError",
    "OAuthToken",
    "ProviderConflictError",
    "RequestContext",
    "SessionListResponse",
    "STATE_COOKIE_MAX_AGE",
    "STATE_COOKIE_NAME",
    "UserNotFoundError",
    "UserProfile",
    "_cookie_domain_or_none",
    "check_auth_rate_limit",
    "clear_session_cookie",
    "count_sessions",
    "create_login_flow_cookie",
    "create_session",
    "create_session_cookie",
    "delete_user_cascade",
    "exchange_code_for_token",
    "fetch_user_profile",
    "get_active_linked_account",
    "get_authorization_url",
    "get_current_session",
    "get_db",
    "get_http_client",
    "get_profile_authorization_url",
    "get_request_context",
    "get_session_by_id",
    "get_settings",
    "invalidate_all_sessions",
    "invalidate_session",
    "link_provider",
    "list_linked_accounts",
    "list_sessions",
    "log_audit_event",
    "mark_revoked",
    "optional_fingerprint",
    "require_authenticated_user_session",
    "router",
    "store_linked_account",
    "upsert_user",
]

router = APIRouter()

from gim_backend.api.routes.auth_account_routes import router as _account_router  # noqa: E402
from gim_backend.api.routes.auth_oauth_routes import (  # noqa: E402
    STATE_COOKIE_MAX_AGE,
    STATE_COOKIE_NAME,
)
from gim_backend.api.routes.auth_oauth_routes import (  # noqa: E402
    router as _oauth_router,
)
from gim_backend.api.routes.auth_session_routes import router as _session_router  # noqa: E402

router.include_router(_oauth_router)
router.include_router(_session_router)
router.include_router(_account_router)
