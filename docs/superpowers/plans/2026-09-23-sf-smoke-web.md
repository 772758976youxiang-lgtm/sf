# SF Express Smoke Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a localhost-only visual smoke page for the existing SF Express order and tracking workflows.

**Architecture:** A Python standard-library HTTP server serves packaged HTML/CSS/JS and two JSON endpoints. Endpoint handlers validate inputs with the existing Pydantic models and call the existing service functions. The browser never receives credentials.

**Tech Stack:** Python 3.11 standard library, existing Pydantic/httpx/MCP dependencies, vanilla HTML/CSS/JS, pytest.

---

## File map

- `src/sf_express_mcp/smoke_web.py`: loopback HTTP server, JSON endpoint validation, sandbox gate, static assets.
- `src/sf_express_mcp/web/index.html`: order and tracking forms plus result regions.
- `src/sf_express_mcp/web/style.css`: responsive visual layout.
- `src/sf_express_mcp/web/app.js`: form state, confirmation preview, fetch calls, safe DOM rendering.
- `tests/test_smoke_web.py`: local HTTP endpoint and sandbox safety tests.
- `pyproject.toml`: package static assets and add launch command.
- `README.md`: start/stop and smoke test instructions.

## Task 1: Local JSON API

- [ ] **Step 1: Write failing tests** in `tests/test_smoke_web.py` for `GET /api/status` returning only `environment` and `credentials_configured`, malformed JSON returning 400, production `POST /api/order` returning 403 without calling SF, and sandbox `POST /api/track` delegating a validated `TrackInput` to the existing service. Use an HTTP server bound to `127.0.0.1` on port `0` and a test client, with monkeypatched service functions to prevent external calls.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_smoke_web.py -q`; expect import failure before implementation.
- [ ] **Step 3: Implement** `SmokeApi` with `status`, `order`, and `track`; parse Pydantic models, call existing service functions, return JSON results and HTTP status. Implement `make_server(port=8765, api=None)` using `ThreadingHTTPServer(("127.0.0.1", port), Handler)`. Handler accepts only `/api/order` and `/api/track` JSON POSTs up to 32 KiB, checks same-origin `Origin`, and serves the three packaged static files on GET. Respond with `Cache-Control: no-store` and no CORS header. Add `main()` CLI and `sf-express-smoke` entry point.
- [ ] **Step 4: Run** the focused tests and full suite; expect pass. Commit the API server and tests.

## Task 2: Visual page

- [ ] **Step 1: Create** `web/index.html` with two sections: create order form and tracking form. Include status badge, confirmation dialog, error/result panel, timeline container, and a collapsible JSON response. Fields match the `CreateOrderInput` and `TrackInput` models.
- [ ] **Step 2: Create** `web/style.css` with a responsive layout, clear sandbox indication, and compact event timeline. Avoid third-party fonts or scripts.
- [ ] **Step 3: Create** `web/app.js` that fetches `/api/status`, builds typed JSON from form fields, shows a human-readable order summary before POST, handles both API responses, and renders server text with `textContent` rather than `innerHTML`. It must not persist inputs.
- [ ] **Step 4: Run** the server locally; inspect the page in a browser at `http://127.0.0.1:8765/`, submit an invalid order and a tracking query with no credentials, and confirm the page shows safe errors. Commit the page assets.

## Task 3: Documentation and verification

- [ ] **Step 1: Update** `README.md` with `.\.venv\Scripts\python.exe -m sf_express_mcp.smoke_web`, loopback URL, sandbox-only behavior, and how to stop the process. Add the package-data configuration to `pyproject.toml` if needed for installation.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe -m compileall -q src`, and `git diff --check`. Check `git status --short` and verify no credentials or personal data are committed.
- [ ] **Step 3: Commit** documentation and verification updates. Leave the local server running only if the user can use the page at the stated URL.

## Self-review

The tests and page cover both user actions, config status, sandbox gating, input errors, same-origin JSON requests, and result display. The web server reuses the existing SF client and never stores or returns credentials.
