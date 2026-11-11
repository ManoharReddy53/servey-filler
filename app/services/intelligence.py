from app.models.domain import (
    DecisionLog,
    IntelligenceResult,
    QuestionType,
    StopReason,
    StructuredAnswer,
    SurveyQuestion,
    SurveySnapshot,
    SurveySuggestion,
)
from app.db.sqlite import SQLiteStore
from app.services.llm import LLMClient
from app.services.profile import ProfileFacts
from app.services.validator import validate_answer


class IntelligenceError(RuntimeError):
    """Raised when an answer cannot be safely used as a survey suggestion."""


class SurveyIntelligenceService:
    def __init__(
        self,
        llm: LLMClient,
        profile: ProfileFacts,
        activity_store: SQLiteStore | None = None,
    ) -> None:
        self.llm = llm
        self.profile = profile
        self.activity_store = activity_store

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
            profile_facts = (
                self.profile.all()
                if question.question_type == QuestionType.FACTUAL
                or self._is_personal_experience(question.text)
                else []
            )
            answer = await self.llm.suggest(
                question.text,
                question.options,
                question.question_type,
                profile_facts,
            )
            answer = self._validate_suggestion(question, answer)
            suggestion = SurveySuggestion(
                    question_id=question.id,
                    suggestion=answer,
                    auto_fill=(
                        answer.answer is not None
                        and question.question_type in {QuestionType.OPINION, QuestionType.PREFERENCE}
                        and not answer.requires_human_review
                    ),
                )
            suggestions.append(suggestion)
            if self.activity_store is not None:
                self.activity_store.save_decision(
                    DecisionLog(
                        question_id=question.id,
                        action="suggest",
                        reason=answer.rationale,
                        answer=answer.answer,
                    )
                )
        return IntelligenceResult(suggestions=suggestions)

    @staticmethod
    def _is_personal_experience(text: str) -> bool:
        normalized = text.casefold()
        return any(
            phrase in normalized
            for phrase in (
                "your experience",
                "your satisfaction",
                "how satisfied are you",
                "do you use",
                "have you used",
                "have you purchased",
                "did you purchase",
                "have you ever",
            )
        )

    def _validate_suggestion(
        self,
        question: SurveyQuestion,
        answer: StructuredAnswer,
    ) -> StructuredAnswer:
        ordinary = question.question_type in {QuestionType.OPINION, QuestionType.PREFERENCE}
        if ordinary and self._is_personal_experience(question.text) and answer.answer is not None:
            if not any(fact.value == answer.answer for fact in self.profile.all()):
                raise IntelligenceError("Personal experience answer is not supported by a verified fact.")
        if not ordinary and not answer.requires_human_review:
            raise IntelligenceError("Generated answers must require human review.")
        if answer.answer is None:
            return answer
        if question.question_type == QuestionType.FACTUAL and not any(
            fact.value == answer.answer for fact in self.profile.all()
        ):
            raise IntelligenceError("Factual answer is not supported by a verified profile fact.")
        result = validate_answer(question, answer.answer)
        if not result.valid:
            raise IntelligenceError(result.reason)
        return answer.model_copy(update={"answer": str(result.normalized_value)})
