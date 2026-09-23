from contextlib import contextmanager
from threading import Thread

import httpx
import pytest

from sf_express_mcp.models import CreateOrderInput, TrackInput
from sf_express_mcp.order_map import OrderMap
from sf_express_mcp.sf_api import SfApiError
from sf_express_mcp.smoke_web import make_server


@pytest.fixture(autouse=True)
def isolated_order_map(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ORDER_MAP_PATH", str(tmp_path / "order-map.sqlite3"))


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
    monkeypatch.delenv("SF_SIGN_MODE", raising=False)
    with local_server() as url:
        response = httpx.get(f"{url}/api/status")
    assert response.status_code == 200
    assert response.json() == {"environment": "sandbox", "credentials_configured": True, "sign_mode": "standard"}
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
    assert 'id="credentialsForm"' in home.text
    assert '<input name="order_id" id="orderId" type="hidden">' in home.text
    assert '客户订单号 <span class="required">' not in home.text


def test_web_credentials_are_used_without_exposing_them(monkeypatch):
    monkeypatch.delenv("SF_PARTNER_ID", raising=False)
    monkeypatch.delenv("SF_CHECK_WORD", raising=False)
    monkeypatch.setenv("SF_ENV", "sandbox")
    seen = {}

    async def fake_track(client, query):
        seen["partner_id"] = client.partner_id
        seen["checkword"] = client.checkword
        seen["sign_mode"] = client.sign_mode
        return {"status": "no_events", "events": [], "latest": None}

    monkeypatch.setattr("sf_express_mcp.smoke_web.track_shipment", fake_track)
    with local_server() as url:
        saved = httpx.post(f"{url}/api/config", json={"partner_id": "private-partner", "checkword": "private-secret", "sign_mode": "simple"})
        status = httpx.get(f"{url}/api/status")
        tracked = httpx.post(f"{url}/api/track", json={"tracking_type": "waybill", "tracking_number": "SF123"})
        cleared = httpx.post(f"{url}/api/config", json={"action": "clear"})
        after_clear = httpx.get(f"{url}/api/status")
    assert saved.status_code == 200
    assert status.json()["credentials_configured"] is True
    assert status.json()["sign_mode"] == "simple"
    assert tracked.status_code == 200
    assert seen == {"partner_id": "private-partner", "checkword": "private-secret", "sign_mode": "simple"}
    assert cleared.status_code == 200
    assert after_clear.json()["credentials_configured"] is False
    for response in (saved, status, cleared, after_clear):
        assert "private-partner" not in response.text
        assert "private-secret" not in response.text


def test_invalid_web_credentials_do_not_replace_saved_pair(monkeypatch):
    monkeypatch.delenv("SF_PARTNER_ID", raising=False)
    monkeypatch.delenv("SF_CHECK_WORD", raising=False)
    with local_server() as url:
        saved = httpx.post(f"{url}/api/config", json={"partner_id": "partner", "checkword": "secret"})
        rejected = httpx.post(f"{url}/api/config", json={"partner_id": "", "checkword": "replacement-secret"})
        status = httpx.get(f"{url}/api/status")
    assert saved.status_code == 200
    assert rejected.status_code == 400
    assert status.json()["credentials_configured"] is True
    assert "replacement-secret" not in rejected.text


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


def test_order_mapping_survives_web_server_restart(monkeypatch):
    monkeypatch.setenv("SF_ENV", "sandbox")
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")

    async def fake_create(client, order):
        return {"status": "created", "order_id": order.order_id, "waybill_numbers": ["SF123"]}

    async def fake_track(client, query):
        return {"status": "no_events", "events": [], "latest": None, "tracking_number": query.tracking_number}

    monkeypatch.setattr("sf_express_mcp.smoke_web.create_order", fake_create)
    monkeypatch.setattr("sf_express_mcp.smoke_web.track_shipment", fake_track)
    order = {
        "order_id": "ORDER-1",
        "sender": {"name": "A", "mobile": "13800000000", "province": "广东省", "city": "深圳市", "address": "测试路1号"},
        "recipient": {"name": "B", "mobile": "13900000000", "province": "上海市", "city": "上海市", "address": "测试路2号"},
        "cargo": [{"name": "文件"}],
    }
    with local_server() as url:
        created = httpx.post(f"{url}/api/order", json=order)
    with local_server() as url:
        tracked = httpx.post(f"{url}/api/track", json={"tracking_type": "waybill", "tracking_number": "SF123"})
    assert created.status_code == 200
    assert created.json()["mapping_saved"] is True
    assert tracked.status_code == 200
    assert tracked.json()["order_id"] == "ORDER-1"


def test_saved_order_id_is_returned_even_if_sf_tracking_fails(monkeypatch):
    monkeypatch.setenv("SF_ENV", "sandbox")
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    OrderMap().save("sandbox", "partner", "ORDER-1", ["SF123"])

    async def fake_track(client, query):
        raise SfApiError("platform", "A1004", "not permitted")

    monkeypatch.setattr("sf_express_mcp.smoke_web.track_shipment", fake_track)
    with local_server() as url:
        response = httpx.post(f"{url}/api/track", json={"tracking_type": "waybill", "tracking_number": "SF123"})
    assert response.status_code == 502
    assert response.json()["order_id"] == "ORDER-1"


def test_cross_origin_json_post_is_rejected():
    with local_server() as url:
        response = httpx.post(
            f"{url}/api/track",
            json={"tracking_type": "waybill", "tracking_number": "SF123"},
            headers={"Origin": "https://other.example"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_DENIED"


@pytest.mark.parametrize("code,expected", [
    ("A1006", "数字签名无效"),
    ("A1004", "路由查询接口权限"),
])
def test_platform_errors_show_actionable_message_without_secret(monkeypatch, code, expected):
    monkeypatch.setenv("SF_PARTNER_ID", "private-partner")
    monkeypatch.setenv("SF_CHECK_WORD", "private-secret")
    monkeypatch.setenv("SF_ENV", "sandbox")

    async def fake_track(client, query):
        raise SfApiError("platform", code, "private-secret")

    monkeypatch.setattr("sf_express_mcp.smoke_web.track_shipment", fake_track)
    with local_server() as url:
        response = httpx.post(f"{url}/api/track", json={"tracking_type": "waybill", "tracking_number": "SF123"})
    assert response.status_code == 502
    assert expected in response.json()["error"]["message"]
    assert "private-secret" not in response.text


@pytest.mark.parametrize("path", ["/api/order", "/api/track"])
def test_api_requires_json_content_type(path):
    with local_server() as url:
        response = httpx.post(f"{url}{path}", content="x=1", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 415
