"""Local-only HTTP page for sandbox smoke testing."""

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import os

from pydantic import ValidationError

from .config import Config
from .models import CreateOrderInput, TrackInput
from .service import create_order, track_shipment
from .sf_api import SfApiClient, SfApiError


MAX_BODY_BYTES = 32 * 1024


def _error(status: int, code: str, message: str, *, fields: list[str] | None = None) -> tuple[int, dict]:
    detail = {"kind": "smoke_web", "code": code, "message": message}
    if fields:
        detail["fields"] = fields
    return status, {"status": "error", "error": detail}


class SmokeApi:
    def status(self) -> dict:
        return {
            "environment": os.getenv("SF_ENV", "sandbox").strip().lower(),
            "credentials_configured": bool(os.getenv("SF_PARTNER_ID", "").strip() and os.getenv("SF_CHECK_WORD", "").strip()),
        }

    @staticmethod
    def _client(config: Config) -> SfApiClient:
        return SfApiClient(config.partner_id, config.checkword, config.endpoint, timeout=config.timeout)

    async def order(self, payload: dict) -> tuple[int, dict]:
        if os.getenv("SF_ENV", "sandbox").strip().lower() != "sandbox":
            return _error(403, "SANDBOX_ONLY", "The smoke page only creates sandbox orders")
        try:
            order = CreateOrderInput.model_validate(payload)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in item["loc"]) for item in exc.errors(include_input=False, include_context=False)]
            return _error(400, "INVALID_INPUT", "Check the order fields", fields=fields)
        try:
            config = Config.from_env()
            return 200, await create_order(self._client(config), order)
        except ValueError:
            return _error(503, "INVALID_CONFIG", "请检查本机配置的顺丰顾客编码、校验码及环境变量")
        except SfApiError as exc:
            return _error(502, exc.code, "SF request failed; check the error code")

    async def track(self, payload: dict) -> tuple[int, dict]:
        try:
            query = TrackInput.model_validate(payload)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in item["loc"]) for item in exc.errors(include_input=False, include_context=False)]
            return _error(400, "INVALID_INPUT", "Check the tracking fields", fields=fields)
        try:
            config = Config.from_env()
            return 200, await track_shipment(self._client(config), query)
        except ValueError:
            return _error(503, "INVALID_CONFIG", "请检查本机配置的顺丰顾客编码、校验码及环境变量")
        except SfApiError as exc:
            return _error(502, exc.code, "SF request failed; check the error code")


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
            if self.path not in ("/api/order", "/api/track"):
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
