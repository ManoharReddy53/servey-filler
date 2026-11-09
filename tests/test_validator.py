from app.models.domain import QuestionType, SurveyQuestion
from app.services.validator import validate_answer


def test_rejects_answer_outside_options() -> None:
    question = SurveyQuestion(id="q1", text="Choice", options=["A"])
    result = validate_answer(question, "B")
    assert not result.valid


def test_rejects_attestation() -> None:
    question = SurveyQuestion(id="q1", text="Attest", question_type=QuestionType.ATTESTATION)
    result = validate_answer(question, "yes")
    assert not result.valid
