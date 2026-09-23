"""One-shot JSON bridge for the DeepSeek Harness native tools.

Secrets arrive only on stdin and never appear in command-line arguments.
"""

import asyncio
import json
import sys
import uuid

from pydantic import ValidationError

from .config import Config
from .models import CancelOrderInput, CreateOrderInput, TrackInput
from .order_map import find_order_id, remember_created_order
from .service import cancel_order, create_order, track_shipment
from .sf_api import SfApiClient, SfApiError


MAX_INPUT_BYTES = 128 * 1024


def _client(config: Config) -> SfApiClient:
    return SfApiClient(config.partner_id, config.checkword, config.endpoint,
                       timeout=config.timeout, sign_mode=config.sign_mode)


async def run_request(request: dict) -> dict:
    try:
        for key in ("partner_id", "checkword", "environment", "sign_mode"):
            if not isinstance(request.get(key), str) or not request[key].strip():
                raise ValueError("Explicit DSH configuration is required")
        config = Config.from_env(
            partner_id=request.get("partner_id"),
            checkword=request.get("checkword"),
            environment=request.get("environment"),
            sign_mode=request.get("sign_mode"),
            allow_production_orders=True,
        )
        operation = request.get("operation")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        client = _client(config)
        if operation == "create":
            order = CreateOrderInput.model_validate({
                **payload,
                "order_id": payload.get("order_id") or f"DSH-{uuid.uuid4().hex[:24]}",
            })
            return remember_created_order(config, await create_order(client, order))
        if operation == "track":
            query = TrackInput.model_validate(payload)
            order_id = find_order_id(config, query.tracking_type, query.tracking_number)
            result = await track_shipment(client, query)
            if order_id:
                result["order_id"] = order_id
            return result
        if operation == "cancel":
            order_id = payload.get("order_id")
            waybill = payload.get("waybill_number")
            if bool(order_id) == bool(waybill):
                raise ValueError("provide exactly one of order_id or waybill_number")
            if waybill:
                order_id = find_order_id(config, "waybill", str(waybill))
                if not order_id:
                    return {"status": "error", "error": {"kind": "local", "code": "ORDER_ID_NOT_FOUND",
                            "message": "No customer order ID saved for this waybill; provide the original order ID"}}
            return await cancel_order(client, CancelOrderInput(order_id=order_id))
        raise ValueError("operation must be create, track, or cancel")
    except (ValidationError, ValueError):
        return {"status": "error", "error": {"kind": "input", "code": "INVALID_INPUT",
                "message": "Check the operation, selected environment, credentials and input fields"}}
    except SfApiError as exc:
        return {"status": "error", "error": {"kind": exc.kind, "code": exc.code,
                "message": "SF request failed; check the error code"}}


def main() -> None:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        result = {"status": "error", "error": {"kind": "input", "code": "INPUT_TOO_LARGE", "message": "Request is too large"}}
    else:
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError("JSON root must be an object")
            result = asyncio.run(run_request(request))
        except (ValueError, UnicodeDecodeError):
            result = {"status": "error", "error": {"kind": "input", "code": "INVALID_JSON", "message": "Send a JSON object"}}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
