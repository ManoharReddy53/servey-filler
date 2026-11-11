from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.browser.session import PlaywrightBrowserSession
from app.models.domain import InputType, StopReason
from app.services.profile import ProfileFacts
from app.services.workflow import SurveyWorkflow


@pytest.fixture
async def session(tmp_path: Path):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        session = PlaywrightBrowserSession(str(tmp_path))
        session._playwright = playwright
        session._context = context
        yield session, page
        await context.close()
        await browser.close()


@pytest.mark.asyncio
async def test_extracts_text_input_and_textarea(session) -> None:
    current, page = session
    await page.set_content(
        '<label for="name">Your name</label><input id="name" required>'
        '<label for="details">Details</label><textarea id="details"></textarea>'
    )
    questions = await current.extract_visible_questions()
    assert [(question.input_type, question.text, question.required) for question in questions] == [
        (InputType.TEXT, "Your name", True),
        (InputType.TEXTAREA, "Details", False),
    ]


@pytest.mark.asyncio
async def test_groups_radio_buttons_and_extracts_options(session) -> None:
    current, page = session
    await page.set_content(
        '<fieldset><legend>What is your age?</legend>'
        '<label><input type="radio" name="age" value="30">30</label>'
        '<label><input type="radio" name="age" value="40" aria-required="true">40</label>'
        '</fieldset>'
    )
    questions = await current.extract_visible_questions()
    assert len(questions) == 1
    assert questions[0].input_type == InputType.RADIO
    assert questions[0].text == "What is your age?"
    assert questions[0].options == ["30", "40"]
    assert questions[0].required


@pytest.mark.asyncio
async def test_groups_checkboxes_and_uses_aria_labelledby(session) -> None:
    current, page = session
    await page.set_content(
        '<span id="question">Which fruits?</span><div role="group" aria-labelledby="question">'
        '<label><input type="checkbox" name="fruit" value="apple">Apple</label>'
        '<label><input type="checkbox" name="fruit" value="pear">Pear</label></div>'
    )
    questions = await current.extract_visible_questions()
    assert len(questions) == 1
    assert questions[0].input_type == InputType.CHECKBOX
    assert questions[0].text == "Which fruits?"
    assert questions[0].options == ["Apple", "Pear"]


@pytest.mark.asyncio
async def test_extracts_dropdown_and_excludes_disabled_placeholder(session) -> None:
    current, page = session
    await page.set_content(
        '<label for="country">Country</label><select id="country">'
        '<option value="">Choose one</option><option value="us">United States</option>'
        '<option value="ca" disabled>Canada</option></select>'
    )
    questions = await current.extract_visible_questions()
    assert questions[0].input_type == InputType.SELECT
    assert questions[0].options == ["United States"]


@pytest.mark.asyncio
async def test_excludes_hidden_and_disabled_controls_and_handles_missing_label(session) -> None:
    current, page = session
    await page.set_content(
        '<input id="hidden" type="hidden"><input id="display-none" style="display:none">'
        '<input id="disabled" disabled><input id="unlabelled">'
    )
    questions = await current.extract_visible_questions()
    assert len(questions) == 1
    assert questions[0].text == "Question 1"


@pytest.mark.asyncio
async def test_extracts_multiple_independent_questions_without_duplicates(session) -> None:
    current, page = session
    await page.set_content(
        '<label for="one">First</label><input id="one">'
        '<label for="two">Second</label><input id="two">'
        '<fieldset><legend>Choice</legend><label><input type="radio" name="choice" value="a">A</label>'
        '<label><input type="radio" name="choice" value="b">B</label></fieldset>'
    )
    questions = await current.extract_visible_questions()
    assert [question.text for question in questions] == ["First", "Second", "Choice"]
    assert len({question.id for question in questions}) == 3


@pytest.mark.asyncio
async def test_rejects_invalid_and_fills_valid_radio_checkbox_and_dropdown(session) -> None:
    current, page = session
    await page.set_content(
        '<fieldset><legend>Color</legend><label><input type="radio" name="color" value="red">Red</label>'
        '<label><input type="radio" name="color" value="blue">Blue</label></fieldset>'
        '<fieldset><legend>Food</legend><label><input type="checkbox" name="food" value="pizza">Pizza</label>'
        '<label><input type="checkbox" name="food" value="salad">Salad</label></fieldset>'
        '<label for="size">Size</label><select id="size"><option value="s">Small</option>'
        '<option value="l">Large</option></select>'
    )
    questions = await current.extract_visible_questions()
    with pytest.raises(ValueError, match="available options"):
        await current.fill(questions[0].id, "green")
    await current.fill(questions[0].id, "Blue")
    await current.fill(questions[1].id, "Pizza")
    await current.fill(questions[2].id, "Large")
    assert await page.locator('input[value="blue"]').is_checked()
    assert await page.locator('input[value="pizza"]').is_checked()
    assert await page.locator("#size").input_value() == "l"


@pytest.mark.asyncio
async def test_stops_on_captcha_and_attestation(session) -> None:
    current, page = session
    await page.set_content("<p>Please complete the CAPTCHA before continuing.</p>")
    assert (await current.inspect_current_page()).stop_reason == StopReason.CAPTCHA

    await page.set_content(
        '<label for="agree">Do you certify that the answers are accurate?</label><input id="agree">'
    )
    snapshot = await SurveyWorkflow(current, ProfileFacts()).inspect()
    assert snapshot.stop_reason == StopReason.ELIGIBILITY_ATTESTATION
