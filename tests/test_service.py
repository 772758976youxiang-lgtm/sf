import asyncio

import pytest

from sf_express_mcp.models import CancelOrderInput, Cargo, Contact, CreateOrderInput, TrackInput
from sf_express_mcp.service import cancel_order, create_order, track_shipment
from sf_express_mcp.sf_api import SfApiError, SfTransportError


def sample_order():
    return CreateOrderInput(
        order_id="ORDER-1",
        sender=Contact(name="寄件人", mobile="13800000000", province="广东省", city="深圳市", address="福田区一号"),
        recipient=Contact(name="收件人", mobile="13900000000", province="上海市", city="上海市", address="浦东新区二号"),
        cargo=[Cargo(name="文件")],
    )


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def call(self, service_code, payload):
        self.calls.append((service_code, payload))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_order_requires_cargo():
    with pytest.raises(ValueError):
        CreateOrderInput(
            order_id="ORDER-1",
            sender=sample_order().sender,
            recipient=sample_order().recipient,
            cargo=[],
        )


def test_contact_rejects_blank_address():
    with pytest.raises(ValueError):
        Contact(name="A", mobile="13800000000", province="广东省", city="深圳市", address=" ")


def test_create_order_maps_contacts_and_waybill():
    client = FakeClient([{"orderId": "ORDER-1", "waybillNoInfoList": [{"waybillType": 1, "waybillNo": "SF123"}]}])
    result = asyncio.run(create_order(client, sample_order()))
    code, payload = client.calls[0]
    assert code == "EXP_RECE_CREATE_ORDER"
    assert payload["contactInfoList"][0]["contactType"] == 1
    assert payload["contactInfoList"][1]["contactType"] == 2
    assert payload["cargoDetails"] == [{"name": "文件", "count": 1}]
    assert result == {"status": "created", "order_id": "ORDER-1", "waybill_numbers": ["SF123"]}


def test_create_order_reconciles_timeout_without_repeating_create():
    client = FakeClient([SfTransportError("timeout"), {"orderId": "ORDER-1", "waybillNoInfoList": [{"waybillNo": "SF123"}]}])
    result = asyncio.run(create_order(client, sample_order()))
    assert [code for code, _ in client.calls] == ["EXP_RECE_CREATE_ORDER", "EXP_RECE_SEARCH_ORDER_RESP"]
    assert client.calls[1][1] == {"orderId": "ORDER-1"}
    assert result["status"] == "created"


def test_create_order_reports_unknown_when_reconciliation_fails():
    client = FakeClient([SfTransportError("timeout"), SfApiError("business", "NOT_FOUND", "not found")])
    result = asyncio.run(create_order(client, sample_order()))
    assert result == {"status": "outcome_unknown", "order_id": "ORDER-1", "waybill_numbers": []}
    assert len(client.calls) == 2


def test_create_order_resolves_duplicate_by_order_id():
    client = FakeClient([SfApiError("business", "8016", "duplicate"), {"orderId": "ORDER-1", "waybillNoInfoList": [{"waybillNo": "SF123"}]}])
    result = asyncio.run(create_order(client, sample_order()))
    assert result["waybill_numbers"] == ["SF123"]
    assert [code for code, _ in client.calls] == ["EXP_RECE_CREATE_ORDER", "EXP_RECE_SEARCH_ORDER_RESP"]


def test_track_shipment_sorts_route_nodes():
    client = FakeClient([{"routeResps": [{"mailNo": "SF123", "routes": [
        {"acceptTime": "2026-09-23 12:00:00", "remark": "签收", "opcode": "80"},
        {"acceptTime": "2026-09-22 12:00:00", "acceptAddress": "深圳", "remark": "揽收", "opcode": "50"},
    ]}]}])
    result = asyncio.run(track_shipment(client, TrackInput(tracking_type="waybill", tracking_number="SF123")))
    assert client.calls[0] == ("EXP_RECE_SEARCH_ROUTES", {"trackingType": 1, "trackingNumber": ["SF123"], "methodType": 1})
    assert result["latest"]["remark"] == "签收"
    assert [node["remark"] for node in result["events"]] == ["揽收", "签收"]


def test_track_shipment_returns_empty_events():
    client = FakeClient([{"routeResps": [{"mailNo": "SF123", "routes": []}]}])
    result = asyncio.run(track_shipment(client, TrackInput(tracking_type="waybill", tracking_number="SF123")))
    assert result["status"] == "no_events"
    assert result["latest"] is None


def test_cancel_order_uses_update_api_and_requires_success_status():
    client = FakeClient([{"orderId": "ORDER-1", "resStatus": 2}])
    result = asyncio.run(cancel_order(client, CancelOrderInput(order_id=" ORDER-1 ")))
    assert client.calls == [("EXP_RECE_UPDATE_ORDER", {"orderId": "ORDER-1", "dealType": 2})]
    assert result == {"status": "cancelled", "order_id": "ORDER-1"}


def test_cancel_order_reports_unknown_without_retrying():
    client = FakeClient([SfTransportError("timeout")])
    result = asyncio.run(cancel_order(client, CancelOrderInput(order_id="ORDER-1")))
    assert result == {"status": "outcome_unknown", "order_id": "ORDER-1"}
    assert len(client.calls) == 1


def test_cancel_order_does_not_call_success_for_mismatch():
    result = asyncio.run(cancel_order(FakeClient([{"orderId": "ORDER-1", "resStatus": 1}]), CancelOrderInput(order_id="ORDER-1")))
    assert result == {"status": "rejected", "order_id": "ORDER-1", "res_status": 1}


def test_cancel_order_does_not_confirm_ambiguous_response():
    for response in ({}, {"resStatus": 2, "orderId": "OTHER-ORDER"}):
        client = FakeClient([response])
        result = asyncio.run(cancel_order(client, CancelOrderInput(order_id="ORDER-1")))
        assert result == {"status": "outcome_unknown", "order_id": "ORDER-1"}
        assert len(client.calls) == 1
