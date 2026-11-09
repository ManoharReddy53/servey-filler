import re

from app.models.domain import QuestionType, SurveyQuestion


_PATTERNS: dict[QuestionType, tuple[str, ...]] = {
    QuestionType.ATTESTATION: ("attest", "certify", "declare", "agree that", "confirm that"),
    QuestionType.ELIGIBILITY: ("eligible", "qualify", "are you currently", "do you have a child"),
    QuestionType.FACTUAL: ("what is your age", "date of birth", "postcode", "zip code", "country"),
    QuestionType.PREFERENCE: (
        "prefer",
        "favorite",
        "favourite",
        "which would you choose",
        "which mobile operating system",
        "operating system do you use",
        "how often",
        "purchase groceries",
    ),
    QuestionType.OPINION: ("what do you think", "opinion", "rate", "satisfied", "how likely"),
}


def classify_question(text: str) -> QuestionType:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    for question_type in (
        QuestionType.ATTESTATION,
        QuestionType.ELIGIBILITY,
        QuestionType.FACTUAL,
        QuestionType.PREFERENCE,
        QuestionType.OPINION,
    ):
        if any(pattern in normalized for pattern in _PATTERNS[question_type]):
            return question_type
    return QuestionType.UNKNOWN


def classify_questions(questions: list[SurveyQuestion]) -> list[SurveyQuestion]:
    return [
        question.model_copy(update={"question_type": classify_question(question.text)})
        for question in questions
    ]
