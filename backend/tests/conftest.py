import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

# Tests use sqlite unless DATABASE_URL is set for integration runs.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+pysqlite:///:memory:",
)

from app.main import app  # noqa: E402
from core.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
