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
manual submission. I cannot automate CAPTCHA or answer qualification/eligibility
questions for you. Factual answers may use verified profile facts; preference
and opinion answers remain unresolved unless explicitly supplied by the user.

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
