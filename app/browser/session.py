from pathlib import Path
from typing import Protocol

from playwright.async_api import BrowserContext, Playwright, async_playwright

from app.models.domain import InputType, StopReason, SurveyQuestion, SurveySnapshot
from app.services.safety import detect_stop_reason
from app.services.url_security import validate_request_url, validate_survey_url


class BrowserSession(Protocol):
    async def extract_visible_questions(self) -> list[SurveyQuestion]: ...
    async def fill(self, question_id: str, value: str) -> None: ...
    async def close(self) -> None: ...


class PlaywrightBrowserSession:
    """Adapter boundary; navigation and submission are intentionally absent."""

    def __init__(self, storage_path: str, approved_domains: tuple[str, ...] = ()) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._question_controls: dict[str, dict[str, object]] = {}
        self.approved_domains = approved_domains

    async def start_authorized(self, url: str) -> None:
        """Open a visible persistent context and navigate to an explicit user URL."""
        if self._context is not None:
            return
        safe_url = validate_survey_url(url, self.approved_domains)
        try:
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.storage_path),
                headless=False,
            )
            route = getattr(self._context, "route", None)
            if route is None:
                raise RuntimeError("Browser request interception is unavailable.")
            await route("**/*", self._guard_request)
            page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            await page.goto(safe_url, wait_until="domcontentloaded")
            validate_survey_url(page.url, self.approved_domains)
        except Exception:
            await self.close()
            raise

    async def _guard_request(self, route) -> None:
        try:
            validate_request_url(route.request.url, self.approved_domains)
        except Exception:
            await route.abort("blockedbyclient")
            return
        await route.continue_()

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
        extracted = await page.evaluate(
            """() => {
                const controls = Array.from(document.querySelectorAll(
                    'input, textarea, select'
                ));
                const visible = element => {
                    if (element.disabled || element.hidden ||
                        element.getAttribute('aria-hidden') === 'true') return false;
                    const fieldset = element.closest('fieldset[disabled]');
                    if (fieldset) return false;
                    const style = window.getComputedStyle(element);
                    return style.display !== 'none' && style.visibility !== 'hidden' &&
                        element.getClientRects().length > 0;
                };
                const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
                const text = element => clean(element?.innerText || element?.textContent);
                const labelledBy = element => {
                    const ids = (element.getAttribute('aria-labelledby') || '').split(/\\s+/);
                    return clean(ids.map(id => document.getElementById(id))
                        .filter(Boolean).map(item => text(item)).join(' '));
                };
                const questionContainer = element => element.closest(
                    'fieldset, [role="group"], [data-question], .question, .question-container, .survey-question'
                );
                const labelFor = element => {
                    const id = element.id;
                    const explicit = id ? document.querySelector(
                        `label[for="${CSS.escape(id)}"]`
                    ) : null;
                    const parent = element.closest('label');
                    const container = questionContainer(element);
                    const legend = container?.querySelector(':scope > legend, legend');
                    return clean(
                        text(legend) ||
                        element.getAttribute('aria-label') ||
                        labelledBy(element) ||
                        (container && labelledBy(container)) ||
                        text(explicit || parent) ||
                        (container ? text(container).replace(text(element), '') : '')
                    );
                };
                const optionLabel = element => {
                    const explicit = element.id ? document.querySelector(
                        `label[for="${CSS.escape(element.id)}"]`
                    ) : null;
                    return clean(text(explicit || element.closest('label')) ||
                        element.getAttribute('aria-label') || element.value);
                };
                const keyFor = element => {
                    const container = questionContainer(element);
                    if (element.name) return `name:${element.name}`;
                    if (container) {
                        if (!container.dataset.surveyExtractionId) {
                            container.dataset.surveyExtractionId =
                                `container-${Array.from(document.querySelectorAll('*')).indexOf(container)}`;
                        }
                        return container.dataset.surveyExtractionId;
                    }
                    return `control:${Array.from(controls).indexOf(element)}`;
                };
                const groups = new Map();
                for (const element of controls) {
                    if (!visible(element)) continue;
                    const tag = element.tagName.toLowerCase();
                    const rawType = tag === 'textarea' ? 'textarea' :
                        tag === 'select' ? 'select' : (element.type || 'text').toLowerCase();
                    if (!['text', 'email', 'tel', 'number', 'url', 'search',
                          'date', 'textarea', 'select', 'radio', 'checkbox'].includes(rawType)) continue;
                    const type = rawType === 'textarea' ? 'textarea' :
                        rawType === 'select' ? 'select' :
                        ['radio', 'checkbox'].includes(rawType) ? rawType : 'text';
                    const grouped = type === 'radio' || type === 'checkbox';
                    const key = grouped ? `${type}:${keyFor(element)}` :
                        `control:${Array.from(controls).indexOf(element)}`;
                    let group = groups.get(key);
                    if (!group) {
                        group = {
                            type, text: labelFor(element), required: false, options: [],
                            indexes: []
                        };
                        groups.set(key, group);
                    }
                    group.text = group.text || labelFor(element);
                    group.required = group.required ||
                        element.required || element.getAttribute('aria-required') === 'true';
                    group.indexes.push(Array.from(controls).indexOf(element));
                    if (type === 'select') {
                        for (const option of Array.from(element.options)) {
                            const label = clean(option.textContent);
                            if (!option.disabled && !option.hidden && option.value &&
                                label && !option.placeholder && option.value !== '') {
                                group.options.push({label, value: option.value});
                            }
                        }
                    } else if (grouped) {
                        const label = optionLabel(element);
                        if (!element.disabled && label && !group.options.some(item => item.value === element.value)) {
                            group.options.push({label, value: element.value});
                        }
                    }
                }
                return Array.from(groups.values()).map((group, index) => ({
                    ...group,
                    text: group.text || `Question ${index + 1}`,
                    id: `question-${index + 1}`
                }));
            }"""
        )
        self._question_controls = {item["id"]: item for item in extracted}
        return [
            SurveyQuestion(
                id=item["id"],
                text=item["text"],
                options=[option["label"] for option in item["options"]],
                required=item["required"],
                input_type=InputType(item["type"]),
            )
            for item in extracted
        ]

    async def fill(self, question_id: str, value: str) -> None:
        if self._context is None:
            raise RuntimeError("Browser authorization must be established explicitly before filling.")
        control = self._question_controls.get(question_id)
        if control is None:
            raise ValueError("Question was not present in the current page snapshot.")
        options = control["options"]
        selected = next(
            (option for option in options if option["label"] == value or option["value"] == value),
            None,
        )
        if control["type"] in {"radio", "checkbox", "select"} and selected is None:
            raise ValueError("Answer is not one of the available options.")
        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        locator = page.locator("input, textarea, select").nth(control["indexes"][0])
        if control["type"] == "radio":
            await locator.evaluate(
                """(element, value) => {
                const scope = element.name
                    ? document.querySelectorAll(
                        `input[type="radio"][name="${CSS.escape(element.name)}"]`
                    )
                    : (element.closest('fieldset, [role="group"], [data-question], .question, .question-container, .survey-question')
                        || document).querySelectorAll('input[type="radio"]');
                const target = Array.from(scope).find(item => item.value === value);
                    if (!target || target.disabled) throw new Error('Radio option is unavailable.');
                    target.click();
                }""",
                selected["value"],
            )
        elif control["type"] == "checkbox":
            await locator.evaluate(
                """(element, value) => {
                const scope = element.name
                    ? document.querySelectorAll(
                        `input[type="checkbox"][name="${CSS.escape(element.name)}"]`
                    )
                    : (element.closest('fieldset, [role="group"], [data-question], .question, .question-container, .survey-question')
                        || document).querySelectorAll('input[type="checkbox"]');
                const target = Array.from(scope).find(item => item.value === value);
                    if (!target || target.disabled) throw new Error('Checkbox option is unavailable.');
                    target.click();
                }""",
                selected["value"],
            )
        elif control["type"] == "select":
            await locator.select_option(selected["value"])
        else:
            await locator.fill(value)

    async def close(self) -> None:
        context = self._context
        playwright = self._playwright
        self._context = None
        self._playwright = None
        try:
            if context is not None:
                await context.close()
        finally:
            if playwright is not None:
                await playwright.stop()
