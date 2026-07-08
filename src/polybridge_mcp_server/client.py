"""HTTP client for the PolyBridge Search and Forecast APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from polybridge_contracts.forecast import ForecastResponse

from polybridge_mcp_server.config import PolybridgeMCPConfig
from polybridge_mcp_server.tools.forecast import (
    ForecastResponseShapeError,
    ForecastToolRequest,
    parse_forecast_response_payload,
)
from polybridge_mcp_server.tools.search import (
    SearchAPIResponse,
    SearchResponseShapeError,
    SearchToolRequest,
    parse_search_response_payload,
)

FORECAST_TIMEOUT_SECONDS = 65.0


class PolybridgeClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.detail = detail


class PolybridgeAuthError(PolybridgeClientError):
    """Raised when the upstream API rejects authentication."""


class PolybridgeRateLimitError(PolybridgeClientError):
    """Raised when the upstream API rate limits a request."""


class PolybridgeValidationError(PolybridgeClientError):
    """Raised when the upstream API rejects request validation."""


class PolybridgeUpstreamError(PolybridgeClientError):
    """Raised when the upstream API is unavailable or returns an unexpected error."""


class PolybridgeTimeoutError(PolybridgeClientError):
    """Raised when the upstream API call times out."""


@dataclass(frozen=True, slots=True)
class AttributionEnvelope:
    attribution_code: str | None = None
    referrer: str | None = None
    channel: str | None = None
    tool: str | None = None
    client: str | None = None
    client_version: str | None = None
    trusted_oauth_client_id: str | None = None


@dataclass(frozen=True, slots=True)
class PolybridgeSearchClient:
    config: PolybridgeMCPConfig
    transport: httpx.AsyncBaseTransport | None = None

    async def search(
        self,
        request: SearchToolRequest,
        *,
        bearer_token: str | None = None,
        attribution: AttributionEnvelope | None = None,
        attribution_code: str | None = None,
        referrer: str | None = None,
        use_config_api_key: bool = True,
    ) -> SearchAPIResponse:
        uses_request_bearer = bearer_token is not None
        try:
            async with httpx.AsyncClient(
                base_url=self.config.api_base_url,
                timeout=httpx.Timeout(self.config.timeout_seconds, connect=5.0),
                transport=self.transport,
            ) as client:
                response = await client.post(
                    "/v1/search",
                    json=request.to_api_payload(),
                    headers=self._build_headers(
                        bearer_token=bearer_token,
                        attribution=attribution,
                        attribution_code=attribution_code,
                        referrer=referrer,
                        use_config_api_key=use_config_api_key,
                    ),
                )
        except httpx.TimeoutException as exc:
            raise PolybridgeTimeoutError(
                "PolyBridge Search request timed out",
            ) from exc
        except httpx.ConnectError as exc:
            raise PolybridgeUpstreamError(
                "PolyBridge Search backend unavailable; check POLYBRIDGE_API_BASE_URL "
                "and that the PolyBridge API is reachable",
            ) from exc
        except httpx.HTTPError as exc:
            raise PolybridgeUpstreamError(f"PolyBridge Search request failed: {exc}") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise PolybridgeUpstreamError(
                    "PolyBridge Search API returned invalid JSON",
                    status_code=200,
                ) from exc
            try:
                return parse_search_response_payload(payload)
            except SearchResponseShapeError as exc:
                raise PolybridgeUpstreamError(
                    str(exc),
                    status_code=200,
                ) from exc

        detail = _extract_error_detail(response)
        retry_after = response.headers.get("Retry-After")

        if response.status_code in {401, 403}:
            if uses_request_bearer:
                raise PolybridgeAuthError(
                    "PolyBridge Search authentication failed",
                    status_code=response.status_code,
                    detail=detail,
                )
            if self.config.api_key is not None:
                message = (
                    "PolyBridge Search authentication failed for the configured bearer "
                    "token; the MCP server will not retry anonymously"
                )
            else:
                message = "PolyBridge Search authentication failed"
            raise PolybridgeAuthError(
                f"{message}: {detail}",
                status_code=response.status_code,
                detail=detail,
            )
        if response.status_code == 429:
            message = "PolyBridge Search rate limit exceeded"
            if retry_after is not None:
                message = f"{message}; retry after {retry_after} second(s)"
            raise PolybridgeRateLimitError(
                message,
                status_code=429,
                retry_after=retry_after,
                detail=detail,
            )
        if response.status_code == 422:
            raise PolybridgeValidationError(
                "PolyBridge Search request is invalid: "
                f"{detail}. Likely causes: empty query, too many dimensions, or "
                "top_k_per_dimension above the allowed cap.",
                status_code=422,
                detail=detail,
            )
        if response.status_code == 503:
            message = f"PolyBridge Search API unavailable: {detail}"
            if retry_after is not None:
                message = f"{message}; retry after {retry_after} second(s)"
            raise PolybridgeUpstreamError(
                message,
                status_code=503,
                retry_after=retry_after,
                detail=detail,
            )
        if 500 <= response.status_code <= 599:
            message = f"PolyBridge Search API unavailable: {detail}"
            if retry_after is not None:
                message = f"{message}; retry after {retry_after} second(s)"
            raise PolybridgeUpstreamError(
                message,
                status_code=response.status_code,
                retry_after=retry_after,
                detail=detail,
            )
        raise PolybridgeClientError(
            f"PolyBridge Search request failed with status {response.status_code}: {detail}",
            status_code=response.status_code,
            detail=detail,
        )

    async def forecast(
        self,
        request: ForecastToolRequest,
        *,
        bearer_token: str | None = None,
        attribution: AttributionEnvelope | None = None,
        attribution_code: str | None = None,
        referrer: str | None = None,
        use_config_api_key: bool = True,
    ) -> ForecastResponse:
        uses_request_bearer = bearer_token is not None
        try:
            async with httpx.AsyncClient(
                base_url=self.config.api_base_url,
                timeout=httpx.Timeout(
                    max(self.config.timeout_seconds, FORECAST_TIMEOUT_SECONDS),
                    connect=5.0,
                ),
                transport=self.transport,
            ) as client:
                response = await client.post(
                    "/v1/forecast",
                    json=request.to_api_payload(),
                    headers=self._build_headers(
                        bearer_token=bearer_token,
                        attribution=attribution,
                        attribution_code=attribution_code,
                        referrer=referrer,
                        use_config_api_key=use_config_api_key,
                    ),
                )
        except httpx.TimeoutException as exc:
            raise PolybridgeTimeoutError(
                "PolyBridge Forecast request timed out",
            ) from exc
        except httpx.ConnectError as exc:
            raise PolybridgeUpstreamError(
                "PolyBridge Forecast backend unavailable; check POLYBRIDGE_API_BASE_URL "
                "and that the PolyBridge API is reachable",
            ) from exc
        except httpx.HTTPError as exc:
            raise PolybridgeUpstreamError(f"PolyBridge Forecast request failed: {exc}") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise PolybridgeUpstreamError(
                    "PolyBridge Forecast API returned invalid JSON",
                    status_code=200,
                ) from exc
            try:
                return parse_forecast_response_payload(payload)
            except ForecastResponseShapeError as exc:
                raise PolybridgeUpstreamError(
                    str(exc),
                    status_code=200,
                ) from exc

        detail = _extract_error_detail(response)
        retry_after = response.headers.get("Retry-After")

        if response.status_code in {401, 403}:
            if uses_request_bearer:
                raise PolybridgeAuthError(
                    "PolyBridge Forecast authentication failed",
                    status_code=response.status_code,
                    detail=detail,
                )
            if self.config.api_key is not None:
                message = (
                    "PolyBridge Forecast authentication failed for the configured bearer "
                    "token; the MCP server will not retry anonymously"
                )
            else:
                message = "PolyBridge Forecast authentication failed"
            raise PolybridgeAuthError(
                f"{message}: {detail}",
                status_code=response.status_code,
                detail=detail,
            )
        if response.status_code == 429:
            message = "PolyBridge Forecast rate limit exceeded"
            if retry_after is not None:
                message = f"{message}; retry after {retry_after} second(s)"
            raise PolybridgeRateLimitError(
                message,
                status_code=429,
                retry_after=retry_after,
                detail=detail,
            )
        if response.status_code == 422:
            raise PolybridgeValidationError(
                (
                    "PolyBridge Forecast request is invalid: "
                    f"{detail}. Likely causes: empty question or question length above the "
                    "allowed cap."
                ),
                status_code=422,
                detail=detail,
            )
        if response.status_code in {503, 504}:
            message = f"PolyBridge Forecast API unavailable: {detail}"
            if retry_after is not None:
                message = f"{message}; retry after {retry_after} second(s)"
            raise PolybridgeUpstreamError(
                message,
                status_code=response.status_code,
                retry_after=retry_after,
                detail=detail,
            )
        if 500 <= response.status_code <= 599:
            message = f"PolyBridge Forecast API unavailable: {detail}"
            if retry_after is not None:
                message = f"{message}; retry after {retry_after} second(s)"
            raise PolybridgeUpstreamError(
                message,
                status_code=response.status_code,
                retry_after=retry_after,
                detail=detail,
            )
        raise PolybridgeClientError(
            f"PolyBridge Forecast request failed with status {response.status_code}: {detail}",
            status_code=response.status_code,
            detail=detail,
        )

    def _build_headers(
        self,
        *,
        bearer_token: str | None = None,
        attribution: AttributionEnvelope | None = None,
        attribution_code: str | None = None,
        referrer: str | None = None,
        use_config_api_key: bool = True,
    ) -> dict[str, str]:
        resolved_attribution_code = attribution_code
        if resolved_attribution_code is None and attribution is not None:
            resolved_attribution_code = attribution.attribution_code

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Polybridge-Attribution-Code": resolved_attribution_code
            or self.config.attribution_code,
        }
        if bearer_token is not None:
            headers["Authorization"] = f"Bearer {bearer_token}"
        elif use_config_api_key and self.config.api_key is not None:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        resolved_referrer = referrer
        if resolved_referrer is None and attribution is not None:
            resolved_referrer = attribution.referrer
        if resolved_referrer is None:
            resolved_referrer = self.config.referrer
        if resolved_referrer is not None:
            headers["X-Polybridge-Referrer"] = resolved_referrer
        if attribution is not None:
            if attribution.channel is not None:
                headers["X-Polybridge-Channel"] = attribution.channel
            if attribution.tool is not None:
                headers["X-Polybridge-Tool"] = attribution.tool
            if attribution.client is not None:
                headers["X-Polybridge-Client"] = attribution.client
            if attribution.client_version is not None:
                headers["X-Polybridge-Client-Version"] = attribution.client_version
            if attribution.trusted_oauth_client_id is not None:
                headers["X-Polybridge-Trusted-OAuth-Client-Id"] = (
                    attribution.trusted_oauth_client_id
                )
        return headers


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        body = response.text.strip()
        return body or "unknown upstream error"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return "unknown upstream error"
