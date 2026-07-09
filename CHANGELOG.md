# Changelog

## PolyBridge MCP v0.3.0 (unreleased)

- Adds six read-only RVOL MCP tools for models, assets, latest forecasts, forecast history, actuals, and latest feature snapshot metadata.
- Requires approved PolyBridge API-key access with `rvol:read` for RVOL; RVOL does not support anonymous access.
- Keeps Search and Forecast anonymous behavior unchanged, with `POLYBRIDGE_API_KEY` still optional for higher Search/Forecast usage.
- Bumps the package version to 0.3.0 for the new RVOL tool family.
- Builds on the source-controlled MCPB package restored before this change.

## PolyBridge MCP v0.2.6

- Simplifies the Claude Desktop MCPB install-card description.
- Positions PolyBridge MCP as probabilistic foresight from live prediction markets.
- Keeps no-key anonymous limits and `POLYBRIDGE_API_KEY` for higher usage.
- Keeps PolyBridge MCP read-only: it does not trade or move funds.

## PolyBridge MCP v0.2.5

- Updates the local Claude Desktop / MCPB package so `polybridge_search` and `polybridge_forecast` work without `POLYBRIDGE_API_KEY` at anonymous limits.
- Keeps `POLYBRIDGE_API_KEY` configuration for higher usage.
- Invalid configured auth fails hard and does not fall back to anonymous.
- Keeps Hosted MCP at `https://mcp.polybridge.ai/mcp`, with no key required at anonymous limits and API key or supported OAuth for higher usage.
- Keeps the package read-only with no trading, orders, payments, sessions, market lookup, market history, Situation Rooms, internal APIs, custody, or write actions.

## PolyBridge MCP v0.2.4

- Patch release for the local Claude Desktop / MCPB package.
- Keeps `polybridge_search` and `polybridge_forecast`.
- Updates the public local MCPB package to default omitted Search dimensions to all
  supported dimensions:
  - `direct`
  - `upstream`
  - `downstream`
  - `correlated`
- Keeps the default API base URL as `https://api.polybridge.ai`.
- Keeps the package read-only with no trading or order placement support.

## PolyBridge MCP v0.2.2

- Patch release for local MCPB compatibility.
- Fixes Forecast parsing for responses using `engine_type="oracle_port"`.
- Prevents `PolyBridge Forecast API returned an unexpected response shape` for current Forecast responses.
- Keeps `polybridge_search` and `polybridge_forecast`.
- Keeps Search + Forecast functionality from v0.2.1.

## PolyBridge MCP v0.2.1

- Patch release for the local Claude Desktop / MCPB package.
- Keeps `polybridge_search` and `polybridge_forecast`.
- Keeps Search + Forecast functionality from v0.2.0.
- Cleans public bundle wording and local package contents.
- Narrows bundled local MCPB contents to local stdio runtime files and required contracts.
- Excludes hosted-only OAuth/server files from the local bundle.
- Keeps the default API base URL as `https://api.polybridge.ai`.
- Updates checksum generation so the `.sha256` sidecar references the final artifact filename.

## PolyBridge MCP v0.2.0

- Adds the read-only `polybridge_forecast` tool.
- Keeps the read-only `polybridge_search` tool.
- Updates the public package name and copy to `PolyBridge MCP`.
- Updates the default API base URL to `https://api.polybridge.ai`.
- At release time, keyed Forecast access used `forecast:read`.
- A `search_forecast` key can power both Search and Forecast.
- The package remains read-only and does not support trading or order placement.

## PolyBridge Search MCP v0.1.0

Initial public beta release.

- Adds Claude Desktop MCP extension for PolyBridge Search.
- Exposes one read-only tool: `polybridge_search`.
- Supports anonymous Search usage with bounded limits.
- Supports `POLYBRIDGE_API_KEY` configuration for higher Builder limits.
- Returns ranked prediction-market search results.
- Scores are relevance/ranking scores, not probabilities or forecasts.
- This was the initial Search-only public release.

Explicitly out of scope:

- No trading.
- No forecast generation.
- No payments.
- No sessions.
- No market history.
- No market lookup.
- No Situation Room.
- Hosted MCP remains beta / request access.
