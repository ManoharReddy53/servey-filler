from typing import Any

from app.models.domain import QuestionType, SurveyQuestion, ValidationResult


def validate_answer(question: SurveyQuestion, value: Any) -> ValidationResult:
    if value is None or value == "":
        return ValidationResult(question_id=question.id, valid=False, reason="Answer is empty.")
    if question.options and value not in question.options:
        return ValidationResult(
            question_id=question.id,
            valid=False,
            reason="Answer is not one of the available options.",
        )
    if question.question_type in {QuestionType.ELIGIBILITY, QuestionType.ATTESTATION}:
        return ValidationResult(
            question_id=question.id,
            valid=False,
            reason="This question requires a human decision.",
        )
    return ValidationResult(
        question_id=question.id,
        valid=True,
        reason="Answer matches the question constraints.",
        normalized_value=value,
    )
