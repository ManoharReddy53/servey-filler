from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QuestionType(StrEnum):
    FACTUAL = "factual"
    PREFERENCE = "preference"
    OPINION = "opinion"
    ELIGIBILITY = "eligibility"
    ATTESTATION = "attestation"
    UNKNOWN = "unknown"


class WorkflowStatus(StrEnum):
    IDLE = "idle"
    EXTRACTING = "extracting"
    READY = "ready"
    STOPPED = "stopped"


class StopReason(StrEnum):
    CAPTCHA = "captcha"
    ANTI_BOT = "anti_bot"
    ELIGIBILITY_ATTESTATION = "eligibility_attestation"
    MANUAL_SUBMISSION = "manual_submission"
    PLATFORM_RESTRICTION = "platform_restriction"


class ProfileFact(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    verified: bool = False
    source: str = Field(min_length=1)


class SurveyQuestion(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    required: bool = False
    question_type: QuestionType = QuestionType.UNKNOWN
    visible: bool = True


class AnswerCandidate(BaseModel):
    question_id: str
    value: Any
    source: str
    permitted: bool = False
    confidence: float = Field(ge=0, le=1, default=0)


class StructuredAnswer(BaseModel):
    answer: str | None = None
    confidence: float = Field(ge=0, le=1, default=0)
    rationale: str
    requires_human_review: bool = True


class ValidationResult(BaseModel):
    question_id: str
    valid: bool
    reason: str
    normalized_value: Any | None = None


class DecisionLog(BaseModel):
    question_id: str | None = None
    action: str
    reason: str
    validation: ValidationResult | None = None


class UnresolvedAnswer(BaseModel):
    question_id: str
    reason: str


class SurveySnapshot(BaseModel):
    questions: list[SurveyQuestion] = Field(default_factory=list)
    stop_reason: StopReason | None = None
