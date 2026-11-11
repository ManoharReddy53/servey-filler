import logging
from dataclasses import dataclass, field

from app.browser.session import PlaywrightBrowserSession
from app.core.config import Settings
from app.db.sqlite import SQLiteStore
from app.models.domain import (
    IntelligenceResult,
    StopReason,
    SurveyQuestion,
    SurveySnapshot,
    WorkflowStatus,
)
from app.services.intelligence import SurveyIntelligenceService
from app.services.llm import LLMError, build_llm_client
from app.services.profile import ProfileFacts
from app.services.workflow import SurveyWorkflow
from app.services.url_security import URLSecurityError, validate_survey_url

logger = logging.getLogger(__name__)


class WorkflowOperationError(RuntimeError):
    """Sanitized failure exposed to API callers."""


@dataclass
class WorkflowController:
    settings: Settings
    profile: ProfileFacts = field(default_factory=ProfileFacts)
    browser: PlaywrightBrowserSession | None = None
    workflow: SurveyWorkflow | None = None
    intelligence: SurveyIntelligenceService | None = None
    snapshot: SurveySnapshot = field(default_factory=SurveySnapshot)
    result: IntelligenceResult | None = None
    status: WorkflowStatus = WorkflowStatus.IDLE
    detail: str = "No browser session is active."
    error: str | None = None

    def __post_init__(self) -> None:
        self.store = SQLiteStore(self.settings.database_path)
        self.store.initialize()

    @property
    def browser_connected(self) -> bool:
        return (
            self.browser is not None
            and self.browser._context is not None
            and not self.browser._context.is_closed()
        )

    async def connect(self, url: str) -> None:
        await self.close()
        try:
            validate_survey_url(url, self.settings.approved_survey_domains)
            self.browser = PlaywrightBrowserSession(
                self.settings.session_storage_path,
                self.settings.approved_survey_domains,
            )
            await self.browser.start_authorized(url)
        except URLSecurityError:
            self.status = WorkflowStatus.ERROR
            self.detail = "Browser connection rejected: URL is not approved."
            self.error = self.detail
            if self.browser is not None:
                await self.browser.close()
                self.browser = None
            raise
        except Exception as exc:
            logger.exception("Browser startup failed")
            if self.browser is not None:
                await self.browser.close()
                self.browser = None
            self.status = WorkflowStatus.ERROR
            self.detail = "Browser connection failed."
            self.error = self.detail
            raise WorkflowOperationError(self.detail) from exc
        self.workflow = SurveyWorkflow(self.browser, self.profile, self.store)
        self.intelligence = SurveyIntelligenceService(
            build_llm_client(self.settings), self.profile, self.store
        )
        self.status = WorkflowStatus.EXTRACTING
        self.detail = "Browser connected."
        self.error = None

    async def inspect(self) -> SurveySnapshot:
        if self.workflow is None:
            raise RuntimeError("Browser connection must be established first.")
        self.status = WorkflowStatus.EXTRACTING
        try:
            self.snapshot = await self.workflow.inspect()
        except Exception as exc:
            self._handle_error(exc, "Browser inspection failed.")
            raise WorkflowOperationError(self.detail) from exc
        self.status = WorkflowStatus.STOPPED if self.snapshot.stop_reason else WorkflowStatus.READY
        self.detail = (
            f"Safety stop: {self.snapshot.stop_reason.value}."
            if self.snapshot.stop_reason
            else f"Extracted {len(self.snapshot.questions)} questions."
        )
        return self.snapshot

    async def generate_and_fill(self) -> IntelligenceResult:
        if self.intelligence is None or self.workflow is None:
            raise RuntimeError("Browser connection must be established first.")
        snapshot = self.snapshot if self.snapshot.questions or self.snapshot.stop_reason else await self.inspect()
        if snapshot.stop_reason is not None:
            self.result = IntelligenceResult(stop_reason=snapshot.stop_reason)
            return self.result
        self.status = WorkflowStatus.EXTRACTING
        try:
            self.result = await self.intelligence.suggest(snapshot)
            if self.result.stop_reason is not None:
                self.status = WorkflowStatus.STOPPED
                self.detail = f"Safety stop: {self.result.stop_reason.value}."
                return self.result
            await self.workflow.apply_suggestions(self.result.suggestions)
        except (LLMError, RuntimeError) as exc:
            self._handle_error(exc, "Survey processing failed.")
            self.result = IntelligenceResult(error=self.detail)
            return self.result
        except Exception as exc:
            logger.exception("Unexpected survey processing failure")
            self._handle_error(exc, "Survey processing failed.")
            self.result = IntelligenceResult(error=self.detail)
            return self.result
        self.status = WorkflowStatus.READY
        self.detail = "Answers generated and eligible answers filled. Submission remains manual."
        return self.result

    async def close(self) -> None:
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                logger.exception("Failed to close browser session")
        self.browser = None
        self.workflow = None
        self.intelligence = None
        if self.status != WorkflowStatus.ERROR:
            self.status = WorkflowStatus.IDLE
            self.detail = "No browser session is active."

    def _handle_error(self, error: Exception, detail: str) -> None:
        self.status = WorkflowStatus.ERROR
        self.error = str(error) if isinstance(error, LLMError) else detail
        self.detail = self.error
