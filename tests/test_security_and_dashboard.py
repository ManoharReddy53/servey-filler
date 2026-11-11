from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.config import ConfigurationError, validate_auth_settings
from app.main import app
from app.services.url_security import URLSecurityError, validate_survey_url
from app.browser.session import PlaywrightBrowserSession


def test_url_validation_allows_approved_https_host(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.url_security.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    assert validate_survey_url("https://survey.example.com/path", ("example.com",)).startswith(
        "https://survey.example.com"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://survey.example.com",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://169.254.169.254/latest",
        "https://unapproved.test/",
        "https://user:pass@survey.example.com/",
    ],
)
def test_url_validation_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(URLSecurityError):
        validate_survey_url(url, ("example.com",))


def test_dashboard_html_is_available_and_uses_safe_rendering() -> None:
    response = TestClient(app).get("/ui")
    assert response.status_code == 200
    assert "Panel Station Survey Assistant" in response.text
    assert "textContent" in response.text
    assert "innerHTML" not in response.text
    assert 'call("/activity/history")' in response.text
    assert "await refresh()" in response.text


def test_authentication_is_enforced_when_configured(monkeypatch) -> None:
    token = "test-token"
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: Settings(dashboard_auth_required=True, dashboard_auth_token=token),
    )
    client = TestClient(app)
    assert client.get("/workflow/state").status_code == 401
    assert client.get("/workflow/state", headers={"Authorization": "Bearer test-token"}).status_code == 200


def test_invalid_operation_returns_non_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: Settings(dashboard_auth_required=False),
    )
    response = TestClient(app).post("/workflow/inspect")
    assert response.status_code == 409


def test_auth_configuration_rejects_missing_and_weak_tokens() -> None:
    with pytest.raises(ConfigurationError, match="required"):
        validate_auth_settings(Settings(dashboard_auth_required=True))
    with pytest.raises(ConfigurationError, match="at least"):
        validate_auth_settings(Settings(dashboard_auth_required=True, dashboard_auth_token="short"))


def test_all_workflow_and_dashboard_api_routes_require_auth(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: Settings(dashboard_auth_required=True, dashboard_auth_token="test-token"),
    )
    client = TestClient(app)
    paths = [
        ("/", "get"),
        ("/ui", "get"),
        ("/dashboard", "get"),
        ("/workflow/status", "get"),
        ("/workflow/state", "get"),
        ("/activity/history", "get"),
        ("/workflow/connect", "post"),
        ("/workflow/inspect", "post"),
        ("/workflow/generate", "post"),
        ("/workflow/close", "post"),
    ]
    for path, method in paths:
        if method == "get":
            response = client.get(path)
        else:
            response = client.post(
                path,
                json={"url": "https://example.com"} if path.endswith("connect") else None,
            )
        assert response.status_code == 401, (path, response.status_code)


@pytest.mark.asyncio
async def test_browser_startup_failure_cleans_up_playwright(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "app.services.url_security.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = self
            self.stopped = False

        async def start(self):
            return self

        async def launch_persistent_context(self, **kwargs):
            raise RuntimeError("launch failed")

        async def stop(self):
            self.stopped = True

    fake = FakePlaywright()
    monkeypatch.setattr("app.browser.session.async_playwright", lambda: fake)
    session = PlaywrightBrowserSession(str(tmp_path), ("example.com",))
    with pytest.raises(RuntimeError, match="launch failed"):
        await session.start_authorized("https://survey.example.com")
    assert session._context is None
    assert session._playwright is None
    assert fake.stopped


@pytest.mark.asyncio
async def test_redirect_to_unapproved_host_is_rejected(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "app.services.url_security.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )

    class Page:
        url = "https://survey.example.com"

        async def goto(self, url, wait_until):
            self.url = "https://evil.example"

    class Context:
        pages = []
        closed = False

        async def new_page(self):
            self.page = Page()
            return self.page

        async def route(self, pattern, handler):
            self.handler = handler

        async def close(self):
            self.closed = True

    class Playwright:
        chromium = None

        def __init__(self):
            self.chromium = self
            self.context = Context()
            self.stopped = False

        async def start(self):
            return self

        async def launch_persistent_context(self, **kwargs):
            return self.context

        async def stop(self):
            self.stopped = True

    fake = Playwright()
    monkeypatch.setattr("app.browser.session.async_playwright", lambda: fake)
    session = PlaywrightBrowserSession(str(tmp_path), ("example.com",))
    with pytest.raises(URLSecurityError, match="approved domain"):
        await session.start_authorized("https://survey.example.com")
    assert fake.context.closed
    assert fake.stopped


@pytest.mark.asyncio
async def test_request_guard_aborts_unsafe_subresource_and_allows_approved_request(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "app.services.url_security.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )

    class Request:
        def __init__(self, url: str) -> None:
            self.url = url

    class Route:
        def __init__(self, url: str) -> None:
            self.request = Request(url)
            self.aborted = False
            self.continued = False

        async def abort(self, reason: str) -> None:
            self.aborted = True

        async def continue_(self) -> None:
            self.continued = True

    session = PlaywrightBrowserSession(str(tmp_path), ("example.com",))
    unsafe = Route("https://169.254.169.254/latest/meta-data")
    safe = Route("https://cdn.example.com/script.js")
    await session._guard_request(unsafe)
    await session._guard_request(safe)
    assert unsafe.aborted and not unsafe.continued
    assert safe.continued and not safe.aborted


def test_dns_resolution_changes_fail_closed(monkeypatch) -> None:
    responses = iter(
        [
            [(None, None, None, None, ("93.184.216.34", 0))],
            [(None, None, None, None, ("10.0.0.5", 0))],
        ]
    )
    monkeypatch.setattr(
        "app.services.url_security.socket.getaddrinfo",
        lambda *args, **kwargs: next(responses),
    )
    assert validate_survey_url("https://survey.example.com", ("example.com",))
    with pytest.raises(URLSecurityError, match="blocked"):
        validate_survey_url("https://survey.example.com", ("example.com",))
