"""Shared fixtures for backend unit tests."""

import os
from collections.abc import Mapping
from contextlib import contextmanager
from unittest.mock import patch

import pytest


@pytest.fixture
def settings_env_override():
    """Temporarily patch settings env vars and clear the cached settings singleton."""

    @contextmanager
    def _override(env_overrides: Mapping[str, str]):
        with patch.dict(os.environ, dict(env_overrides), clear=False):
            from gim_backend.core.config import get_settings

            get_settings.cache_clear()
            try:
                yield
            finally:
                get_settings.cache_clear()

    return _override

