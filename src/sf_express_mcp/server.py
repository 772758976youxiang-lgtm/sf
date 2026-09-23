"""MCP stdio server exposing SF Express order and tracking tools."""

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .config import Config
from .models import CancelOrderInput, CreateOrderInput, TrackInput
from .order_map import find_order_id, remember_created_order
from .service import cancel_order, create_order, track_shipment
from .sf_api import SfApiClient, SfApiError


mcp = MCPServer("SF Express")


def _client(config: Config) -> SfApiClient:
    return SfApiClient(config.partner_id, config.checkword, config.endpoint, timeout=config.timeout, sign_mode=config.sign_mode)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=False, open_world_hint=True))
async def sf_create_order(order: CreateOrderInput) -> dict:
    """Create an SF Express shipment. This may request a courier and incur charges. Show the full order summary and obtain the user's confirmation before calling. Use a stable, unique order_id; an uncertain result must not be retried blindly."""
    try:
        config = Config.from_env()
        if not config.can_create_order:
            return {"status": "error", "error": {"kind": "configuration", "code": "PRODUCTION_DISABLED", "message": "Set SF_ALLOW_PRODUCTION_ORDERS=true to enable production orders"}}
        return remember_created_order(config, await create_order(_client(config), order))
    except (SfApiError, ValueError) as exc:
        if isinstance(exc, SfApiError):
            error = {"kind": exc.kind, "code": exc.code, "message": "SF request failed; check the error code"}
        else:
            error = {"kind": "configuration", "code": "INVALID_CONFIG", "message": str(exc)}
        return {"status": "error", "error": error}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def sf_track_shipment(query: TrackInput) -> dict:
    """Get SF Express shipment route events by waybill number or by your own customer order ID. Results are limited to shipments owned by the configured SF account."""
    order_id = None
    try:
        config = Config.from_env()
        order_id = find_order_id(config, query.tracking_type, query.tracking_number)
        result = await track_shipment(_client(config), query)
        if order_id:
            result["order_id"] = order_id
        return result
    except (SfApiError, ValueError) as exc:
        if isinstance(exc, SfApiError):
            error = {"kind": exc.kind, "code": exc.code, "message": "SF request failed; check the error code"}
        else:
            error = {"kind": "configuration", "code": "INVALID_CONFIG", "message": str(exc)}
        result = {"status": "error", "error": error}
        if order_id:
            result["order_id"] = order_id
        return result


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=False, open_world_hint=True))
async def sf_cancel_order(request: CancelOrderInput) -> dict:
    """Cancel an existing SF order by customer order ID. Show the order ID and obtain the user's confirmation first. A transport failure has an unknown outcome; do not retry automatically."""
    try:
        config = Config.from_env()
        if config.environment == "production" and not config.can_create_order:
            return {"status": "error", "error": {"kind": "configuration", "code": "PRODUCTION_DISABLED", "message": "Set SF_ALLOW_PRODUCTION_ORDERS=true to enable production cancellation"}}
        return await cancel_order(_client(config), request)
    except (SfApiError, ValueError) as exc:
        if isinstance(exc, SfApiError):
            error = {"kind": exc.kind, "code": exc.code, "message": "SF request failed; check the error code"}
        else:
            error = {"kind": "configuration", "code": "INVALID_CONFIG", "message": str(exc)}
        return {"status": "error", "error": error}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
