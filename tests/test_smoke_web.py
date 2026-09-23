from contextlib import contextmanager
from threading import Thread

import httpx
import pytest

from sf_express_mcp.models import CreateOrderInput, TrackInput
from sf_express_mcp.smoke_web import make_server


@contextmanager
def local_server():
    server = make_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_status_exposes_no_credentials(monkeypatch):
    monkeypatch.setenv("SF_PARTNER_ID", "private-partner")
    monkeypatch.setenv("SF_CHECK_WORD", "private-secret")
    monkeypatch.setenv("SF_ENV", "sandbox")
    with local_server() as url:
        response = httpx.get(f"{url}/api/status")
    assert response.status_code == 200
    assert response.json() == {"environment": "sandbox", "credentials_configured": True}
    assert "private-secret" not in response.text
    assert "private-partner" not in response.text


def test_home_and_assets_are_served_without_cache():
    with local_server() as url:
        home = httpx.get(f"{url}/")
        css = httpx.get(f"{url}/style.css")
        script = httpx.get(f"{url}/app.js")
    assert home.status_code == 200
    assert "顺丰" in home.text
    assert home.headers["Cache-Control"] == "no-store"
    assert css.status_code == 200
    assert script.status_code == 200


def test_bad_json_returns_400():
    with local_server() as url:
        response = httpx.post(f"{url}/api/track", content="{bad", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"


def test_missing_credentials_return_localized_configuration_error(monkeypatch):
    monkeypatch.delenv("SF_PARTNER_ID", raising=False)
    monkeypatch.delenv("SF_CHECK_WORD", raising=False)
    with local_server() as url:
        response = httpx.post(f"{url}/api/track", json={"tracking_type": "waybill", "tracking_number": "SF123"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INVALID_CONFIG"
    assert "本机配置" in response.json()["error"]["message"]


def test_production_order_is_blocked_before_sf_call(monkeypatch):
    monkeypatch.setenv("SF_ENV", "production")
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.setenv("SF_ALLOW_PRODUCTION_ORDERS", "true")
    with local_server() as url:
        response = httpx.post(f"{url}/api/order", json={})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SANDBOX_ONLY"


def test_tracking_delegates_validated_input(monkeypatch):
    monkeypatch.setenv("SF_ENV", "sandbox")
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    seen = {}

    async def fake_track(client, query):
        seen["query"] = query
        return {"status": "no_events", "events": [], "latest": None}

    monkeypatch.setattr("sf_express_mcp.smoke_web.track_shipment", fake_track)
    with local_server() as url:
        response = httpx.post(f"{url}/api/track", json={"tracking_type": "order", "tracking_number": "ORDER-1"})
    assert response.status_code == 200
    assert seen["query"] == TrackInput(tracking_type="order", tracking_number="ORDER-1")
    assert response.json()["status"] == "no_events"


def test_sandbox_order_delegates_validated_input(monkeypatch):
    monkeypatch.setenv("SF_ENV", "sandbox")
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    seen = {}

    async def fake_create(client, order):
        seen["order"] = order
        return {"status": "created", "order_id": order.order_id, "waybill_numbers": ["SF123"]}

    monkeypatch.setattr("sf_express_mcp.smoke_web.create_order", fake_create)
    order = {
        "order_id": "ORDER-1",
        "sender": {"name": "A", "mobile": "13800000000", "province": "广东省", "city": "深圳市", "address": "测试路1号"},
        "recipient": {"name": "B", "mobile": "13900000000", "province": "上海市", "city": "上海市", "address": "测试路2号"},
        "cargo": [{"name": "文件"}],
    }
    with local_server() as url:
        response = httpx.post(f"{url}/api/order", json=order)
    assert response.status_code == 200
    assert isinstance(seen["order"], CreateOrderInput)
    assert seen["order"].order_id == "ORDER-1"
    assert response.json()["waybill_numbers"] == ["SF123"]


def test_cross_origin_json_post_is_rejected():
    with local_server() as url:
        response = httpx.post(
            f"{url}/api/track",
            json={"tracking_type": "waybill", "tracking_number": "SF123"},
            headers={"Origin": "https://other.example"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_DENIED"


@pytest.mark.parametrize("path", ["/api/order", "/api/track"])
def test_api_requires_json_content_type(path):
    with local_server() as url:
        response = httpx.post(f"{url}{path}", content="x=1", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 415
