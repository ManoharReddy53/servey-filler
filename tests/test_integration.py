from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.browser.session import PlaywrightBrowserSession
from app.core.config import Settings
from app.db.sqlite import SQLiteStore
from app.models.domain import (
    IntelligenceResult,
    QuestionType,
    StructuredAnswer,
    SurveyQuestion,
    SurveySnapshot,
)
from app.services.intelligence import SurveyIntelligenceService
from app.services.orchestrator import WorkflowController
from app.services.profile import ProfileFacts
from app.services.workflow import SurveyWorkflow


class FixtureLLM:
    async def suggest(self, question, options, question_type, profile_facts):
        if options:
            answer = options[0]
        else:
            answer = "It is a practical and convenient option."
        return StructuredAnswer(
            answer=answer,
            rationale="Local fixture response.",
            requires_human_review=False,
        )


@pytest.mark.asyncio
async def test_local_html_flows_from_extraction_to_fill_and_sqlite(tmp_path: Path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.set_content(
            '<label for="opinion">What do you think about online shopping?</label>'
            '<textarea id="opinion"></textarea>'
            '<fieldset><legend>Which feature is most important?</legend>'
            '<label><input type="radio" name="feature" value="Battery life">Battery life</label>'
            '<label><input type="radio" name="feature" value="Camera">Camera</label></fieldset>'
        )
        session = PlaywrightBrowserSession(str(tmp_path / "browser"))
        session._playwright = playwright
        session._context = context
        store = SQLiteStore(str(tmp_path / "activity.sqlite3"))
        store.initialize()
        workflow = SurveyWorkflow(session, ProfileFacts(), store)
        intelligence = SurveyIntelligenceService(FixtureLLM(), ProfileFacts(), store)

        snapshot = await workflow.inspect()
        result = await intelligence.suggest(snapshot)
        decisions = await workflow.apply_suggestions(result.suggestions)

        assert len(snapshot.questions) == 2
        assert result.suggestions[0].auto_fill
        assert any(decision.action == "fill" for decision in decisions)
        assert await page.locator("#opinion").input_value() == "It is a practical and convenient option."
        assert await page.locator('input[value="Battery life"]').is_checked()
        assert len(store.activity_history()) >= 4
        await context.close()
        await browser.close()


@pytest.mark.asyncio
async def test_controller_stops_on_captcha_without_calling_llm(tmp_path: Path) -> None:
    settings = Settings(
        database_path=str(tmp_path / "state.sqlite3"),
        session_storage_path=str(tmp_path / "browser"),
        llm_provider="disabled",
    )
    controller = WorkflowController(settings)
    class FakeBrowser:
        _context = None

        async def inspect_current_page(self):
            from app.models.domain import StopReason

            return SurveySnapshot(stop_reason=StopReason.CAPTCHA)

        async def close(self):
            pass

    controller.browser = FakeBrowser()
    controller.workflow = SurveyWorkflow(controller.browser, ProfileFacts(), controller.store)
    snapshot = await controller.inspect()
    assert snapshot.stop_reason.value == "captcha"
    assert controller.status.value == "stopped"


@pytest.mark.asyncio
async def test_controller_handles_gemini_error_without_filling(tmp_path: Path) -> None:
    settings = Settings(
        database_path=str(tmp_path / "state.sqlite3"),
        session_storage_path=str(tmp_path / "browser"),
        llm_provider="disabled",
    )
    controller = WorkflowController(settings)
    controller.browser = type("Browser", (), {"_context": None})()
    controller.workflow = SurveyWorkflow(
        controller.browser,
        ProfileFacts(),
        controller.store,
    )
    controller.intelligence = type(
        "FailingIntelligence",
        (),
        {"suggest": lambda self, snapshot: (_ for _ in ()).throw(RuntimeError("Gemini unavailable"))},
    )()
    controller.snapshot = SurveySnapshot(
        questions=[SurveyQuestion(id="q", text="What do you think?", question_type=QuestionType.OPINION)]
    )
    result = await controller.generate_and_fill()
    assert isinstance(result, IntelligenceResult)
    assert controller.status.value == "error"
