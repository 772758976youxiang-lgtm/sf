"""Runtime configuration for SF Express access."""

from dataclasses import dataclass, field
import os
from urllib.parse import urlparse


ENDPOINTS = {
    "sandbox": "https://sfapi-sbox.sf-express.com/std/service",
    "production": "https://sfapi.sf-express.com/std/service",
}


@dataclass(frozen=True)
class Config:
    partner_id: str = field(repr=False)
    checkword: str = field(repr=False)
    environment: str
    endpoint: str
    timeout: float
    can_create_order: bool

    @classmethod
    def from_env(cls) -> "Config":
        partner_id = os.getenv("SF_PARTNER_ID", "").strip()
        checkword = os.getenv("SF_CHECK_WORD", "").strip()
        if not partner_id or not checkword:
            raise ValueError("Set SF_PARTNER_ID and SF_CHECK_WORD before calling SF tools")
        environment = os.getenv("SF_ENV", "sandbox").strip().lower()
        if environment not in ENDPOINTS:
            raise ValueError("SF_ENV must be sandbox or production")
        timeout = float(os.getenv("SF_HTTP_TIMEOUT", "10"))
        if timeout <= 0:
            raise ValueError("SF_HTTP_TIMEOUT must be positive")
        endpoint = os.getenv("SF_API_URL", "").strip() or ENDPOINTS[environment]
        parsed = urlparse(endpoint)
        expected_host = urlparse(ENDPOINTS[environment]).hostname
        if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("SF_API_URL must use the configured SF environment host over HTTPS")
        allow_production = os.getenv("SF_ALLOW_PRODUCTION_ORDERS", "").strip().lower() == "true"
        return cls(
            partner_id=partner_id,
            checkword=checkword,
            environment=environment,
            endpoint=endpoint,
            timeout=timeout,
            can_create_order=environment == "sandbox" or allow_production,
        )
