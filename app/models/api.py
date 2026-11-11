from pydantic import BaseModel, Field

from app.models.domain import (
    IntelligenceResult,
    StopReason,
    SurveyQuestion,
    WorkflowStatus,
)


class HealthResponse(BaseModel):
    status: str
    service: str


class WorkflowResponse(BaseModel):
    status: WorkflowStatus
    detail: str


class ActivityEntry(BaseModel):
    id: int
    question_id: str | None
    action: str
    reason: str
    answer: str | None
    created_at: str


class WorkflowStateResponse(BaseModel):
    status: WorkflowStatus
    browser_connected: bool
    detail: str
    stop_reason: StopReason | None = None
    questions: list[SurveyQuestion] = Field(default_factory=list)
    intelligence: IntelligenceResult | None = None
    pending_question_ids: list[str] = Field(default_factory=list)
    activity: list["ActivityEntry"] = Field(default_factory=list)


class ConnectRequest(BaseModel):
    url: str


class OperationResponse(BaseModel):
    state: WorkflowStateResponse
