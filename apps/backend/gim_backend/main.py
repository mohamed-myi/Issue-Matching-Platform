import logging
from contextlib import asynccontextmanager

_app = None
_logging_configured = False


def _configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    audit_logger = logging.getLogger("audit")
    audit_handler = logging.StreamHandler()
    audit_handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.handlers = [audit_handler]
    audit_logger.propagate = False

    _logging_configured = True


def create_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from gim_backend.api.dependencies import close_http_client
    from gim_backend.api.routes import (
        auth,
        bookmarks,
        feed,
        internal_recommendations,
        issues,
        profile,
        profile_github,
        profile_onboarding,
        profile_resume,
        public,
        recommendations,
        repositories,
        search,
        taxonomy,
    )
    from gim_backend.core.config import get_settings
    from gim_backend.core.errors import ProfileError, profile_exception_handler
    from gim_backend.core.redis import close_redis
    from gim_backend.middleware.auth import session_cookie_sync_middleware
    from gim_backend.middleware.security_headers import SecurityHeadersMiddleware
    from gim_backend.services.embedding_service import close_embedder

    _configure_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        yield
        await close_http_client()
        await close_redis()
        await close_embedder()

    app = FastAPI(
        title="IssueIndex API",
        description="Issue discovery and developer matching platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_exception_handler(ProfileError, profile_exception_handler)

    # P1 Security: CORS must be explicitly configured in production
    if settings.environment == "production" and not settings.cors_origins:
        raise ValueError("CORS_ORIGINS must be configured in production")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(",") if settings.cors_origins else ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=86400,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.middleware("http")(session_cookie_sync_middleware)

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(search.router, prefix="/search", tags=["search"])
    app.include_router(feed.router, prefix="/feed", tags=["feed"])
    app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
    app.include_router(internal_recommendations.router, prefix="/internal", tags=["internal"])
    app.include_router(profile.router, prefix="/profile", tags=["profile"])
    app.include_router(profile_onboarding.router, prefix="/profile", tags=["profile"])
    app.include_router(profile_github.router, prefix="/profile", tags=["profile"])
    app.include_router(profile_resume.router, prefix="/profile", tags=["profile"])
    app.include_router(bookmarks.router, prefix="/bookmarks", tags=["bookmarks"])
    app.include_router(issues.router, prefix="/issues", tags=["issues"])
    app.include_router(repositories.router, prefix="/repositories", tags=["repositories"])
    app.include_router(public.router, tags=["public"])
    app.include_router(taxonomy.router, prefix="/taxonomy", tags=["taxonomy"])

    return app


def get_app():
    global _app
    if _app is None:
        _app = create_app()
    return _app


def reset_app_for_testing() -> None:
    global _app, _logging_configured
    _app = None
    _logging_configured = False


def __getattr__(name: str):
    if name == "app":
        return get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


app: object

__all__ = ["app", "create_app", "get_app", "reset_app_for_testing"]
