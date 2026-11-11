import pytest

from app.models.domain import (
    AnswerCandidate,
    QuestionType,
    StructuredAnswer,
    SurveyQuestion,
    SurveySuggestion,
    StopReason,
)
from app.services.profile import ProfileFacts
from app.services.workflow import SurveyWorkflow


class MockBrowser:
    def __init__(self, questions: list[SurveyQuestion]) -> None:
        self.questions = questions
        self.filled: list[tuple[str, str]] = []

    async def extract_visible_questions(self) -> list[SurveyQuestion]:
        return self.questions

    async def fill(self, question_id: str, value: str) -> None:
        self.filled.append((question_id, value))

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_fills_only_verified_profile_facts() -> None:
    browser = MockBrowser([SurveyQuestion(id="age", text="What is your age?", options=["30"])])
    workflow = SurveyWorkflow(browser, ProfileFacts())
    await workflow.apply(
        [AnswerCandidate(question_id="age", value="30", source="verified_profile", permitted=True)]
    )
    assert browser.filled == [("age", "30")]


@pytest.mark.asyncio
async def test_stops_before_attestation() -> None:
    browser = MockBrowser(
        [SurveyQuestion(id="agree", text="Do you certify this?", question_type=QuestionType.ATTESTATION)]
    )
    snapshot = await SurveyWorkflow(browser, ProfileFacts()).inspect()
    assert snapshot.stop_reason == StopReason.ELIGIBILITY_ATTESTATION


@pytest.mark.asyncio
async def test_does_not_fill_when_attestation_is_present() -> None:
    browser = MockBrowser(
        [
            SurveyQuestion(id="age", text="What is your age?", options=["30"]),
            SurveyQuestion(id="agree", text="Do you certify this?", question_type=QuestionType.ATTESTATION),
        ]
    )
    workflow = SurveyWorkflow(browser, ProfileFacts())
    await workflow.apply(
        [AnswerCandidate(question_id="age", value="30", source="verified_profile", permitted=True)]
    )
    assert browser.filled == []


@pytest.mark.asyncio
async def test_fills_generated_opinion_and_records_answer() -> None:
    browser = MockBrowser(
        [SurveyQuestion(id="opinion", text="What do you think?", question_type=QuestionType.OPINION)]
    )
    workflow = SurveyWorkflow(browser, ProfileFacts())
    decisions = await workflow.apply_suggestions(
        [
            SurveySuggestion(
                question_id="opinion",
                suggestion=StructuredAnswer(
                    answer="It is convenient.",
                    rationale="Ordinary opinion.",
                    requires_human_review=False,
                ),
                auto_fill=True,
            )
        ]
    )
    assert browser.filled == [("opinion", "It is convenient.")]
    assert decisions[-1].answer == "It is convenient."
