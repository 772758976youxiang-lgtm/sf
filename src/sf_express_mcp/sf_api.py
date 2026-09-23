"""Signing and transport for SF Express's standard API."""

import base64
import hashlib
import json
import time
import uuid
from urllib.parse import quote_plus

import httpx


class SfApiError(Exception):
    def __init__(self, kind: str, code: str, message: str):
        self.kind = kind
        self.code = code
        self.message = message
        super().__init__(f"{kind} {code}: {message}")


class SfTransportError(SfApiError):
    def __init__(self, message: str):
        super().__init__("transport", "NETWORK_ERROR", message)


def digest(msg_data: str, timestamp: str, checkword: str, *, sign_mode: str = "standard") -> str:
    source = msg_data + timestamp + checkword
    if sign_mode == "standard":
        source = quote_plus(source)
    elif sign_mode != "simple":
        raise ValueError("SF_SIGN_MODE must be standard or simple")
    encoded = source.encode("utf-8")
    return base64.b64encode(hashlib.md5(encoded).digest()).decode("ascii")


class SfApiClient:
    def __init__(
        self,
        partner_id: str,
        checkword: str,
        endpoint: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sign_mode: str = "standard",
    ):
        self.partner_id = partner_id
        self.checkword = checkword
        self.endpoint = endpoint
        self.timeout = timeout
        self.transport = transport
        self.sign_mode = sign_mode

    async def call(self, service_code: str, payload: dict) -> dict:
        msg_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = str(int(time.time()))
        form = {
            "partnerID": self.partner_id,
            "requestID": str(uuid.uuid4()),
            "serviceCode": service_code,
            "timestamp": timestamp,
            "msgData": msg_data,
            "msgDigest": digest(msg_data, timestamp, self.checkword, sign_mode=self.sign_mode),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(self.endpoint, data=form)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise SfTransportError(f"HTTP {exc.response.status_code}") from exc
            raise SfApiError("http", str(exc.response.status_code), "SF HTTP request failed") from exc
        except httpx.RequestError as exc:
            raise SfTransportError(type(exc).__name__) from exc
        try:
            outer = response.json()
            if not isinstance(outer, dict):
                raise ValueError("outer response is not an object")
            if outer.get("apiResultCode") != "A1000":
                raise SfApiError("platform", str(outer.get("apiResultCode", "UNKNOWN")), str(outer.get("apiErrorMsg", "SF platform rejected request")))
            inner = outer.get("apiResultData")
            if isinstance(inner, str):
                inner = json.loads(inner)
            if not isinstance(inner, dict):
                raise ValueError("business response is not an object")
            if inner.get("success") is not True:
                raise SfApiError("business", str(inner.get("errorCode", "UNKNOWN")), str(inner.get("errorMsg", "SF business request failed")))
            result = inner.get("msgData")
            if isinstance(result, str):
                result = json.loads(result)
            return result if isinstance(result, dict) else {"data": result}
        except (ValueError, TypeError) as exc:
            raise SfApiError("protocol", "INVALID_RESPONSE", "SF returned an invalid response") from exc
