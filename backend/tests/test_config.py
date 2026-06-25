import pytest
from pydantic import ValidationError

from core.config import Settings, get_settings


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    get_settings.cache_clear()

    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql")
    assert settings.mock_mode is True


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_origins_parsed_from_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,https://example.vercel.app")
    get_settings.cache_clear()

    settings = Settings(_env_file=None)
    assert settings.cors_origins == [
        "http://localhost:5173",
        "https://example.vercel.app",
    ]


def test_render_database_url_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@dpg-abc.oregon-postgres.render.com/spotify_discovery",
    )
    get_settings.cache_clear()

    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in settings.database_url
