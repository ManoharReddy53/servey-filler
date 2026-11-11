from app.models.domain import (
    IntelligenceResult,
    QuestionType,
    StopReason,
    StructuredAnswer,
    SurveyQuestion,
    SurveySnapshot,
    SurveySuggestion,
)
from app.services.llm import LLMClient
from app.services.profile import ProfileFacts
from app.services.validator import validate_answer


class IntelligenceError(RuntimeError):
    """Raised when an answer cannot be safely used as a survey suggestion."""


class SurveyIntelligenceService:
    def __init__(self, llm: LLMClient, profile: ProfileFacts) -> None:
        self.llm = llm
        self.profile = profile

    async def suggest(self, snapshot: SurveySnapshot) -> IntelligenceResult:
        if snapshot.stop_reason is not None:
            return IntelligenceResult(stop_reason=snapshot.stop_reason)

        suggestions: list[SurveySuggestion] = []
        for question in snapshot.questions:
            if question.question_type in {QuestionType.ATTESTATION, QuestionType.ELIGIBILITY}:
                return IntelligenceResult(
                    suggestions=suggestions,
                    stop_reason=StopReason.ELIGIBILITY_ATTESTATION,
                )
            answer = await self.llm.suggest(
                question.text,
                question.options,
                question.question_type,
                self.profile.all() if question.question_type == QuestionType.FACTUAL else [],
            )
            answer = self._validate_suggestion(question, answer)
            suggestions.append(SurveySuggestion(question_id=question.id, suggestion=answer))
        return IntelligenceResult(suggestions=suggestions)

    @staticmethod
    def _validate_suggestion(
        question: SurveyQuestion,
        answer: StructuredAnswer,
    ) -> StructuredAnswer:
        if not answer.requires_human_review:
            raise IntelligenceError("Generated answers must require human review.")
        if answer.answer is None:
            return answer
        result = validate_answer(question, answer.answer)
        if not result.valid:
            raise IntelligenceError(result.reason)
        return answer.model_copy(update={"answer": str(result.normalized_value)})
