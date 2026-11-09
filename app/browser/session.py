from pathlib import Path
from typing import Protocol

from playwright.async_api import BrowserContext, Playwright, async_playwright

from app.models.domain import StopReason, SurveyQuestion, SurveySnapshot
from app.services.safety import detect_stop_reason


class BrowserSession(Protocol):
    async def extract_visible_questions(self) -> list[SurveyQuestion]: ...
    async def fill(self, question_id: str, value: str) -> None: ...
    async def close(self) -> None: ...


class PlaywrightBrowserSession:
    """Adapter boundary; navigation and submission are intentionally absent."""

    def __init__(self, storage_path: str) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    async def start_authorized(self, url: str) -> None:
        """Open a visible persistent context and navigate to an explicit user URL."""
        if self._context is not None:
            return
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.storage_path),
            headless=False,
        )
        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

    async def inspect_current_page(self) -> SurveySnapshot:
        if self._context is None:
            raise RuntimeError("Browser authorization must be established explicitly before extraction.")
        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        stop_reason = detect_stop_reason(await page.locator("body").inner_text())
        if stop_reason is not None:
            return SurveySnapshot(stop_reason=stop_reason)
        return SurveySnapshot(questions=await self.extract_visible_questions())

    async def extract_visible_questions(self) -> list[SurveyQuestion]:
        if self._context is None:
            raise RuntimeError("Browser authorization must be established explicitly before extraction.")
        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        controls = page.locator("input:not([type='hidden']):not([type='submit']):not([type='password']), textarea, select")
        questions: list[SurveyQuestion] = []
        for index in range(await controls.count()):
            control = controls.nth(index)
            if not await control.is_visible():
                continue
            question_id = await control.get_attribute("name") or await control.get_attribute("id") or f"control-{index}"
            label = await control.evaluate(
                """element => {
                    const id = element.id;
                    const explicit = id ? document.querySelector(`label[for="${id}"]`) : null;
                    const parent = element.closest('label');
                    return (explicit || parent)?.innerText?.trim() || element.getAttribute('aria-label') || '';
                }"""
            )
            if not label:
                continue
            options = await control.locator("option").all_inner_texts() if await control.evaluate(
                "element => element.tagName.toLowerCase() === 'select'"
            ) else []
            questions.append(SurveyQuestion(id=question_id, text=label, options=options))
        return questions

    async def fill(self, question_id: str, value: str) -> None:
        raise RuntimeError("Playwright session is not connected.")

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
