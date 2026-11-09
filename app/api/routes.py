from fastapi import APIRouter

from app.models.domain import WorkflowStatus
from app.models.api import HealthResponse, WorkflowResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="panel-station-ai-survey-assistant")


@router.get("/workflow/status", response_model=WorkflowResponse)
def workflow_status() -> WorkflowResponse:
    return WorkflowResponse(status=WorkflowStatus.IDLE, detail="No browser session is active.")
