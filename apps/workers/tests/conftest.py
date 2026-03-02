"""Shared fixtures and path setup for worker tests"""

import pytest



@pytest.fixture(autouse=True)
def setup_test_environment():
    """Ensure test environment is properly configured."""
    import os

    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault(
        "DATABASE_URL", "postgresql://test:test@localhost:5432/testdb"
    )
    yield
