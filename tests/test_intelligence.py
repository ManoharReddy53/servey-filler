import pytest

from app.models.domain import QuestionType, StructuredAnswer, SurveyQuestion
from app.services.classifier import classify_question
from app.services.llm import DisabledLLMClient, MockLLMClient
from app.services.validator import validate_answer


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What is your age?", QuestionType.FACTUAL),
        ("Which mobile operating system do you use?", QuestionType.PREFERENCE),
        ("How often do you purchase groceries online?", QuestionType.PREFERENCE),
        ("What is your opinion about electric vehicles?", QuestionType.OPINION),
    ],
)
def test_sample_question_classification(text: str, expected: QuestionType) -> None:
    assert classify_question(text) == expected


@pytest.mark.asyncio
async def test_disabled_llm_returns_safe_structured_response() -> None:
    response = await DisabledLLMClient().suggest("What is your age?", ["30", "40"])
    assert response.answer is None
    assert response.requires_human_review


@pytest.mark.asyncio
async def test_mock_llm_returns_structured_response() -> None:
    expected = StructuredAnswer(
        answer="Android",
        confidence=0.9,
        rationale="Configured mock response.",
        requires_human_review=True,
    )
    client = MockLLMClient({"Which mobile operating system do you use?": expected})
    assert await client.suggest("Which mobile operating system do you use?", ["Android"]) == expected


def test_multiple_choice_validation_accepts_and_rejects_options() -> None:
    question = SurveyQuestion(
        id="os",
        text="Which mobile operating system do you use?",
        options=["Android", "iOS"],
    )
    assert validate_answer(question, "Android").valid
    rejected = validate_answer(question, "Windows Phone")
    assert not rejected.valid
    assert "available options" in rejected.reason
