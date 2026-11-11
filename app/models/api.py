from pydantic import BaseModel

from app.models.domain import WorkflowStatus


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
