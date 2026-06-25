import os

import pytest

from core.config import Settings
from core.llm import MockLLMClient, get_llm_client


def test_mock_llm_client_returns_json(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        GROQ_API_KEY=None,
    )
    client = get_llm_client(settings)
    assert isinstance(client, MockLLMClient)

    result = client.complete_json('Return {"status":"ok"}', system="You are a test assistant.")
    assert result["mock"] is True
    assert result["result"]["status"] == "ok"


def test_groq_smoke_test():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set")

    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        GROQ_API_KEY=api_key,
    )
    client = get_llm_client(settings)
    result = client.complete_json(
        'Respond with JSON: {"status":"ok"}',
        system="Return valid JSON only.",
    )
    assert isinstance(result, dict)
    assert "status" in result
