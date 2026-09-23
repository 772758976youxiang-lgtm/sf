"""Runtime configuration for SF Express access."""

from dataclasses import dataclass, field
import os
from urllib.parse import urlparse


ENDPOINTS = {
    "sandbox": "https://sfapi-sbox.sf-express.com/std/service",
    "production": "https://bspgw.sf-express.com/std/service",
}


@dataclass(frozen=True)
class Config:
    partner_id: str = field(repr=False)
    checkword: str = field(repr=False)
    environment: str
    endpoint: str
    timeout: float
    can_create_order: bool
    sign_mode: str

    @classmethod
    def from_env(cls, *, partner_id: str | None = None, checkword: str | None = None,
                 sign_mode: str | None = None, environment: str | None = None,
                 allow_production_orders: bool | None = None) -> "Config":
        partner_id = (partner_id if partner_id is not None else os.getenv("SF_PARTNER_ID", "")).strip()
        checkword = (checkword if checkword is not None else os.getenv("SF_CHECK_WORD", "")).strip()
        if not partner_id or not checkword:
            raise ValueError("Set SF_PARTNER_ID and SF_CHECK_WORD before calling SF tools")
        process_environment = os.getenv("SF_ENV", "sandbox").strip().lower()
        environment = (environment if environment is not None else process_environment).strip().lower()
        if environment not in ENDPOINTS:
            raise ValueError("SF_ENV must be sandbox or production")
        sign_mode = (sign_mode if sign_mode is not None else os.getenv("SF_SIGN_MODE", "standard")).strip().lower()
        if sign_mode not in ("standard", "simple"):
            raise ValueError("SF_SIGN_MODE must be standard or simple")
        timeout = float(os.getenv("SF_HTTP_TIMEOUT", "10"))
        if timeout <= 0:
            raise ValueError("SF_HTTP_TIMEOUT must be positive")
        endpoint_override = os.getenv("SF_API_URL", "").strip() if environment == process_environment else ""
        endpoint = endpoint_override or ENDPOINTS[environment]
        parsed = urlparse(endpoint)
        allowed_hosts = {urlparse(ENDPOINTS[environment]).hostname}
        if environment == "production":
            allowed_hosts.add("sfapi.sf-express.com")  # Older SF integrations use this host.
        if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username
                or parsed.password or parsed.port not in (None, 443)
                or parsed.path != "/std/service" or parsed.query or parsed.fragment):
            raise ValueError("SF_API_URL must use the configured SF environment host over HTTPS")
        allow_production = (os.getenv("SF_ALLOW_PRODUCTION_ORDERS", "").strip().lower() == "true"
                            if allow_production_orders is None else allow_production_orders)
        return cls(
            partner_id=partner_id,
            checkword=checkword,
            environment=environment,
            endpoint=endpoint,
            timeout=timeout,
            can_create_order=environment == "sandbox" or allow_production,
            sign_mode=sign_mode,
        )
