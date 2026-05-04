"""LLM provider HTTP interfaces."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMRequest:
    """Standardized request to any LLM provider."""

    prompt: str
    article_text: str
    temperature: float = 0.0
    max_tokens: int = 512


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    label: str | None = None
    labels_json: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    raw_response: dict | None = None
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    error: str | None = None
    success: bool = True


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        """Make one classification call."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider using direct HTTP via httpx."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        self._model = model

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        """Call Gemini API and normalize the response."""
        import httpx

        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self._model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{request.prompt}\n\n---\n\n기사:\n{request.article_text}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)

            if response.status_code == 429:
                return LLMResponse(
                    success=False,
                    error="rate_limit_429",
                    raw_response={"status": 429},
                )
            if response.status_code != 200:
                return LLMResponse(
                    success=False,
                    error=f"http_{response.status_code}",
                    raw_response={"status": response.status_code, "body": response.text[:500]},
                )

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return LLMResponse(success=False, error="no_candidates", raw_response=data)

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            usage = data.get("usageMetadata", {})
            label, confidence, rationale = _parse_classification_response(text)
            return LLMResponse(
                label=label,
                confidence=confidence,
                rationale=rationale,
                raw_response=data,
                prompt_tokens=usage.get("promptTokenCount", 0),
                candidates_tokens=usage.get("candidatesTokenCount", 0),
                success=True,
            )
        except httpx.TimeoutException:
            return LLMResponse(success=False, error="timeout")
        except Exception as exc:
            return LLMResponse(success=False, error=str(exc))


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude API provider skeleton for later steps."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self._model = model

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        return LLMResponse(success=False, error="claude_provider_not_yet_implemented")


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider skeleton for later steps."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def call(self, request: LLMRequest, api_key: str) -> LLMResponse:
        return LLMResponse(success=False, error="openai_provider_not_yet_implemented")


def _parse_classification_response(text: str) -> tuple[str | None, float | None, str | None]:
    """Parse JSON or plain-text LLM output into label, confidence, rationale."""
    text = text.strip()
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            payload = json.loads(text[start:end])
            label = payload.get("label") or payload.get("classification") or payload.get("category")
            confidence = payload.get("confidence")
            rationale = payload.get("rationale") or payload.get("reason") or payload.get("explanation")
            return (
                str(label) if label else None,
                float(confidence) if confidence is not None else None,
                str(rationale) if rationale else None,
            )
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        return lines[0][:100], None, None
    return None, None, None
