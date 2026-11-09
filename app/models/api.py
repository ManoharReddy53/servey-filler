from pydantic import BaseModel

from app.models.domain import WorkflowStatus


class HealthResponse(BaseModel):
    status: str
    service: str


class WorkflowResponse(BaseModel):
    status: WorkflowStatus
    detail: str
