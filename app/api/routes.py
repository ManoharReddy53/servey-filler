import hmac

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.models.domain import WorkflowStatus
from app.core.config import get_settings
from app.db.sqlite import SQLiteStore
from app.models.api import (
    ActivityEntry,
    ConnectRequest,
    HealthResponse,
    OperationResponse,
    WorkflowResponse,
    WorkflowStateResponse,
)
from app.services.orchestrator import WorkflowController, WorkflowOperationError
from app.ui import dashboard_page

router = APIRouter()


def _controller(request: Request) -> WorkflowController:
    controller = getattr(request.app.state, "workflow_controller", None)
    if controller is None:
        raise HTTPException(status_code=503, detail="Workflow controller is unavailable.")
    return controller


def _authorize(request: Request) -> None:
    settings = get_settings()
    if not settings.dashboard_auth_required:
        return
    configured = settings.dashboard_auth_token
    if not configured:
        raise HTTPException(status_code=503, detail="Dashboard authentication is not configured.")
    header = request.headers.get("authorization", "")
    expected_header = "Bearer " + configured
    if not hmac.compare_digest(header, expected_header):
        raise HTTPException(status_code=401, detail="Authentication required.")


def _state(controller: WorkflowController) -> WorkflowStateResponse:
    suggestions = controller.result.suggestions if controller.result else []
    return WorkflowStateResponse(
        status=controller.status,
        browser_connected=controller.browser_connected,
        detail=controller.detail,
        stop_reason=controller.snapshot.stop_reason,
        questions=controller.snapshot.questions,
        intelligence=controller.result,
        pending_question_ids=[
            item.question_id for item in suggestions
            if item.suggestion.answer is None or item.suggestion.requires_human_review
        ],
        activity=[
            item for item in controller.store.activity_history()
        ],
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Unauthenticated liveness probe; it exposes no workflow or configuration data."""
    return HealthResponse(status="ok", service="panel-station-ai-survey-assistant")


@router.get("/workflow/status", response_model=WorkflowResponse)
async def workflow_status(request: Request) -> WorkflowResponse:
    _authorize(request)
    controller = _controller(request)
    return WorkflowResponse(status=controller.status, detail=controller.detail)


@router.get("/workflow/state", response_model=WorkflowStateResponse)
async def workflow_state(request: Request) -> WorkflowStateResponse:
    _authorize(request)
    return _state(_controller(request))


@router.get("/dashboard", response_model=WorkflowStateResponse)
async def dashboard(request: Request) -> WorkflowStateResponse:
    _authorize(request)
    return _state(_controller(request))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_ui(request: Request) -> HTMLResponse:
    _authorize(request)
    return dashboard_page()


@router.post("/workflow/connect", response_model=OperationResponse)
async def workflow_connect(request: Request, payload: ConnectRequest) -> OperationResponse:
    _authorize(request)
    controller = _controller(request)
    try:
        await controller.connect(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowOperationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return OperationResponse(state=_state(controller))


@router.post("/workflow/inspect", response_model=OperationResponse)
async def workflow_inspect(request: Request) -> OperationResponse:
    _authorize(request)
    controller = _controller(request)
    try:
        await controller.inspect()
    except WorkflowOperationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OperationResponse(state=_state(controller))


@router.post("/workflow/generate", response_model=OperationResponse)
async def workflow_generate(request: Request) -> OperationResponse:
    _authorize(request)
    controller = _controller(request)
    try:
        await controller.generate_and_fill()
        if controller.status == WorkflowStatus.ERROR:
            raise HTTPException(status_code=502, detail=controller.detail)
    except WorkflowOperationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OperationResponse(state=_state(controller))


@router.post("/workflow/close", response_model=OperationResponse)
async def workflow_close(request: Request) -> OperationResponse:
    _authorize(request)
    controller = _controller(request)
    await controller.close()
    return OperationResponse(state=_state(controller))


@router.get("/activity/history", response_model=list[ActivityEntry])
def activity_history(request: Request, limit: int = 100) -> list[ActivityEntry]:
    _authorize(request)
    store = SQLiteStore(get_settings().database_path)
    store.initialize()
    return [ActivityEntry.model_validate(entry) for entry in store.activity_history(limit)]
