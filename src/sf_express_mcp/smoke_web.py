"""Local-only HTTP page for SF smoke testing."""

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import os
from threading import Lock

from pydantic import ValidationError

from .config import Config, ENDPOINTS
from .models import CreateOrderInput, TrackInput
from .order_map import find_order_id, remember_created_order
from .service import create_order, track_shipment
from .sf_api import SfApiClient, SfApiError


MAX_BODY_BYTES = 32 * 1024


def _error(status: int, code: str, message: str, *, fields: list[str] | None = None) -> tuple[int, dict]:
    detail = {"kind": "smoke_web", "code": code, "message": message}
    if fields:
        detail["fields"] = fields
    return status, {"status": "error", "error": detail}


def _sf_error(exc: SfApiError, operation: str, environment: str) -> tuple[int, dict]:
    environment_label = "生产" if environment == "production" else "沙盒"
    if exc.kind == "platform" and exc.code == "A1006":
        message = f"顺丰数字签名无效。请核对{environment_label}顾客编码与校验码是否属于同一应用；若无误，请检查签名配置。"
    elif exc.kind == "platform" and exc.code == "A1004":
        message = f"当前顾客编码没有{operation}接口权限。请在顺丰开放平台的应用 API 列表中关联该接口，并确认使用{environment_label}环境。"
    else:
        message = "顺丰请求失败，请检查错误码"
    return _error(502, exc.code, message)


class SmokeApi:
    def __init__(self) -> None:
        configured = os.getenv("SF_ENV", "sandbox").strip().lower()
        self._environment = configured if configured in ENDPOINTS else "sandbox"
        self._credentials: dict[str, tuple[str, str, str]] = {}
        self._credentials_lock = Lock()

    def _selection(self) -> tuple[str, tuple[str, str, str] | None]:
        with self._credentials_lock:
            return self._environment, self._credentials.get(self._environment)

    def status(self) -> dict:
        environment, saved = self._selection()
        process_environment = os.getenv("SF_ENV", "sandbox").strip().lower()
        inherited = environment == process_environment
        return {
            "environment": environment,
            "credentials_configured": bool(saved or (inherited and os.getenv("SF_PARTNER_ID", "").strip() and os.getenv("SF_CHECK_WORD", "").strip())),
            "sign_mode": saved[2] if saved else os.getenv("SF_SIGN_MODE", "standard").strip().lower() if inherited else "simple",
        }

    def configure(self, payload: dict) -> tuple[int, dict]:
        environment = payload.get("environment")
        if environment is not None and environment not in ENDPOINTS:
            return _error(400, "INVALID_ENVIRONMENT", "请选择沙盒或生产环境")
        if payload.get("action") == "select":
            if environment is None:
                return _error(400, "INVALID_ENVIRONMENT", "请选择沙盒或生产环境")
            with self._credentials_lock:
                self._environment = environment
            return 200, self.status()
        if payload.get("action") == "clear":
            with self._credentials_lock:
                self._credentials.pop(self._environment, None)
            return 200, self.status()
        partner_id = payload.get("partner_id")
        checkword = payload.get("checkword")
        sign_mode = payload.get("sign_mode", "simple")
        if (not isinstance(partner_id, str) or not isinstance(checkword, str)
                or not 1 <= len(partner_id.strip()) <= 128
                or not 1 <= len(checkword.strip()) <= 256
                or sign_mode not in ("standard", "simple")):
            return _error(400, "INVALID_CONFIG", "请输入顾客编码、校验码并选择签名方式")
        with self._credentials_lock:
            selected = environment or self._environment
            self._credentials[selected] = (partner_id.strip(), checkword.strip(), sign_mode)
            self._environment = selected
        return 200, self.status()

    def _config(self) -> Config:
        environment, saved = self._selection()
        if saved:
            return Config.from_env(partner_id=saved[0], checkword=saved[1], sign_mode=saved[2],
                                   environment=environment, allow_production_orders=True)
        if environment != os.getenv("SF_ENV", "sandbox").strip().lower():
            raise ValueError("Credentials are not configured for the selected environment")
        return Config.from_env(environment=environment, allow_production_orders=True)

    @staticmethod
    def _client(config: Config) -> SfApiClient:
        return SfApiClient(config.partner_id, config.checkword, config.endpoint, timeout=config.timeout, sign_mode=config.sign_mode)

    async def order(self, payload: dict) -> tuple[int, dict]:
        environment, _ = self._selection()
        if payload.get("environment") not in (None, environment):
            return _error(409, "ENVIRONMENT_CHANGED", "运行环境已切换，请重新核对订单")
        if environment == "production" and (payload.get("environment") != "production" or payload.get("confirm_production") is not True):
            return _error(403, "PRODUCTION_CONFIRMATION_REQUIRED", "生产下单需要先核对订单并明确确认")
        try:
            order = CreateOrderInput.model_validate(payload)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in item["loc"]) for item in exc.errors(include_input=False, include_context=False)]
            return _error(400, "INVALID_INPUT", "Check the order fields", fields=fields)
        try:
            config = self._config()
            if config.environment != environment:
                return _error(409, "ENVIRONMENT_CHANGED", "运行环境已切换，请重新核对订单")
            return 200, remember_created_order(config, await create_order(self._client(config), order))
        except ValueError:
            return _error(503, "INVALID_CONFIG", "请检查本机配置的顺丰顾客编码、校验码及环境变量")
        except SfApiError as exc:
            return _sf_error(exc, "下订单", environment)

    async def track(self, payload: dict) -> tuple[int, dict]:
        try:
            query = TrackInput.model_validate(payload)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in item["loc"]) for item in exc.errors(include_input=False, include_context=False)]
            return _error(400, "INVALID_INPUT", "Check the tracking fields", fields=fields)
        try:
            config = self._config()
            order_id = find_order_id(config, query.tracking_type, query.tracking_number)
            result = await track_shipment(self._client(config), query)
            if order_id:
                result["order_id"] = order_id
            return 200, result
        except ValueError:
            return _error(503, "INVALID_CONFIG", "请检查本机配置的顺丰顾客编码、校验码及环境变量")
        except SfApiError as exc:
            status, result = _sf_error(exc, "路由查询", config.environment)
            if order_id:
                result["order_id"] = order_id
            return status, result


def make_server(port: int = 8765, api: SmokeApi | None = None) -> ThreadingHTTPServer:
    smoke_api = api or SmokeApi()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/api/status":
                self._json(200, smoke_api.status())
                return
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            }
            if self.path not in assets:
                self._json(*_error(404, "NOT_FOUND", "Page not found"))
                return
            name, content_type = assets[self.path]
            body = files("sf_express_mcp").joinpath("web", name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path not in ("/api/order", "/api/track", "/api/config"):
                self._json(*_error(404, "NOT_FOUND", "Endpoint not found"))
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._json(*_error(415, "JSON_REQUIRED", "Send application/json"))
                return
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{self.server.server_address[1]}"
            if origin and origin != expected_origin:
                self._json(*_error(403, "ORIGIN_DENIED", "Use the local smoke page"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length > MAX_BODY_BYTES:
                self._json(*_error(413, "BODY_TOO_LARGE", "Request body is too large"))
                return
            if length <= 0:
                self._json(*_error(400, "INVALID_JSON", "Send a JSON object"))
                return
            try:
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("JSON root must be an object")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                self._json(*_error(400, "INVALID_JSON", "Send a JSON object"))
                return
            if self.path == "/api/config":
                self._json(*smoke_api.configure(payload))
            else:
                operation = smoke_api.order if self.path == "/api/order" else smoke_api.track
                self._json(*asyncio.run(operation(payload)))

        def log_message(self, format: str, *args) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SF Express localhost smoke page")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with make_server(args.port) as server:
        print(f"SF smoke page: http://127.0.0.1:{args.port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
