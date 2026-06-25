import pytest

from core.config import get_settings


def test_health_check_returns_ok(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "development"
    assert payload["mock_mode"] == "true"
