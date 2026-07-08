"""Configuration for the PolyBridge MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_POLYBRIDGE_API_BASE_URL = "https://api.polybridge.ai"
DEFAULT_SEARCH_TIMEOUT_SECONDS = 40.0
DEFAULT_ATTRIBUTION_CODE = "builder-program"
DEFAULT_OAUTH_PROTECTED_RESOURCE_URL = "https://mcp.polybridge.ai/mcp"
DEFAULT_OAUTH_AUTHORIZATION_SERVER_URL = "https://api.polybridge.ai"
DEFAULT_OAUTH_VERIFY_URL = "https://api.polybridge.ai/internal/oauth/verify"


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() == "true"


def _normalize_optional_env(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("POLYBRIDGE_API_BASE_URL must be a valid http(s) URL")
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class PolybridgeMCPConfig:
    api_base_url: str = DEFAULT_POLYBRIDGE_API_BASE_URL
    api_key: str | None = None
    attribution_code: str = DEFAULT_ATTRIBUTION_CODE
    referrer: str | None = None
    timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT_SECONDS
    hosted_mcp_oauth_enabled: bool = False
    oauth_protected_resource_url: str = DEFAULT_OAUTH_PROTECTED_RESOURCE_URL
    oauth_authorization_server_url: str = DEFAULT_OAUTH_AUTHORIZATION_SERVER_URL
    oauth_verify_url: str = DEFAULT_OAUTH_VERIFY_URL
    oauth_verify_shared_secret: str | None = None

    @classmethod
    def from_env(cls) -> PolybridgeMCPConfig:
        return cls(
            api_base_url=_normalize_base_url(
                os.environ.get("POLYBRIDGE_API_BASE_URL", DEFAULT_POLYBRIDGE_API_BASE_URL)
            ),
            api_key=_normalize_optional_env(os.environ.get("POLYBRIDGE_API_KEY")),
            attribution_code=(
                _normalize_optional_env(os.environ.get("POLYBRIDGE_ATTRIBUTION_CODE"))
                or DEFAULT_ATTRIBUTION_CODE
            ),
            referrer=_normalize_optional_env(os.environ.get("POLYBRIDGE_REFERRER")),
            timeout_seconds=DEFAULT_SEARCH_TIMEOUT_SECONDS,
            hosted_mcp_oauth_enabled=_env_bool("POLYBRIDGE_HOSTED_MCP_OAUTH_ENABLED", False),
            oauth_protected_resource_url=_normalize_base_url(
                os.environ.get(
                    "POLYBRIDGE_OAUTH_PROTECTED_RESOURCE_URL",
                    DEFAULT_OAUTH_PROTECTED_RESOURCE_URL,
                )
            ),
            oauth_authorization_server_url=_normalize_base_url(
                os.environ.get(
                    "POLYBRIDGE_OAUTH_AUTHORIZATION_SERVER_URL",
                    DEFAULT_OAUTH_AUTHORIZATION_SERVER_URL,
                )
            ),
            oauth_verify_url=_normalize_base_url(
                os.environ.get(
                    "POLYBRIDGE_OAUTH_VERIFY_URL",
                    DEFAULT_OAUTH_VERIFY_URL,
                )
            ),
            oauth_verify_shared_secret=_normalize_optional_env(
                os.environ.get("POLYBRIDGE_OAUTH_VERIFY_SHARED_SECRET")
            ),
        )

    @property
    def has_api_key(self) -> bool:
        return self.api_key is not None

    @property
    def oauth_verify_enabled(self) -> bool:
        return self.hosted_mcp_oauth_enabled and self.oauth_verify_shared_secret is not None
