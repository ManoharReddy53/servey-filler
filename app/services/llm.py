import asyncio
import json
from typing import Protocol

from pydantic import ValidationError

from app.core.config import Settings
from app.models.domain import StructuredAnswer


class LLMError(RuntimeError):
    """Provider-neutral error that does not expose credentials or response data."""


class LLMClient(Protocol):
    async def suggest(self, question: str, options: list[str]) -> StructuredAnswer:
        """Return a reviewable suggestion; callers remain responsible for safety."""


class DisabledLLMClient:
    async def suggest(self, question: str, options: list[str]) -> StructuredAnswer:
        return StructuredAnswer(
            rationale="LLM credentials are not configured; no answer was generated.",
        )


class MockLLMClient:
    """Deterministic offline client for tests and local development."""

    def __init__(self, responses: dict[str, StructuredAnswer] | None = None) -> None:
        self.responses = responses or {}

    async def suggest(self, question: str, options: list[str]) -> StructuredAnswer:
        return self.responses.get(
            question,
            StructuredAnswer(rationale="No mock response configured for this question."),
        )


class GeminiLLMClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30,
        client: object | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("Gemini authentication is not configured.")
        if not model:
            raise LLMError("Gemini model is not configured.")
        self.model = model
        self.timeout_seconds = timeout_seconds
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self.client = client

    async def verify_model(self) -> None:
        try:
            await asyncio.wait_for(
                self.client.aio.models.get(model=self.model),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise LLMError("Gemini model verification timed out.") from exc
        except Exception as exc:
            raise self._safe_provider_error(exc, "Gemini model verification failed.") from exc

    async def suggest(self, question: str, options: list[str]) -> StructuredAnswer:
        prompt = (
            "Return JSON matching the requested schema. Do not invent personal facts "
            "or experiences. If the answer cannot be grounded, use null and require "
            "human review.\n"
            f"Question: {question}\n"
            f"Available options: {json.dumps(options)}"
        )
        try:
            from google.genai import types

            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=StructuredAnswer,
                    ),
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise LLMError("Gemini request timed out.") from exc
        except Exception as exc:
            raise self._safe_provider_error(exc, "Gemini request failed.") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise LLMError("Gemini returned an empty response.")
        try:
            return StructuredAnswer.model_validate_json(text)
        except (ValidationError, ValueError, TypeError) as exc:
            raise LLMError("Gemini returned malformed structured JSON.") from exc

    @staticmethod
    def _safe_provider_error(error: Exception, fallback: str) -> LLMError:
        name = type(error).__name__.casefold()
        message = str(error).casefold()
        if "auth" in name or "permission" in name or "unauth" in message or "api key" in message:
            return LLMError("Gemini authentication failed.")
        if "quota" in name or "resourceexhaust" in name or "rate" in message or "quota" in message:
            return LLMError("Gemini quota or rate limit was reached.")
        return LLMError(fallback)


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.casefold()
    if provider == "mock":
        return MockLLMClient()
    if provider == "disabled":
        return DisabledLLMClient()
    if provider == "gemini":
        return GeminiLLMClient(
            api_key=settings.gemini_api_key or settings.llm_api_key or "",
            model=settings.gemini_model or settings.llm_model or "",
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise LLMError("Unsupported LLM provider.")
