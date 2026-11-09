import logging

from app.browser.session import BrowserSession
from app.models.domain import (
    AnswerCandidate,
    DecisionLog,
    QuestionType,
    StopReason,
    SurveySnapshot,
    UnresolvedAnswer,
)
from app.services.classifier import classify_questions
from app.services.profile import ProfileFacts
from app.services.validator import validate_answer

logger = logging.getLogger(__name__)


class SurveyWorkflow:
    def __init__(self, browser: BrowserSession, profile: ProfileFacts) -> None:
        self.browser = browser
        self.profile = profile
        self.decisions: list[DecisionLog] = []
        self.unresolved: list[UnresolvedAnswer] = []

    async def inspect(self) -> SurveySnapshot:
        questions = classify_questions(await self.browser.extract_visible_questions())
        for question in questions:
            if question.question_type in {QuestionType.ATTESTATION, QuestionType.ELIGIBILITY}:
                self.decisions.append(
                    DecisionLog(
                        question_id=question.id,
                        action="stop",
                        reason="Human review required for eligibility or attestation.",
                    )
                )
                return SurveySnapshot(
                    questions=questions,
                    stop_reason=StopReason.ELIGIBILITY_ATTESTATION,
                )
        return SurveySnapshot(questions=questions)

    async def apply(self, candidates: list[AnswerCandidate]) -> list[DecisionLog]:
        snapshot = await self.inspect()
        if snapshot.stop_reason is not None:
            self.decisions.append(
                DecisionLog(
                    action="stop",
                    reason=f"Filling blocked by stop condition: {snapshot.stop_reason.value}.",
                )
            )
            return self.decisions
        questions = {question.id: question for question in snapshot.questions}
        for candidate in candidates:
            question = questions.get(candidate.question_id)
            if question is None:
                self._unresolved(candidate.question_id, "Question was not visible in the snapshot.")
                continue
            if question.question_type in {
                QuestionType.PREFERENCE,
                QuestionType.OPINION,
                QuestionType.UNKNOWN,
            }:
                self._unresolved(question.id, "Personal preference or opinion cannot be fabricated.")
                continue
            if not candidate.permitted or candidate.source != "verified_profile":
                self._unresolved(question.id, "Only verified profile facts may be auto-filled.")
                continue
            result = validate_answer(question, candidate.value)
            self.decisions.append(
                DecisionLog(question_id=question.id, action="validate", reason=result.reason, validation=result)
            )
            if not result.valid:
                self._unresolved(question.id, result.reason)
                continue
            await self.browser.fill(question.id, str(result.normalized_value))
            self.decisions.append(
                DecisionLog(question_id=question.id, action="fill", reason="Validated permitted answer was filled.")
            )
        return self.decisions

    def _unresolved(self, question_id: str, reason: str) -> None:
        logger.info("Unresolved answer question_id=%s reason=%s", question_id, reason)
        self.unresolved.append(UnresolvedAnswer(question_id=question_id, reason=reason))
        self.decisions.append(DecisionLog(question_id=question_id, action="unresolved", reason=reason))
