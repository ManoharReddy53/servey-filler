import asyncio

import pytest

from app.core.config import Settings
from app.models.domain import StructuredAnswer
from app.services.llm import GeminiLLMClient, LLMError, build_llm_client


class FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def get(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response

    async def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: object) -> None:
        self.aio = type("Async", (), {"models": FakeModels(response)})()


class GoodResponse:
    text = '{"answer":"blue","confidence":0.8,"rationale":"Synthetic test.","requires_human_review":true}'


@pytest.mark.asyncio
async def test_gemini_returns_structured_answer_without_real_credentials() -> None:
    client = GeminiLLMClient("synthetic-key", "gemini-test", client=FakeClient(GoodResponse()))
    await client.verify_model()
    answer = await client.suggest("Synthetic question", ["blue", "green"])
    assert answer == StructuredAnswer(
        answer="blue", confidence=0.8, rationale="Synthetic test.", requires_human_review=True
    )


@pytest.mark.asyncio
async def test_gemini_rejects_malformed_response() -> None:
    class BadResponse:
        text = "not json"

    client = GeminiLLMClient("synthetic-key", "gemini-test", client=FakeClient(BadResponse()))
    with pytest.raises(LLMError, match="malformed"):
        await client.suggest("Synthetic question", [])


@pytest.mark.asyncio
async def test_gemini_timeout_is_sanitized() -> None:
    class SlowModels(FakeModels):
        async def generate_content(self, **kwargs: object) -> object:
            await asyncio.sleep(0.02)
            return self.response

    fake = FakeClient(GoodResponse())
    fake.aio.models = SlowModels(GoodResponse())
    client = GeminiLLMClient("synthetic-key", "gemini-test", timeout_seconds=0.001, client=fake)
    with pytest.raises(LLMError, match="timed out"):
        await client.suggest("Synthetic question", [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("invalid API key: secret-value"), "authentication failed"),
        (RuntimeError("quota exceeded for project"), "quota or rate limit"),
    ],
)
async def test_provider_errors_are_sanitized(error: Exception, expected: str) -> None:
    class ErrorModels(FakeModels):
        async def generate_content(self, **kwargs: object) -> object:
            raise error

    fake = FakeClient(GoodResponse())
    fake.aio.models = ErrorModels(GoodResponse())
    client = GeminiLLMClient("synthetic-key", "gemini-test", client=fake)
    with pytest.raises(LLMError, match=expected) as raised:
        await client.suggest("Synthetic question", [])
    assert "secret-value" not in str(raised.value)


def test_provider_selection_defaults_to_disabled_and_supports_mock() -> None:
    assert build_llm_client(Settings(llm_provider="disabled")).__class__.__name__ == "DisabledLLMClient"
    assert build_llm_client(Settings(llm_provider="mock")).__class__.__name__ == "MockLLMClient"
