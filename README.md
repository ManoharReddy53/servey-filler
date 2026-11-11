# Panel Station AI Survey Assistant

Safety-first application skeleton for extracting and assisting with surveys. It
does not contain a target URL, does not navigate to Panel Station, and never
submits a survey.

## Architecture

- `app/api`: FastAPI health and read-only workflow endpoints.
- `app/browser`: browser session abstraction and Playwright implementation.
- `app/models`: Pydantic domain and API models.
- `app/services`: classification, profile facts, answer validation, and workflow policy.
- `app/db`: SQLite persistence for profiles, surveys, decisions, and unresolved answers.

The browser must be authorized by a user through a visible browser session. The
workflow stops before CAPTCHA, anti-bot checks, eligibility attestations, and
manual submission. CAPTCHA solving and survey submission are always manual.
Factual answers require verified profile facts; unsupported personal experiences
are never fabricated.

## Dashboard and protected API

The browser dashboard is available at `/ui` (and `/`) when the FastAPI server is
running. It provides connect, inspect, generate-and-fill, disconnect, workflow
status, pending questions, safety interruptions, and activity history. Activity
history is fetched from `/activity/history` after each operation.

Configure an explicit approved-domain allowlist and a strong bearer token:

```dotenv
APPROVED_SURVEY_DOMAINS=surveys.example.com
DASHBOARD_AUTH_REQUIRED=true
DASHBOARD_AUTH_TOKEN=<random-token-at-least-32-characters>
```

Generate a token without putting it in source control:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`/health` is intentionally unauthenticated and returns only a liveness response.
All dashboard, workflow, and activity endpoints require `Authorization: Bearer
<token>` when authentication is enabled. Use HTTPS/TLS and restrict inbound
access with a firewall or private network; do not expose the development server
directly to the public internet.

Browser requests are intercepted and each request URL is checked for HTTPS,
approved hostnames, and unsafe resolved address ranges. Playwright does not
provide an atomic DNS pinning mechanism: a hostname can change between the
validation lookup and the browser connection (DNS rebinding/TOCTOU). For
production, enforce an outbound firewall or proxy allowlist that permits only
the approved survey domains and blocks loopback, private, link-local, reserved,
and cloud-metadata networks. The application fails closed when resolution or
request interception is unavailable, but this network control is still required
for a complete rebinding defense.

## Safe browser inspection

After confirming that automation is allowed by the platform and your account,
run this command with an explicit permitted survey URL:

```bash
.venv/bin/python scripts/panelstation_inspect.py --url 'https://YOUR-PERMITTED-SURVEY-URL'
```

The browser is visible and persistent under `./browser-state`. Log in manually,
open a survey yourself, and press Enter. The harness only reads visible labeled
form controls and prints classified questions as JSON. It does not answer,
submit, bypass CAPTCHA, or navigate to another survey. Stop immediately if the
page shows a CAPTCHA, anti-bot check, eligibility/attestation, or a platform
warning. Delete `browser-state/` only if you intentionally want to remove the
local session.

## Development

```bash
python -m pip install -e '.[test]'
playwright install chromium
pytest
uvicorn app.main:app --reload
```

Keep `GEMINI_API_KEY` in the environment (or a secret manager); never commit it.

## Gemini integration

The configured provider defaults to `disabled`. To use Gemini, set
`LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, and optionally `GEMINI_MODEL` in `.env`.
The client verifies the configured model, requests JSON matching `StructuredAnswer`,
applies a timeout, and sanitizes authentication, quota, timeout, and malformed
response failures.

Run the optional synthetic connectivity test:

```bash
.venv/bin/python scripts/gemini_smoke_test.py
```

It requires `GEMINI_API_KEY` and sends only a synthetic question. It does not
access Panel Station or start Playwright.

For a separate live smoke test using the exact prompt
`Explain what an AI agent is in two sentences.`:

```bash
.venv/bin/python scripts/test_gemini_live.py
```

It reads `.env`, verifies the configured model, and prints only a status plus
the model response or a sanitized error. It never prints the API key.
# servey-filler
