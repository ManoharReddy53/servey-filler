from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings, validate_auth_settings
from app.services.orchestrator import WorkflowController


@asynccontextmanager
async def lifespan(application: FastAPI):
    validate_auth_settings(get_settings())
    try:
        yield
    finally:
        await application.state.workflow_controller.close()


app = FastAPI(
    title="Panel Station AI Survey Assistant",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.state.workflow_controller = WorkflowController(get_settings())
