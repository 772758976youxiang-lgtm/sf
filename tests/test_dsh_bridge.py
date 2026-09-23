import asyncio

from sf_express_mcp.dsh_bridge import run_request
from sf_express_mcp.order_map import OrderMap


def test_dsh_bridge_creates_with_generated_order_id_and_saved_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ORDER_MAP_PATH", str(tmp_path / "map.sqlite3"))
    monkeypatch.delenv("SF_API_URL", raising=False)
    seen = {}

    async def fake_create(client, order):
        seen["endpoint"] = client.endpoint
        seen["order_id"] = order.order_id
        return {"status": "created", "order_id": order.order_id, "waybill_numbers": ["SF123"]}

    monkeypatch.setattr("sf_express_mcp.dsh_bridge.create_order", fake_create)
    result = asyncio.run(run_request({
        "operation": "create", "environment": "sandbox", "sign_mode": "simple",
        "partner_id": "partner", "checkword": "private-secret",
        "payload": {
            "sender": {"name": "A", "mobile": "13800000000", "province": "广东省", "city": "深圳市", "address": "测试路1号"},
            "recipient": {"name": "B", "mobile": "13900000000", "province": "上海市", "city": "上海市", "address": "测试路2号"},
            "cargo": [{"name": "文件"}],
        },
    }))
    assert result["status"] == "created"
    assert result["order_id"].startswith("DSH-")
    assert OrderMap().lookup("sandbox", "partner", "SF123") == result["order_id"]
    assert seen["endpoint"] == "https://sfapi-sbox.sf-express.com/std/service"
    assert "private-secret" not in str(result)


def test_dsh_bridge_cancels_by_waybill_from_saved_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ORDER_MAP_PATH", str(tmp_path / "map.sqlite3"))
    OrderMap().save("sandbox", "partner", "ORDER-1", ["SF123"])
    seen = {}

    async def fake_cancel(client, request):
        seen["order_id"] = request.order_id
        return {"status": "cancelled", "order_id": request.order_id}

    monkeypatch.setattr("sf_express_mcp.dsh_bridge.cancel_order", fake_cancel)
    result = asyncio.run(run_request({"operation": "cancel", "environment": "sandbox", "sign_mode": "simple",
                                      "partner_id": "partner", "checkword": "private-secret",
                                      "payload": {"waybill_number": "SF123"}}))
    assert result == {"status": "cancelled", "order_id": "ORDER-1"}
    assert seen["order_id"] == "ORDER-1"
