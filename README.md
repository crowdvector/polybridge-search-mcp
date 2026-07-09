# PolyBridge MCP

PolyBridge MCP gives Claude Desktop probabilistic foresight from live prediction markets and approved read-only RVOL access.

Ask a question about the future, even when no exact market exists. PolyBridge finds relevant markets, synthesizes the evidence, and returns a read-only forecast with probabilities and source-market metadata.

Search and Forecast can run without an API key at anonymous limits. Add `POLYBRIDGE_API_KEY` for higher Search/Forecast usage and for approved RVOL access with `rvol:read`.

PolyBridge MCP is read-only. It does not trade or move funds.

## Tools

PolyBridge MCP exposes read-only tools:

- `polybridge_search`
- `polybridge_forecast`
- `polybridge_rvol_models`
- `polybridge_rvol_assets`
- `polybridge_rvol_latest`
- `polybridge_rvol_history`
- `polybridge_rvol_actuals`
- `polybridge_rvol_features_latest`

All tools are read-only. They do not place trades, submit orders, handle custody,
or perform write actions.

### Search

`polybridge_search` retrieves relevant prediction markets for a topic or question.

- Search results return ranked prediction-market retrieval results.
- Scores are relevance/ranking scores, not probabilities.
- Local MCPB Search works without `POLYBRIDGE_API_KEY` at anonymous limits.
- Configure `POLYBRIDGE_API_KEY` only for higher Search usage.
- If `dimensions` is omitted, Search uses all supported dimensions by default:
  `direct`, `upstream`, `downstream`, and `correlated`.

### Forecast

`polybridge_forecast` generates read-only forecasts using PolyBridge market search and evidence synthesis.

- Forecast responses return forecast outputs and probabilities.
- Local MCPB Forecast works without `POLYBRIDGE_API_KEY` at anonymous limits.
- Configure `POLYBRIDGE_API_KEY` only for higher Forecast usage.
- A `search_forecast` key can power both Search and Forecast tools.

### RVOL

The `polybridge_rvol_*` tools provide approved read-only access to PolyBridge realized-volatility model metadata, assets, latest forecasts, forecast history, actuals, and feature snapshot metadata.

- RVOL requires `POLYBRIDGE_API_KEY` with `rvol:read`.
- RVOL does not support anonymous access.
- If your key is not approved for RVOL, request access from PolyBridge.
- RVOL responses return curated backend JSON. They are not trading analysis or advice.

## Non-goals

PolyBridge MCP does not provide:

- trading
- orders
- payments
- sessions
- market lookup
- Situation Rooms
- internal APIs
- custody
- write actions

## Installation

1. Download the latest `.mcpb` package from GitHub Releases.
2. Open or import the file in Claude Desktop.
3. Enable the extension.
4. Search and Forecast can run without an API key at anonymous limits. Configure `POLYBRIDGE_API_KEY` for higher Search/Forecast usage or approved RVOL access.

## Basic Usage

Ask Claude:

> Use PolyBridge Search to find active prediction markets related to US recession risk.

Or:

> Use PolyBridge Forecast to estimate the probability of a US recession in 2026.

Or, with an approved RVOL key:

> Use PolyBridge RVOL latest to fetch the latest BTC one-day realized-volatility forecasts.

## API Key Configuration

- Local MCPB Search and Forecast work without `POLYBRIDGE_API_KEY` at anonymous limits.
- Configure `POLYBRIDGE_API_KEY` in the Claude Desktop extension settings for higher Search/Forecast usage or approved RVOL access.
- RVOL requires a PolyBridge API key with `rvol:read` and does not run anonymously.
- Invalid configured auth fails hard and does not fall back to anonymous.
- Use the PolyBridge Developer Console to create a Search+Forecast key or request approved RVOL access from PolyBridge.
- A `search_forecast` key can power both Search and Forecast tools.
- Do not paste API keys into chat.

## Search Limits

Anonymous / local with no key:

- `top_k_per_dimension <= 50`
- `dimensions <= 4`

With `POLYBRIDGE_API_KEY`:

- `top_k_per_dimension <= 100`
- `dimensions <= 4`

## Release Packaging

For a local v0.3.1 MCPB build, run:

```sh
python3 scripts/build_mcpb.py
```

This creates local artifacts only:

- `dist/polybridge-mcp-v0.3.1.mcpb`
- `dist/polybridge-mcp-v0.3.1.mcpb.sha256`

Do not publish, tag, or upload these files until the release has passed review.

## Supported Search Dimensions

- `direct`
- `upstream`
- `downstream`
- `correlated`

## REST API

The public REST API supports Search and Forecast without an API key at anonymous limits.
Add an API key for higher Search/Forecast usage. RVOL requires an approved PolyBridge API key with `rvol:read`.

- Search: `https://api.polybridge.ai/v1/search`
- Forecast: `https://api.polybridge.ai/v1/forecast`
- RVOL models: `https://api.polybridge.ai/v1/rvol/models`
- RVOL assets: `https://api.polybridge.ai/v1/rvol/assets`
- RVOL latest: `https://api.polybridge.ai/v1/rvol/latest`
- RVOL history: `https://api.polybridge.ai/v1/rvol/history`
- RVOL actuals: `https://api.polybridge.ai/v1/rvol/actuals`
- RVOL latest features: `https://api.polybridge.ai/v1/rvol/features/latest`

## Hosted MCP

Hosted MCP is available at `https://mcp.polybridge.ai/mcp`. Search and Forecast
can run without an API key at anonymous limits. Add an API key or supported
OAuth for higher Search/Forecast usage. RVOL requires approved API-key access.
Invalid configured auth fails hard and does not fall back to anonymous.

## Support

For higher usage, RVOL access, or other access questions, contact the PolyBridge team.
