"""MCP server wiring for PolyBridge Search, Forecast, and RVOL."""

from dataclasses import dataclass
from typing import Annotated, Any, Awaitable, Callable

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from polybridge_contracts.forecast import ForecastResponse
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from polybridge_mcp_server.client import (
    AttributionEnvelope,
    PolybridgeClientError,
    PolybridgeSearchClient,
)
from polybridge_mcp_server.config import DEFAULT_ATTRIBUTION_CODE, PolybridgeMCPConfig
from polybridge_mcp_server.tools.forecast import (
    POLYBRIDGE_FORECAST_TOOL_DESCRIPTION,
    ForecastToolRequest,
)
from polybridge_mcp_server.tools.rvol import (
    POLYBRIDGE_RVOL_ACTUALS_TOOL_DESCRIPTION,
    POLYBRIDGE_RVOL_ASSETS_TOOL_DESCRIPTION,
    POLYBRIDGE_RVOL_FEATURES_LATEST_TOOL_DESCRIPTION,
    POLYBRIDGE_RVOL_HISTORY_TOOL_DESCRIPTION,
    POLYBRIDGE_RVOL_LATEST_TOOL_DESCRIPTION,
    POLYBRIDGE_RVOL_MODELS_TOOL_DESCRIPTION,
    RVOL_API_KEY_REQUIRED_MESSAGE,
    RvolActualsRequest,
    RvolAPIResponse,
    RvolAssetsRequest,
    RvolFeaturesLatestRequest,
    RvolHistoryRequest,
    RvolLatestRequest,
    RvolModelsRequest,
)
from polybridge_mcp_server.tools.search import (
    API_KEY_SEARCH_TOOL_LIMITS,
    DEFAULT_SEARCH_DIMENSIONS,
    POLYBRIDGE_SEARCH_TOOL_DESCRIPTION,
    AllowedDimension,
    CompactSearchResponse,
    SearchToolFilters,
    SearchToolLimits,
    SearchToolRequest,
    format_search_response,
    resolve_search_tool_limits,
)

SEARCH_READ_SCOPE = "search:read"
FORECAST_READ_SCOPE = "forecast:read"

LOCAL_SERVER_INSTRUCTIONS = (
    "Use polybridge_search to retrieve relevant prediction markets for a topic or question. "
    "Use polybridge_forecast to generate a read-only forecast using PolyBridge market search "
    "and evidence synthesis. Use the polybridge_rvol_* tools for approved read-only RVOL "
    "access with a PolyBridge API key. This server does not provide trading, payments, "
    "Situation Room, or internal API access."
)
HOSTED_SERVER_INSTRUCTIONS = (
    "Use polybridge_search to retrieve relevant prediction markets for a topic or question. "
    "Use polybridge_forecast to generate a read-only forecast using PolyBridge market search "
    "and evidence synthesis. Use the polybridge_rvol_* tools for approved read-only RVOL "
    "access with a PolyBridge API key. This server does not provide trading, payments, "
    "Situation Room, or internal API access."
)

HOSTED_API_KEY_REQUIRED_MESSAGE = "Hosted MCP Bearer token missing"
INVALID_AUTHORIZATION_HEADER_MESSAGE = "Invalid Authorization header; expected Bearer token"
HOSTED_ANONYMOUS_ATTRIBUTION_CODE = "hosted-mcp-anonymous"
HOSTED_API_KEY_ATTRIBUTION_CODE = "hosted-mcp-api-key"
HOSTED_OAUTH_ATTRIBUTION_CODE = "hosted-mcp-oauth"
HOSTED_OAUTH_REFERRER = "https://mcp.polybridge.ai"
LOCAL_MCPB_CHANNEL = "local_mcpb"
HOSTED_MCP_CHANNEL = "hosted_mcp"
POLYBRIDGE_MCP_CLIENT = "polybridge-mcp"
HOSTED_OAUTH_SERVER_CREDENTIAL_REQUIRED_MESSAGE = (
    "PolyBridge server-side API credential required for hosted MCP OAuth"
)
SEARCH_SCOPE_REQUIRED_MESSAGE = "polybridge_search requires search:read"
FORECAST_SCOPE_REQUIRED_MESSAGE = "polybridge_forecast requires forecast:read"
LOCAL_FORECAST_SCOPE_ACCESS_MESSAGE = (
    "Configured API key needs forecast:read or search_forecast access."
)
LOCAL_FORECAST_AUTH_FAILED_MESSAGE = (
    "Configured POLYBRIDGE_API_KEY was rejected by PolyBridge Forecast authentication."
)


@dataclass(frozen=True, slots=True)
class SearchRequestContext:
    limits: SearchToolLimits
    bearer_token: str | None = None
    attribution: AttributionEnvelope | None = None
    use_config_api_key: bool = True


@dataclass(frozen=True, slots=True)
class HostedToolRequestContext:
    bearer_token: str | None = None
    attribution: AttributionEnvelope | None = None
    use_config_api_key: bool = True


def create_server(
    config: PolybridgeMCPConfig | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
    stateless_http: bool = False,
    hosted_api_key_beta: bool = False,
    oauth_token_verifier: TokenVerifier | None = None,
    require_oauth_transport_auth: bool = True,
) -> FastMCP:
    resolved_config = config or PolybridgeMCPConfig.from_env()
    oauth_enabled = hosted_api_key_beta and resolved_config.oauth_verify_enabled
    search_limits = (
        API_KEY_SEARCH_TOOL_LIMITS
        if hosted_api_key_beta
        else resolve_search_tool_limits(api_key_present=resolved_config.has_api_key)
    )
    client = PolybridgeSearchClient(resolved_config, transport=transport)
    auth_settings = None
    resolved_oauth_verifier = None
    if oauth_enabled and require_oauth_transport_auth:
        from mcp.server.auth.settings import AuthSettings

        from polybridge_mcp_server.oauth import PolybridgeOAuthTokenVerifier

        auth_settings = AuthSettings(
            issuer_url=resolved_config.oauth_authorization_server_url,
            resource_server_url=resolved_config.oauth_protected_resource_url,
        )
        resolved_oauth_verifier = oauth_token_verifier or PolybridgeOAuthTokenVerifier(
            resolved_config
        )
    server = FastMCP(
        name="PolyBridge MCP Server",
        instructions=(
            HOSTED_SERVER_INSTRUCTIONS if hosted_api_key_beta else LOCAL_SERVER_INSTRUCTIONS
        ),
        host=host,
        port=port,
        streamable_http_path=streamable_http_path,
        stateless_http=stateless_http,
        auth=auth_settings,
        token_verifier=resolved_oauth_verifier,
    )

    @server.tool(
        name="polybridge_search",
        title="PolyBridge Search",
        description=POLYBRIDGE_SEARCH_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_search(
        query: Annotated[
            str,
            Field(description="Natural-language topic or question to match to public markets."),
        ],
        dimensions: Annotated[
            list[AllowedDimension],
            Field(
                description=("Search dimensions to run. Uses all supported dimensions by default."),
                min_length=1,
                max_length=search_limits.max_dimensions,
            ),
        ] = DEFAULT_SEARCH_DIMENSIONS,
        top_k_per_dimension: Annotated[
            int,
            Field(
                description=("Maximum number of candidate markets to return per search dimension."),
                ge=1,
                le=search_limits.max_top_k_per_dimension,
            ),
        ] = 5,
        filters: Annotated[
            SearchToolFilters | None,
            Field(
                description=(
                    "Optional market filters. Currently only filters.status is supported, "
                    "with active, closed, or resolved."
                )
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> CompactSearchResponse:
        request_context = _resolve_request_context(
            hosted_api_key_beta=hosted_api_key_beta,
            oauth_enabled=oauth_enabled,
            ctx=ctx,
            default_limits=search_limits,
            config=resolved_config,
            tool_name="polybridge_search",
            required_scope=SEARCH_READ_SCOPE,
            scope_error_message=SEARCH_SCOPE_REQUIRED_MESSAGE,
        )
        try:
            request = SearchToolRequest.model_validate(
                {
                    "query": query,
                    "dimensions": list(dimensions),
                    "top_k_per_dimension": top_k_per_dimension,
                    "filters": filters,
                },
                context={"search_limits": request_context.limits},
            )
        except PydanticValidationError as exc:
            raise ToolError(_format_validation_error(exc)) from exc

        try:
            return format_search_response(
                await client.search(
                    request,
                    bearer_token=request_context.bearer_token,
                    attribution=request_context.attribution,
                    use_config_api_key=request_context.use_config_api_key,
                )
            )
        except PolybridgeClientError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="polybridge_forecast",
        title="PolyBridge Forecast",
        description=POLYBRIDGE_FORECAST_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_forecast(
        question: Annotated[
            str,
            Field(
                description=(
                    "Clearly stated future-event forecasting question, 500 characters or fewer."
                )
            ),
        ],
        include_graph: Annotated[
            bool,
            Field(description=("Whether to include the causal graph in the structured response.")),
        ] = True,
        ctx: Context | None = None,
    ) -> ForecastResponse:
        try:
            request = ForecastToolRequest.model_validate(
                {
                    "question": question,
                    "include_graph": include_graph,
                }
            )
        except PydanticValidationError as exc:
            raise ToolError(_format_validation_error(exc)) from exc

        if hosted_api_key_beta:
            request_context = _resolve_hosted_tool_request_context(
                hosted_api_key_beta=hosted_api_key_beta,
                oauth_enabled=oauth_enabled,
                ctx=ctx,
                config=resolved_config,
                tool_name="polybridge_forecast",
                required_scope=FORECAST_READ_SCOPE,
                scope_error_message=FORECAST_SCOPE_REQUIRED_MESSAGE,
            )
        else:
            request_context = HostedToolRequestContext(
                attribution=_build_local_attribution(
                    config=resolved_config,
                    tool_name="polybridge_forecast",
                )
            )

        try:
            return await client.forecast(
                request,
                bearer_token=request_context.bearer_token,
                attribution=request_context.attribution,
                use_config_api_key=request_context.use_config_api_key,
            )
        except PolybridgeClientError as exc:
            if not hosted_api_key_beta and exc.status_code in {401, 403}:
                if exc.status_code == 403:
                    raise ToolError(LOCAL_FORECAST_SCOPE_ACCESS_MESSAGE) from exc
                raise ToolError(LOCAL_FORECAST_AUTH_FAILED_MESSAGE) from exc
            raise ToolError(str(exc)) from exc

    async def _execute_rvol_tool(
        *,
        tool_name: str,
        request_model: type[BaseModel],
        request_data: dict[str, Any],
        client_method: Callable[..., Awaitable[RvolAPIResponse]],
    ) -> RvolAPIResponse:
        if not resolved_config.has_api_key:
            raise ToolError(RVOL_API_KEY_REQUIRED_MESSAGE)
        try:
            request = request_model.model_validate(request_data)
        except PydanticValidationError as exc:
            raise ToolError(_format_validation_error(exc)) from exc

        try:
            return await client_method(
                request,
                attribution=_build_local_attribution(
                    config=resolved_config,
                    tool_name=tool_name,
                ),
            )
        except PolybridgeClientError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="polybridge_rvol_models",
        title="PolyBridge RVOL Models",
        description=POLYBRIDGE_RVOL_MODELS_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_rvol_models(
        model_id: Annotated[
            str | None,
            Field(description="Optional stable RVOL model identifier."),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of models to return.", ge=1, le=1000),
        ] = 100,
    ) -> RvolAPIResponse:
        return await _execute_rvol_tool(
            tool_name="polybridge_rvol_models",
            request_model=RvolModelsRequest,
            request_data={"model_id": model_id, "limit": limit},
            client_method=client.rvol_models,
        )

    @server.tool(
        name="polybridge_rvol_assets",
        title="PolyBridge RVOL Assets",
        description=POLYBRIDGE_RVOL_ASSETS_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_rvol_assets(
        include_inactive: Annotated[
            bool,
            Field(description="Whether to include inactive RVOL assets."),
        ] = False,
        limit: Annotated[
            int,
            Field(description="Maximum number of assets to return.", ge=1, le=1000),
        ] = 500,
    ) -> RvolAPIResponse:
        return await _execute_rvol_tool(
            tool_name="polybridge_rvol_assets",
            request_model=RvolAssetsRequest,
            request_data={"include_inactive": include_inactive, "limit": limit},
            client_method=client.rvol_assets,
        )

    @server.tool(
        name="polybridge_rvol_latest",
        title="PolyBridge RVOL Latest",
        description=POLYBRIDGE_RVOL_LATEST_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_rvol_latest(
        model: Annotated[
            str | None,
            Field(description="Optional RVOL model alias or model_id."),
        ] = None,
        model_version: Annotated[
            str | None,
            Field(description="Optional RVOL model version."),
        ] = None,
        asset: Annotated[
            str | None,
            Field(description="Optional RVOL asset symbol."),
        ] = None,
        horizon: Annotated[
            str | None,
            Field(description="Optional RVOL forecast horizon."),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of forecasts to return.", ge=1, le=1000),
        ] = 100,
    ) -> RvolAPIResponse:
        return await _execute_rvol_tool(
            tool_name="polybridge_rvol_latest",
            request_model=RvolLatestRequest,
            request_data={
                "model": model,
                "model_version": model_version,
                "asset": asset,
                "horizon": horizon,
                "limit": limit,
            },
            client_method=client.rvol_latest,
        )

    @server.tool(
        name="polybridge_rvol_history",
        title="PolyBridge RVOL History",
        description=POLYBRIDGE_RVOL_HISTORY_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_rvol_history(
        model: Annotated[
            str | None,
            Field(description="Optional RVOL model alias or model_id."),
        ] = None,
        model_version: Annotated[
            str | None,
            Field(description="Optional RVOL model version."),
        ] = None,
        asset: Annotated[
            str | None,
            Field(description="Optional RVOL asset symbol."),
        ] = None,
        horizon: Annotated[
            str | None,
            Field(description="Optional RVOL forecast horizon."),
        ] = None,
        start: Annotated[
            str | None,
            Field(description="Optional inclusive UTC as_of start ISO date-time."),
        ] = None,
        end: Annotated[
            str | None,
            Field(description="Optional inclusive UTC as_of end ISO date-time."),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of forecasts to return.", ge=1, le=10000),
        ] = 1000,
    ) -> RvolAPIResponse:
        return await _execute_rvol_tool(
            tool_name="polybridge_rvol_history",
            request_model=RvolHistoryRequest,
            request_data={
                "model": model,
                "model_version": model_version,
                "asset": asset,
                "horizon": horizon,
                "start": start,
                "end": end,
                "limit": limit,
            },
            client_method=client.rvol_history,
        )

    @server.tool(
        name="polybridge_rvol_actuals",
        title="PolyBridge RVOL Actuals",
        description=POLYBRIDGE_RVOL_ACTUALS_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_rvol_actuals(
        asset: Annotated[
            str | None,
            Field(description="Optional RVOL asset symbol."),
        ] = None,
        horizon: Annotated[
            str | None,
            Field(description="Optional RVOL horizon."),
        ] = None,
        start: Annotated[
            str | None,
            Field(description="Optional inclusive UTC as_of start ISO date-time."),
        ] = None,
        end: Annotated[
            str | None,
            Field(description="Optional inclusive UTC as_of end ISO date-time."),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of actuals to return.", ge=1, le=10000),
        ] = 1000,
    ) -> RvolAPIResponse:
        return await _execute_rvol_tool(
            tool_name="polybridge_rvol_actuals",
            request_model=RvolActualsRequest,
            request_data={
                "asset": asset,
                "horizon": horizon,
                "start": start,
                "end": end,
                "limit": limit,
            },
            client_method=client.rvol_actuals,
        )

    @server.tool(
        name="polybridge_rvol_features_latest",
        title="PolyBridge RVOL Features Latest",
        description=POLYBRIDGE_RVOL_FEATURES_LATEST_TOOL_DESCRIPTION,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        structured_output=True,
    )
    async def polybridge_rvol_features_latest(
        asset: Annotated[
            str | None,
            Field(description="Optional RVOL asset symbol."),
        ] = None,
        horizon: Annotated[
            str | None,
            Field(description="Optional RVOL horizon."),
        ] = None,
        feature_set_id: Annotated[
            str | None,
            Field(description="Optional public feature-set identifier."),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of feature snapshots to return.", ge=1, le=1000),
        ] = 100,
    ) -> RvolAPIResponse:
        return await _execute_rvol_tool(
            tool_name="polybridge_rvol_features_latest",
            request_model=RvolFeaturesLatestRequest,
            request_data={
                "asset": asset,
                "horizon": horizon,
                "feature_set_id": feature_set_id,
                "limit": limit,
            },
            client_method=client.rvol_features_latest,
        )

    return server


def _format_validation_error(exc: PydanticValidationError) -> str:
    messages = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error["loc"])
        messages.append(f"{path}: {error['msg']}")
    return "; ".join(messages)


def _resolve_request_context(
    *,
    hosted_api_key_beta: bool,
    oauth_enabled: bool,
    ctx: Context | None,
    default_limits: SearchToolLimits,
    config: PolybridgeMCPConfig,
    tool_name: str,
    required_scope: str,
    scope_error_message: str,
) -> SearchRequestContext:
    if not hosted_api_key_beta:
        return SearchRequestContext(
            limits=default_limits,
            attribution=_build_local_attribution(config=config, tool_name=tool_name),
        )

    hosted_context = _resolve_hosted_tool_request_context(
        hosted_api_key_beta=hosted_api_key_beta,
        oauth_enabled=oauth_enabled,
        ctx=ctx,
        config=config,
        tool_name=tool_name,
        required_scope=required_scope,
        scope_error_message=scope_error_message,
    )
    return SearchRequestContext(
        limits=API_KEY_SEARCH_TOOL_LIMITS,
        bearer_token=hosted_context.bearer_token,
        attribution=hosted_context.attribution,
        use_config_api_key=hosted_context.use_config_api_key,
    )


def _resolve_hosted_tool_request_context(
    *,
    hosted_api_key_beta: bool,
    oauth_enabled: bool,
    ctx: Context | None,
    config: PolybridgeMCPConfig,
    tool_name: str,
    required_scope: str,
    scope_error_message: str,
) -> HostedToolRequestContext:
    if not hosted_api_key_beta:
        return HostedToolRequestContext()

    if not oauth_enabled:
        bearer_token = _extract_optional_hosted_bearer_token(ctx)
        if bearer_token is None:
            return HostedToolRequestContext(
                attribution=_build_hosted_attribution(
                    config=config,
                    tool_name=tool_name,
                    default_attribution_code=HOSTED_ANONYMOUS_ATTRIBUTION_CODE,
                ),
                use_config_api_key=False,
            )
        return HostedToolRequestContext(
            bearer_token=bearer_token,
            attribution=_build_hosted_attribution(
                config=config,
                tool_name=tool_name,
                default_attribution_code=HOSTED_API_KEY_ATTRIBUTION_CODE,
            ),
            use_config_api_key=False,
        )

    from polybridge_mcp_server.oauth import PolybridgeHostedAccessToken

    access_token = get_access_token()
    if access_token is None:
        return HostedToolRequestContext(
            attribution=_build_hosted_attribution(
                config=config,
                tool_name=tool_name,
                default_attribution_code=HOSTED_ANONYMOUS_ATTRIBUTION_CODE,
            ),
            use_config_api_key=False,
        )
    if not isinstance(access_token, PolybridgeHostedAccessToken):
        raise ToolError("Hosted MCP authentication failed")
    if required_scope not in access_token.scopes:
        raise ToolError(scope_error_message)

    if access_token.auth_type == "api_key":
        return HostedToolRequestContext(
            bearer_token=access_token.token,
            attribution=_build_hosted_attribution(
                config=config,
                tool_name=tool_name,
                default_attribution_code=HOSTED_API_KEY_ATTRIBUTION_CODE,
            ),
            use_config_api_key=False,
        )

    if not config.has_api_key:
        raise ToolError(HOSTED_OAUTH_SERVER_CREDENTIAL_REQUIRED_MESSAGE)

    return HostedToolRequestContext(
        attribution=_build_hosted_attribution(
            config=config,
            tool_name=tool_name,
            default_attribution_code=HOSTED_OAUTH_ATTRIBUTION_CODE,
            default_referrer=HOSTED_OAUTH_REFERRER,
            trusted_oauth_client_id=access_token.client_id,
        ),
    )


def _build_hosted_attribution(
    *,
    config: PolybridgeMCPConfig,
    tool_name: str,
    default_attribution_code: str,
    default_referrer: str | None = None,
    trusted_oauth_client_id: str | None = None,
) -> AttributionEnvelope:
    from polybridge_mcp_server import __version__

    # Hosted mode treats builder-program as the package default rather than a meaningful
    # hosted override. Only custom configured attribution codes replace hosted defaults.
    attribution_code = (
        config.attribution_code
        if config.attribution_code != DEFAULT_ATTRIBUTION_CODE
        else default_attribution_code
    )
    referrer = config.referrer if config.referrer is not None else default_referrer

    return AttributionEnvelope(
        attribution_code=attribution_code,
        referrer=referrer,
        channel=HOSTED_MCP_CHANNEL,
        tool=tool_name,
        client=POLYBRIDGE_MCP_CLIENT,
        client_version=__version__,
        trusted_oauth_client_id=trusted_oauth_client_id,
    )


def _build_local_attribution(
    *,
    config: PolybridgeMCPConfig,
    tool_name: str,
) -> AttributionEnvelope:
    from polybridge_mcp_server import __version__

    return AttributionEnvelope(
        attribution_code=config.attribution_code,
        referrer=config.referrer,
        channel=LOCAL_MCPB_CHANNEL,
        tool=tool_name,
        client=POLYBRIDGE_MCP_CLIENT,
        client_version=__version__,
    )


def _extract_hosted_bearer_token(ctx: Context | None) -> str:
    bearer_token = _extract_optional_hosted_bearer_token(ctx)
    if bearer_token is None:
        raise ToolError(HOSTED_API_KEY_REQUIRED_MESSAGE)
    return bearer_token


def _extract_optional_hosted_bearer_token(ctx: Context | None) -> str | None:
    request = None
    if ctx is not None:
        try:
            request = ctx.request_context.request
        except ValueError:
            request = None

    authorization = None
    if request is not None:
        authorization = request.headers.get("authorization")

    if authorization is None:
        return None

    scheme, separator, token = authorization.partition(" ")
    normalized_token = token.strip()
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not normalized_token
        or any(character.isspace() for character in normalized_token)
    ):
        raise ToolError(INVALID_AUTHORIZATION_HEADER_MESSAGE)

    return normalized_token
