from app.models.domain import QuestionType
from app.services.classifier import classify_question


def test_classifies_safety_sensitive_questions_first() -> None:
    assert classify_question("Do you certify that you are eligible?") == QuestionType.ATTESTATION
    assert classify_question("Are you eligible for this study?") == QuestionType.ELIGIBILITY


def test_classifies_common_question_types() -> None:
    assert classify_question("What is your age?") == QuestionType.FACTUAL
    assert classify_question("Which product do you prefer?") == QuestionType.PREFERENCE
    assert classify_question("How satisfied are you?") == QuestionType.OPINION
