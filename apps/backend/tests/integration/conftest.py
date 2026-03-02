import os
from pathlib import Path
from uuid import uuid4

import pytest

_DOCKER_INTEGRATION_FILES = {
    "ingestion/test_infrastructure.py",
    "ingestion/test_persistence_upsert.py",
    "search/test_search_flow.py",
}

_MODEL_INTEGRATION_FILES = {
    "ingestion/test_embedding_stream.py",
}

_LIVE_API_INTEGRATION_FILES = {
    "ingestion/test_github_client_live.py",
}

_REAL_DB_INTEGRATION_FILES = {
    "ingestion/test_janitor_prune.py",
}


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Reset rate limiter state between integration tests to avoid 429 leakage."""
    from gim_backend.middleware.rate_limit import reset_rate_limiter, reset_rate_limiter_instance

    reset_rate_limiter()
    reset_rate_limiter_instance()
    yield
    reset_rate_limiter()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from gim_backend.main import app

    return TestClient(app)


@pytest.fixture
def mock_user_email() -> str:
    return "test@example.com"


@pytest.fixture
def mock_user(mock_user_email: str):
    from unittest.mock import MagicMock

    user = MagicMock()
    user.id = uuid4()
    user.email = mock_user_email
    return user


@pytest.fixture
def mock_session(mock_user):
    from unittest.mock import MagicMock

    session = MagicMock()
    session.id = uuid4()
    session.user_id = mock_user.id
    return session


@pytest.fixture
def authenticated_client(client, mock_user, mock_session):
    from gim_backend.main import app
    from gim_backend.middleware.auth import require_auth

    def _mock_require_auth():
        return (mock_user, mock_session)

    app.dependency_overrides[require_auth] = _mock_require_auth
    yield client
    app.dependency_overrides.clear()


def _enabled(env_name: str) -> bool:
    return os.getenv(env_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _classify_integration_path(path_str: str) -> str | None:
    integration_root = Path(__file__).resolve().parent
    try:
        rel = Path(path_str).resolve().relative_to(integration_root).as_posix()
    except Exception:
        return None

    if rel.startswith("prod/"):
        return "prod_db"
    if rel in _DOCKER_INTEGRATION_FILES:
        return "docker"
    if rel in _MODEL_INTEGRATION_FILES:
        return "model"
    if rel in _LIVE_API_INTEGRATION_FILES:
        return "live_api"
    if rel in _REAL_DB_INTEGRATION_FILES:
        return "real_db"
    return None


def pytest_ignore_collect(collection_path, config):  # noqa: ARG001
    kind = _classify_integration_path(str(collection_path))
    if kind is None:
        return False

    if kind == "prod_db":
        return not _enabled("RUN_PROD_DB_TESTS")
    if kind == "docker":
        return not _enabled("RUN_DOCKER_INTEGRATION")
    if kind == "model":
        return not _enabled("RUN_MODEL_INTEGRATION")
    if kind == "live_api":
        return not _enabled("RUN_LIVE_API_INTEGRATION")
    if kind == "real_db":
        return not _enabled("RUN_REAL_DB_INTEGRATION")
    return False


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    run_docker = _enabled("RUN_DOCKER_INTEGRATION")
    run_model = _enabled("RUN_MODEL_INTEGRATION")
    run_live_api = _enabled("RUN_LIVE_API_INTEGRATION")
    run_real_db = _enabled("RUN_REAL_DB_INTEGRATION")
    run_prod_db = _enabled("RUN_PROD_DB_TESTS")

    skip_docker = pytest.mark.skip(reason="Docker integration tests are opt-in; set RUN_DOCKER_INTEGRATION=1")
    skip_model = pytest.mark.skip(
        reason=("Model integration tests are opt-in (may download/load large models); set RUN_MODEL_INTEGRATION=1")
    )
    skip_live_api = pytest.mark.skip(reason="Live API integration tests are opt-in; set RUN_LIVE_API_INTEGRATION=1")
    skip_real_db = pytest.mark.skip(reason="Real DB integration tests are opt-in; set RUN_REAL_DB_INTEGRATION=1")
    skip_prod_db = pytest.mark.skip(
        reason="Production DB tests are opt-in and excluded by default; set RUN_PROD_DB_TESTS=1"
    )

    for item in items:
        kind = _classify_integration_path(str(item.fspath))
        if kind == "prod_db":
            item.add_marker(pytest.mark.prod_db)
            if not run_prod_db:
                item.add_marker(skip_prod_db)
            continue

        if kind == "docker":
            item.add_marker(pytest.mark.docker)
            if not run_docker:
                item.add_marker(skip_docker)
            continue

        if kind == "model":
            item.add_marker(pytest.mark.external)
            item.add_marker(pytest.mark.model)
            if not run_model:
                item.add_marker(skip_model)
            continue

        if kind == "live_api":
            item.add_marker(pytest.mark.external)
            item.add_marker(pytest.mark.live_api)
            if not run_live_api:
                item.add_marker(skip_live_api)
            continue

        if kind == "real_db":
            item.add_marker(pytest.mark.external)
            item.add_marker(pytest.mark.real_db)
            if not run_real_db:
                item.add_marker(skip_real_db)
