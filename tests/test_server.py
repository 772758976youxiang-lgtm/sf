import asyncio
import sys

from mcp import Client, StdioServerParameters
import pytest

from sf_express_mcp.config import Config
from sf_express_mcp.models import TrackInput
from sf_express_mcp.server import mcp, sf_track_shipment
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
    config = Config.from_env()
    assert config.environment == "sandbox"
    assert config.endpoint == "https://sfapi-sbox.sf-express.com/std/service"


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
