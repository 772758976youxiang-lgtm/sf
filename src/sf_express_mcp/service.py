"""Order and tracking workflows independent of the MCP transport."""

from datetime import datetime, timezone

from .models import CreateOrderInput, TrackInput
from .sf_api import SfApiError, SfTransportError


def _waybills(data: dict) -> list[str]:
    items = data.get("waybillNoInfoList") or []
    return [str(item["waybillNo"]) for item in items if isinstance(item, dict) and item.get("waybillNo")]


def _order_result(order_id: str, data: dict) -> dict:
    return {"status": "created", "order_id": str(data.get("orderId") or order_id), "waybill_numbers": _waybills(data)}


async def create_order(client, order: CreateOrderInput) -> dict:
    def contact_payload(contact, kind: int) -> dict:
        result = {
            "contactType": kind,
            "contact": contact.name,
            "mobile": contact.mobile,
            "country": "CN",
            "province": contact.province,
            "city": contact.city,
            "address": contact.address,
        }
        if contact.county:
            result["county"] = contact.county
        return result

    payload = {
        "language": "zh-CN",
        "orderId": order.order_id,
        "contactInfoList": [contact_payload(order.sender, 1), contact_payload(order.recipient, 2)],
        "cargoDetails": [
            {key: value for key, value in {"name": cargo.name, "count": cargo.count, "weight": cargo.weight_kg}.items() if value is not None}
            for cargo in order.cargo
        ],
        "parcelQty": order.parcel_qty,
        "payMethod": order.pay_method,
        "isDocall": 1 if order.request_pickup else 0,
    }
    optional = {
        "totalWeight": order.total_weight_kg,
        "expressTypeId": order.express_type_id,
        "monthlyCard": order.monthly_card,
        "sendStartTm": order.pickup_time,
        "remark": order.remark,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    try:
        result = await client.call("EXP_RECE_CREATE_ORDER", payload)
    except SfApiError as exc:
        if not isinstance(exc, SfTransportError) and not (exc.kind == "business" and exc.code == "8016"):
            raise
        try:
            result = await client.call("EXP_RECE_SEARCH_ORDER_RESP", {"orderId": order.order_id})
        except SfApiError:
            return {"status": "outcome_unknown", "order_id": order.order_id, "waybill_numbers": []}
    return _order_result(order.order_id, result)


async def track_shipment(client, query: TrackInput) -> dict:
    payload = {
        "trackingType": 1 if query.tracking_type == "waybill" else 2,
        "trackingNumber": [query.tracking_number],
        "methodType": 1,
    }
    result = await client.call("EXP_RECE_SEARCH_ROUTES", payload)
    route_resps = result.get("routeResps") or []
    first = route_resps[0] if route_resps and isinstance(route_resps[0], dict) else {}
    events = [
        {
            "time": str(node.get("acceptTime", "")),
            "address": str(node.get("acceptAddress", "")),
            "remark": str(node.get("remark", "")),
            "opcode": str(node.get("opcode", "")),
        }
        for node in (first.get("routes") or [])
        if isinstance(node, dict)
    ]
    events.sort(key=lambda item: item["time"])
    return {
        "status": "ok" if events else "no_events",
        "tracking_type": query.tracking_type,
        "tracking_number": query.tracking_number,
        "waybill_number": first.get("mailNo"),
        "latest": events[-1] if events else None,
        "events": events,
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }
