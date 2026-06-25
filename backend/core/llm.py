import json
from abc import ABC, abstractmethod
from typing import Any, cast

from groq import Groq

from core.config import Settings, get_settings


class LLMClient(ABC):
    @abstractmethod
    def complete_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    def complete_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        del max_tokens
        return {
            "mock": True,
            "model": model or "mock",
            "prompt_preview": prompt[:120],
            "result": {"status": "ok"},
        }


class GroqLLMClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for GroqLLMClient")
        self._settings = settings
        self._client = Groq(api_key=settings.groq_api_key)

    def complete_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(  # type: ignore[call-overload]
            model=model or self._settings.groq_model_small,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or "{}"
        return cast(dict[str, Any], json.loads(content))


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.mock_mode:
        return MockLLMClient()
    return GroqLLMClient(settings)
