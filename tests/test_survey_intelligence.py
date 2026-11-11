import pytest

from app.models.domain import (
    IntelligenceResult,
    ProfileFact,
    QuestionType,
    StopReason,
    StructuredAnswer,
    SurveyQuestion,
    SurveySnapshot,
)
from app.services.intelligence import IntelligenceError, SurveyIntelligenceService
from app.services.llm import GeminiLLMClient, LLMError
from app.services.profile import ProfileFacts


class RecordingLLM:
    def __init__(self, answer: StructuredAnswer) -> None:
        self.answer = answer
        self.calls: list[tuple[object, ...]] = []

    async def suggest(self, *args: object, **kwargs: object) -> StructuredAnswer:
        self.calls.append((*args, kwargs))
        return self.answer


@pytest.mark.asyncio
async def test_generates_reviewable_suggestions_with_verified_facts() -> None:
    llm = RecordingLLM(
        StructuredAnswer(answer="30", confidence=0.9, rationale="Matches verified fact.")
    )
    service = SurveyIntelligenceService(
        llm,
        ProfileFacts([ProfileFact(key="age", value="30", verified=True, source="user")]),
    )
    result = await service.suggest(
        SurveySnapshot(
            questions=[
                SurveyQuestion(
                    id="age",
                    text="What is your age?",
                    question_type=QuestionType.FACTUAL,
                    options=["30", "40"],
                )
            ]
        )
    )
    assert result == IntelligenceResult(
        suggestions=[{"question_id": "age", "suggestion": llm.answer}]
    )
    assert llm.calls[0][3] == [
        ProfileFact(key="age", value="30", verified=True, source="user")
    ]


@pytest.mark.asyncio
async def test_preference_and_opinion_answers_are_user_input_requests() -> None:
    llm = RecordingLLM(
        StructuredAnswer(answer=None, rationale="User input is required.")
    )
    service = SurveyIntelligenceService(llm, ProfileFacts())
    result = await service.suggest(
        SurveySnapshot(
            questions=[
                SurveyQuestion(
                    id="choice",
                    text="Which do you prefer?",
                    question_type=QuestionType.PREFERENCE,
                    options=["A", "B"],
                )
            ]
        )
    )
    assert result.suggestions[0].suggestion.answer is None
    assert llm.calls[0][3] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question_type", "answer"),
    [
        (QuestionType.OPINION, "Electric vehicles can reduce pollution and transport costs."),
        (QuestionType.PREFERENCE, "Battery life"),
    ],
)
async def test_generates_direct_ordinary_answers_without_review(
    question_type: QuestionType, answer: str
) -> None:
    llm = RecordingLLM(
        StructuredAnswer(answer=answer, rationale="Concise generated response.", requires_human_review=False)
    )
    result = await SurveyIntelligenceService(llm, ProfileFacts()).suggest(
        SurveySnapshot(
            questions=[
                SurveyQuestion(
                    id="q",
                    text="Ordinary survey question",
                    question_type=question_type,
                    options=["Battery life"] if question_type == QuestionType.PREFERENCE else [],
                )
            ]
        )
    )
    assert result.suggestions[0].auto_fill
    assert not result.suggestions[0].suggestion.requires_human_review


@pytest.mark.asyncio
async def test_neutral_is_a_valid_multiple_choice_answer() -> None:
    answer = StructuredAnswer(answer="Neutral", rationale="Balanced selection.", requires_human_review=False)
    result = await SurveyIntelligenceService(RecordingLLM(answer), ProfileFacts()).suggest(
        SurveySnapshot(
            questions=[
                SurveyQuestion(
                    id="q", text="How do you feel?", question_type=QuestionType.OPINION,
                    options=["Positive", "Neutral", "Negative"],
                )
            ]
        )
    )
    assert result.suggestions[0].suggestion.answer == "Neutral"
    assert result.suggestions[0].auto_fill


@pytest.mark.asyncio
async def test_missing_personal_fact_stays_reviewable() -> None:
    answer = StructuredAnswer(answer=None, rationale="Verified age is missing.")
    result = await SurveyIntelligenceService(RecordingLLM(answer), ProfileFacts()).suggest(
        SurveySnapshot(
            questions=[
                SurveyQuestion(id="age", text="What is your age?", question_type=QuestionType.FACTUAL)
            ]
        )
    )
    assert result.suggestions[0].suggestion.answer is None
    assert not result.suggestions[0].auto_fill


@pytest.mark.asyncio
async def test_rejects_fabricated_personal_experience() -> None:
    llm = RecordingLLM(
        StructuredAnswer(
            answer="I use online shopping every week.",
            rationale="Fabricated experience.",
            requires_human_review=False,
        )
    )
    service = SurveyIntelligenceService(llm, ProfileFacts())
    with pytest.raises(IntelligenceError, match="verified fact"):
        await service.suggest(
            SurveySnapshot(
                questions=[
                    SurveyQuestion(
                        id="usage",
                        text="Do you use online shopping?",
                        question_type=QuestionType.PREFERENCE,
                    )
                ]
            )
        )


@pytest.mark.asyncio
async def test_rejects_non_reviewable_and_invalid_option_answers() -> None:
    question = SurveyQuestion(id="q", text="Choice", options=["A"])
    service = SurveyIntelligenceService(
        RecordingLLM(StructuredAnswer(answer="B", rationale="bad")),
        ProfileFacts(),
    )
    with pytest.raises(IntelligenceError, match="available options"):
        await service.suggest(SurveySnapshot(questions=[question]))

    service.llm = RecordingLLM(
        StructuredAnswer(answer="A", rationale="unsafe", requires_human_review=False)
    )
    with pytest.raises(IntelligenceError, match="human review"):
        await service.suggest(SurveySnapshot(questions=[question]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [StopReason.CAPTCHA, StopReason.ANTI_BOT, StopReason.ELIGIBILITY_ATTESTATION],
)
async def test_stop_reasons_prevent_llm_processing(reason: StopReason) -> None:
    llm = RecordingLLM(StructuredAnswer(rationale="unused"))
    result = await SurveyIntelligenceService(llm, ProfileFacts()).suggest(
        SurveySnapshot(stop_reason=reason)
    )
    assert result.stop_reason == reason
    assert llm.calls == []


def test_gemini_prompt_contains_context() -> None:
    class FakeModels:
        async def generate_content(self, **kwargs: object) -> object:
            self.kwargs = kwargs
            return type(
                "Response",
                (),
                {"text": '{"answer":null,"confidence":0,"rationale":"User input required.","requires_human_review":true}'},
            )()

    models = FakeModels()
    client = GeminiLLMClient(
        "key",
        "model",
        client=type("Client", (), {"aio": type("Aio", (), {"models": models})()})(),
    )
    import asyncio

    asyncio.run(
        client.suggest(
            "Which color?",
            ["Blue", "Green"],
            QuestionType.PREFERENCE,
            [ProfileFact(key="age", value="30", verified=True, source="user")],
        )
    )
    prompt = models.kwargs["contents"]
    assert "Question type: preference" in prompt
    assert '"Blue"' in prompt
    assert '"key": "age"' in prompt
    assert '"value": "30"' in prompt
