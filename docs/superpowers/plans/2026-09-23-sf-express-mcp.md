# SF Express MCP Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable Python MCP stdio server with safe order creation and shipment tracking tools for the SF Express standard API.

**Architecture:** A small API client owns signing and HTTP transport. Pydantic input models validate the two public tool contracts. The MCP server maps the models to API calls and returns structured, sanitized results. No credentials or live order data are stored.

**Tech Stack:** Python 3.11, MCP Python SDK 2.x, Pydantic 2, httpx, pytest.

---

## File map

- `pyproject.toml`: runtime and test dependencies, console entry point.
- `src/sf_express_mcp/config.py`: environment configuration and production gate.
- `src/sf_express_mcp/models.py`: order and tracking input schemas.
- `src/sf_express_mcp/sf_api.py`: signature, HTTP request, layered response decoding.
- `src/sf_express_mcp/service.py`: order and tracking workflows, timeout reconciliation, output mapping.
- `src/sf_express_mcp/server.py`: MCP v2 tool registration and stdio launch.
- `tests/test_sf_api.py`, `tests/test_service.py`, `tests/test_server.py`: focused behavioral tests.
- `.env.example`, `.gitignore`, `README.md`: safe configuration and use.

## Task 1: Package and signed transport

- [ ] **Step 1: Write a failing signature test** in `tests/test_sf_api.py`:

```python
import base64
import hashlib
from urllib.parse import quote_plus
from sf_express_mcp.sf_api import digest

def test_digest_matches_official_sdk_rule():
    value = '{"orderId":"A 1"}'
    expected = base64.b64encode(hashlib.md5(quote_plus(value + "123" + "secret").encode()).digest()).decode()
    assert digest(value, "123", "secret") == expected
```

- [ ] **Step 2: Run** `python -m pytest tests/test_sf_api.py -q`; expect import failure.
- [ ] **Step 3: Create** `pyproject.toml` with `mcp>=2,<3`, `httpx>=0.27,<1`, `pydantic>=2,<3`, and pytest test extra; create `src/sf_express_mcp/__init__.py`; implement `digest(msg_data: str, timestamp: str, checkword: str) -> str` using UTF-8 `quote_plus`, MD5 bytes, then Base64. Implement `SfApiClient.call(service_code, payload)` with JSON serialized once, unique `requestID`, seconds timestamp, form POST to configured `/std/service` endpoint, timeout, and a distinct exception for transport failure. Parse outer `apiResultCode == "A1000"` and nested `apiResultData.success is True`; preserve sanitized code and message on failures.
- [ ] **Step 4: Add mock transport tests** for exact form fields, double-layer success, platform error, and business error; run `python -m pytest tests/test_sf_api.py -q`, expect all pass.
- [ ] **Step 5: Commit** `git add pyproject.toml src/sf_express_mcp tests/test_sf_api.py && git commit -m "feat: add SF API signed client"` (PowerShell can run these as separate commands).

## Task 2: Validated tool inputs and business workflows

- [ ] **Step 1: Write failing tests** in `tests/test_service.py`:

```python
import pytest
from sf_express_mcp.models import Contact, CreateOrderInput, Cargo

def test_order_requires_sender_recipient_and_cargo():
    with pytest.raises(ValueError):
        CreateOrderInput(order_id="A1", sender=Contact(name="A", mobile="13800000000", address="深圳"), recipient=Contact(name="B", mobile="13900000000", address="上海"), cargo=[])

def test_contact_rejects_blank_address():
    with pytest.raises(ValueError):
        Contact(name="A", mobile="13800000000", address=" ")
```

- [ ] **Step 2: Run** `python -m pytest tests/test_service.py -q`; expect import failure.
- [ ] **Step 3: Implement** `Contact`, `Cargo`, `CreateOrderInput`, and `TrackInput` in `models.py` with trimmed non-empty values, `order_id` maximum 64 characters, `cargo` at least one item, `tracking_type` limited to `waybill | order`, and one non-empty tracking number. In `service.py`, implement `create_order(client, input)` to map contact types `1` and `2`, call `EXP_RECE_CREATE_ORDER`, return order ID and waybill list; on uncertain transport failure call `EXP_RECE_SEARCH_ORDER_RESP` by the same order ID and return `outcome_unknown` if unresolved. Implement `track_shipment(client, input)` to call `EXP_RECE_SEARCH_ROUTES` with tracking type `1` or `2`, `trackingNumber: [value]`, `methodType: 1`, and normalize/sort route nodes.
- [ ] **Step 4: Add mock client tests** for order payload, successful waybill mapping, no duplicate create after timeout, route sort, and empty routes; run `python -m pytest tests/test_service.py -q`, expect all pass.
- [ ] **Step 5: Commit** `git add src/sf_express_mcp/models.py src/sf_express_mcp/service.py tests/test_service.py && git commit -m "feat: add order and tracking workflows"`.

## Task 3: MCP wiring and configuration

- [ ] **Step 1: Write a failing test** in `tests/test_server.py` that imports `mcp` from `sf_express_mcp.server` and checks its registered tool names are exactly `sf_create_order` and `sf_track_shipment`.
- [ ] **Step 2: Run** `python -m pytest tests/test_server.py -q`; expect import failure.
- [ ] **Step 3: Implement** `config.py` with `SF_PARTNER_ID`, `SF_CHECK_WORD`, `SF_ENV` default `sandbox`, `SF_HTTP_TIMEOUT`, and `SF_ALLOW_PRODUCTION_ORDERS` default false. Reject production order calls unless the gate is true. In `server.py`, create `MCPServer("SF Express")`; decorate two async functions with `@mcp.tool()`; give the order tool an explicit side-effect docstring and the tracking tool a read-only annotation. Launch via `mcp.run(transport="stdio")` only inside `if __name__ == "__main__"`. Keep SDK/model imports side-effect free and defer secret validation until a tool call so `tools/list` works without credentials.
- [ ] **Step 4: Run** `python -m pytest tests/test_server.py -q` and `python -m pytest -q`; expect all pass. Verify an MCP client can list two tools over stdio without credentials.
- [ ] **Step 5: Commit** `git add src/sf_express_mcp/config.py src/sf_express_mcp/server.py tests/test_server.py && git commit -m "feat: expose SF workflows as MCP tools"`.

## Task 4: Operator documentation and final verification

- [ ] **Step 1: Add** `.gitignore` for `.venv`, `__pycache__`, `.pytest_cache`, and `.env`; `.env.example` with placeholder values only; `README.md` with Python install, environment setup, stdio MCP client JSON, sample tool inputs, production confirmation requirement, and exact sandbox smoke-test steps.
- [ ] **Step 2: Run** `python -m pytest -q`, `python -m compileall -q src`, and `git diff --check`; expect all pass.
- [ ] **Step 3: Inspect** `git status --short` and search tracked files for credential-like values; no live credentials should be tracked.
- [ ] **Step 4: Commit** `git add .gitignore .env.example README.md && git commit -m "docs: explain SF MCP setup and safety"`.

## Self-review

- Spec coverage: both tools, signing, sandbox default, production gate, timeout reconciliation, privacy, tests, and documentation are assigned above.
- Names and types are consistent across the file map and tasks.
- No live SF request is possible until the operator supplies credentials; current account documentation must be checked before production use.
