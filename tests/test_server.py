import asyncio
import sys

from mcp import Client, StdioServerParameters
import pytest

from sf_express_mcp.config import Config
from sf_express_mcp.models import CreateOrderInput, TrackInput
from sf_express_mcp.server import mcp, sf_create_order, sf_track_shipment
from sf_express_mcp.sf_api import SfApiError


def test_mcp_lists_exactly_two_tools_without_credentials(monkeypatch):
    monkeypatch.delenv("SF_PARTNER_ID", raising=False)
    monkeypatch.delenv("SF_CHECK_WORD", raising=False)

    async def check():
        async with Client(mcp) as client:
            result = await client.list_tools()
            assert {tool.name for tool in result.tools} == {"sf_create_order", "sf_track_shipment"}
            order = next(tool for tool in result.tools if tool.name == "sf_create_order")
            assert order.input_schema["properties"]["order"]

    asyncio.run(check())


def test_stdio_process_lists_two_tools():
    async def check():
        params = StdioServerParameters(command=sys.executable, args=["-m", "sf_express_mcp.server"])
        async with Client(params) as client:
            result = await client.list_tools()
            assert {tool.name for tool in result.tools} == {"sf_create_order", "sf_track_shipment"}

    asyncio.run(check())


def test_config_defaults_to_sandbox(monkeypatch):
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.delenv("SF_ENV", raising=False)
    monkeypatch.delenv("SF_SIGN_MODE", raising=False)
    config = Config.from_env()
    assert config.environment == "sandbox"
    assert config.endpoint == "https://sfapi-sbox.sf-express.com/std/service"
    assert config.sign_mode == "standard"


def test_config_accepts_simple_signature(monkeypatch):
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.setenv("SF_SIGN_MODE", "simple")
    assert Config.from_env().sign_mode == "simple"


def test_production_order_requires_explicit_gate(monkeypatch):
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.setenv("SF_ENV", "production")
    monkeypatch.delenv("SF_ALLOW_PRODUCTION_ORDERS", raising=False)
    config = Config.from_env()
    assert config.can_create_order is False


def test_custom_endpoint_cannot_send_credentials_to_other_domain(monkeypatch):
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.setenv("SF_API_URL", "https://other.example/std/service")
    with pytest.raises(ValueError):
        Config.from_env()


def test_sf_error_does_not_echo_private_details(monkeypatch):
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.delenv("SF_API_URL", raising=False)

    class FailingClient:
        async def call(self, code, payload):
            raise SfApiError("business", "E123", "phone 13800000000 at street 12")

    monkeypatch.setattr("sf_express_mcp.server._client", lambda _: FailingClient())
    result = asyncio.run(sf_track_shipment(TrackInput(tracking_type="waybill", tracking_number="SF123")))
    assert result["error"]["code"] == "E123"
    assert "13800000000" not in str(result)
    assert "street 12" not in str(result)


def test_mcp_order_mapping_is_available_during_tracking(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_PARTNER_ID", "partner")
    monkeypatch.setenv("SF_CHECK_WORD", "secret")
    monkeypatch.setenv("SF_ENV", "sandbox")
    monkeypatch.setenv("SF_ORDER_MAP_PATH", str(tmp_path / "order-map.sqlite3"))

    async def fake_create(client, order):
        return {"status": "created", "order_id": order.order_id, "waybill_numbers": ["SF123"]}

    async def fake_track(client, query):
        return {"status": "no_events", "events": []}

    monkeypatch.setattr("sf_express_mcp.server.create_order", fake_create)
    monkeypatch.setattr("sf_express_mcp.server.track_shipment", fake_track)
    order = CreateOrderInput(
        order_id="ORDER-1",
        sender={"name": "A", "mobile": "13800000000", "province": "广东省", "city": "深圳市", "address": "测试路1号"},
        recipient={"name": "B", "mobile": "13900000000", "province": "上海市", "city": "上海市", "address": "测试路2号"},
        cargo=[{"name": "文件"}],
    )
    created = asyncio.run(sf_create_order(order))
    tracked = asyncio.run(sf_track_shipment(TrackInput(tracking_type="waybill", tracking_number="SF123")))
    assert created["mapping_saved"] is True
    assert tracked["order_id"] == "ORDER-1"
