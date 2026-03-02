import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env files before setting defaults. Tests force safe defaults for
# sensitive connection settings unless an explicit opt-in is provided.
project_root = Path(__file__).resolve().parent.parent.parent.parent
env_local_path = project_root / ".env.local"
try:
    load_dotenv(env_local_path)
except PermissionError:
    # CI may deny access to local secret files.
    # Tests fall back to defaults below.
    pass
load_dotenv(project_root / ".env")

os.environ.setdefault("FINGERPRINT_SECRET", "test_fingerprint_secret_for_testing_only_32chars")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_for_testing")
os.environ.setdefault("GITHUB_CLIENT_ID", "test_github_client_id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test_github_client_secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test_google_client_id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test_google_client_secret")
os.environ.setdefault("ENVIRONMENT", "development")

# Default test runs must never require or accidentally use a real/prod DB.
# Opt-in flags are handled by dedicated integration tests only.
if os.getenv("RUN_REAL_DB_INTEGRATION") != "1" and os.getenv("RUN_PROD_DB_TESTS") != "1":
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/testdb"
else:
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

os.environ["REDIS_URL"] = ""  # Force in-memory rate limiting for tests

# Order matters: import base models first, then those with relationships.
from gim_database.models.identity import LinkedAccount, Session, User  # noqa: E402, F401
from gim_database.models.persistence import BookmarkedIssue, PersonalNote  # noqa: E402, F401
from gim_database.models.profiles import UserProfile  # noqa: E402, F401


@pytest.fixture(autouse=True)
async def reset_global_state():
    """
    Ensure global singletons are reset between tests to prevent:
    1. 'Event loop is closed' errors (from stale Redis clients)
    2. State leakage between tests
    """
    from gim_backend.core.redis import close_redis, reset_redis_for_testing
    from gim_backend.middleware.rate_limit import reset_rate_limiter, reset_rate_limiter_instance

    # Clean before
    reset_redis_for_testing()
    reset_rate_limiter_instance()

    yield

    # Clean after
    await close_redis()
    reset_redis_for_testing()
    reset_rate_limiter()
    reset_rate_limiter_instance()


@pytest.fixture
def sample_q_components():
    """Shared ingestion test fixture for representative quality gate components."""
    from gim_backend.ingestion.quality_gate import QScoreComponents

    return QScoreComponents(
        has_code=True,
        has_headers=True,
        tech_weight=0.5,
        is_junk=False,
    )
