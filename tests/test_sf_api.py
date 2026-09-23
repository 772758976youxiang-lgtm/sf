import base64
import asyncio
import hashlib
import json
from urllib.parse import quote_plus
from urllib.parse import parse_qs

import httpx
import pytest

from sf_express_mcp.sf_api import SfApiClient, SfApiError, SfTransportError, digest


def test_digest_matches_official_sdk_rule():
    value = '{"orderId":"A 1"}'
    expected = base64.b64encode(
        hashlib.md5(quote_plus(value + "123" + "secret").encode()).digest()
    ).decode()
    assert digest(value, "123", "secret") == expected


def test_simple_digest_signs_raw_utf8_without_url_encoding():
    value = '{"name":"护肤品 1"}'
    expected = base64.b64encode(hashlib.md5((value + "123" + "secret").encode("utf-8")).digest()).decode("ascii")
    assert digest(value, "123", "secret", sign_mode="simple") == expected
    assert digest(value, "123", "secret", sign_mode="standard") != expected


def test_call_posts_signed_form_and_decodes_two_response_layers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({key: values[0] for key, values in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, json={
            "apiResultCode": "A1000",
            "apiResultData": json.dumps({"success": True, "msgData": {"orderId": "O1"}}),
        })

    client = SfApiClient("partner", "secret", "https://example.test/std/service", transport=httpx.MockTransport(handler))
    result = asyncio.run(client.call("EXP_RECE_CREATE_ORDER", {"orderId": "O1"}))
    assert result == {"orderId": "O1"}
    assert seen["partnerID"] == "partner"
    assert seen["serviceCode"] == "EXP_RECE_CREATE_ORDER"
    assert json.loads(seen["msgData"]) == {"orderId": "O1"}
    assert seen["msgDigest"] == digest(seen["msgData"], seen["timestamp"], "secret")
    assert seen["requestID"]


def test_call_uses_selected_simple_signature():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({key: values[0] for key, values in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, json={"apiResultCode": "A1000", "apiResultData": json.dumps({"success": True, "msgData": {}})})

    client = SfApiClient("partner", "secret", "https://example.test/std/service", sign_mode="simple", transport=httpx.MockTransport(handler))
    asyncio.run(client.call("EXP_RECE_SEARCH_ROUTES", {"language": "zh-CN"}))
    assert seen["msgDigest"] == digest(seen["msgData"], seen["timestamp"], "secret", sign_mode="simple")


def test_call_decodes_msg_data_when_it_is_a_json_string():
    response = {
        "apiResultCode": "A1000",
        "apiResultData": json.dumps({"success": True, "msgData": '{"routeResps":[]}'}),
    }
    client = SfApiClient("partner", "secret", "https://example.test/std/service", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)))
    assert asyncio.run(client.call("EXP_RECE_SEARCH_ROUTES", {})) == {"routeResps": []}


@pytest.mark.parametrize("response,kind,code", [
    ({"apiResultCode": "A1006", "apiErrorMsg": "bad signature"}, "platform", "A1006"),
    ({"apiResultCode": "A1000", "apiResultData": '{"success":false,"errorCode":"8016","errorMsg":"duplicate"}'}, "business", "8016"),
])
def test_call_rejects_platform_and_business_failures(response, kind, code):
    client = SfApiClient("partner", "secret", "https://example.test/std/service", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)))
    with pytest.raises(SfApiError) as caught:
        asyncio.run(client.call("EXP_RECE_CREATE_ORDER", {"orderId": "O1"}))
    assert caught.value.kind == kind
    assert caught.value.code == code


def test_http_server_error_has_uncertain_outcome():
    client = SfApiClient("partner", "secret", "https://example.test/std/service", transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(SfTransportError):
        asyncio.run(client.call("EXP_RECE_CREATE_ORDER", {"orderId": "O1"}))
