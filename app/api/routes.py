from fastapi import APIRouter

from app.models.domain import WorkflowStatus
from app.core.config import get_settings
from app.db.sqlite import SQLiteStore
from app.models.api import ActivityEntry, HealthResponse, WorkflowResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="panel-station-ai-survey-assistant")


@router.get("/workflow/status", response_model=WorkflowResponse)
def workflow_status() -> WorkflowResponse:
    return WorkflowResponse(status=WorkflowStatus.IDLE, detail="No browser session is active.")


@router.get("/activity/history", response_model=list[ActivityEntry])
def activity_history(limit: int = 100) -> list[ActivityEntry]:
    store = SQLiteStore(get_settings().database_path)
    store.initialize()
    return [ActivityEntry.model_validate(entry) for entry in store.activity_history(limit)]
