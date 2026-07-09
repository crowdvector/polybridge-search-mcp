import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

import httpx

EXPECTED_TOOL_NAMES = {
    "polybridge_search",
    "polybridge_forecast",
    "polybridge_rvol_models",
    "polybridge_rvol_assets",
    "polybridge_rvol_latest",
    "polybridge_rvol_history",
    "polybridge_rvol_actuals",
    "polybridge_rvol_features_latest",
}
EXPECTED_RVOL_TOOL_NAMES = {
    "polybridge_rvol_models",
    "polybridge_rvol_assets",
    "polybridge_rvol_latest",
    "polybridge_rvol_history",
    "polybridge_rvol_actuals",
    "polybridge_rvol_features_latest",
}


class PolybridgeMCPSmokeTest(unittest.IsolatedAsyncioTestCase):
    def test_package_imports(self) -> None:
        import polybridge_mcp_server

        self.assertEqual(polybridge_mcp_server.__version__, "0.3.0")

    def test_release_surface_versions_match(self) -> None:
        import polybridge_mcp_server

        manifest = json.loads(Path("manifest.json").read_text())
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())

        self.assertEqual(manifest["version"], "0.3.0")
        self.assertEqual(pyproject["project"]["version"], "0.3.0")
        self.assertEqual(polybridge_mcp_server.__version__, "0.3.0")

    def test_manifest_release_copy_and_tools(self) -> None:
        manifest = json.loads(Path("manifest.json").read_text())

        self.assertEqual(
            manifest["description"],
            "Read-only PolyBridge tools for Search, Forecast, and approved RVOL data "
            "access.",
        )
        self.assertEqual(
            manifest["user_config"]["POLYBRIDGE_API_KEY"]["description"],
            "Optional for Search and Forecast higher limits. Required for approved RVOL "
            "tools; the key must include rvol:read. Do not paste API keys into chat.",
        )
        self.assertEqual(
            manifest["user_config"]["POLYBRIDGE_ATTRIBUTION_CODE"]["description"],
            "Code sent with PolyBridge Search, Forecast, and RVOL API requests for "
            "builder attribution.",
        )

        manifest_tools = {tool["name"]: tool for tool in manifest["tools"]}
        self.assertTrue(EXPECTED_TOOL_NAMES.issubset(manifest_tools))
        for tool_name in EXPECTED_RVOL_TOOL_NAMES:
            description = manifest_tools[tool_name]["description"]
            self.assertIn("Read-only", description)
            self.assertIn("POLYBRIDGE_API_KEY", description)
            self.assertIn("rvol:read", description)
            self.assertNotIn("trade", description.lower())
            self.assertNotIn("order", description.lower())

    async def test_server_registers_search_forecast_and_rvol_tools(self) -> None:
        from polybridge_mcp_server.config import PolybridgeMCPConfig
        from polybridge_mcp_server.server import create_server

        mcp_server = create_server(config=PolybridgeMCPConfig())
        tools = {tool.name: tool for tool in await mcp_server.list_tools()}

        self.assertTrue(EXPECTED_TOOL_NAMES.issubset(tools))
        for tool_name in EXPECTED_TOOL_NAMES:
            self.assertTrue(tools[tool_name].annotations.readOnlyHint)

    def test_api_key_env_handling_imports_without_printing_values(self) -> None:
        from polybridge_mcp_server.config import PolybridgeMCPConfig

        with patch.dict(os.environ, {"POLYBRIDGE_API_KEY": " test-key "}, clear=False):
            config = PolybridgeMCPConfig.from_env()

        self.assertEqual(config.api_key, "test-key")
        self.assertTrue(config.has_api_key)

    async def test_search_forecast_anonymous_headers_stay_unchanged(self) -> None:
        from polybridge_mcp_server.client import PolybridgeSearchClient
        from polybridge_mcp_server.config import PolybridgeMCPConfig

        client = PolybridgeSearchClient(PolybridgeMCPConfig())
        headers = client._build_headers()

        self.assertNotIn("Authorization", headers)

    async def test_rvol_missing_key_returns_friendly_error_without_upstream_call(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        from polybridge_mcp_server.client import PolybridgeAuthError, PolybridgeSearchClient
        from polybridge_mcp_server.config import PolybridgeMCPConfig
        from polybridge_mcp_server.server import create_server
        from polybridge_mcp_server.tools.rvol import (
            RVOL_API_KEY_REQUIRED_MESSAGE,
            RvolModelsRequest,
        )

        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json=[])

        config = PolybridgeMCPConfig()
        client = PolybridgeSearchClient(config, transport=httpx.MockTransport(handler))

        with self.assertRaises(PolybridgeAuthError) as client_error:
            await client.rvol_models(RvolModelsRequest())
        self.assertEqual(str(client_error.exception), RVOL_API_KEY_REQUIRED_MESSAGE)
        self.assertFalse(called)

        mcp_server = create_server(config=config, transport=httpx.MockTransport(handler))
        with self.assertRaises(ToolError) as tool_error:
            await mcp_server.call_tool("polybridge_rvol_models", {})
        self.assertIn(RVOL_API_KEY_REQUIRED_MESSAGE, str(tool_error.exception))
        self.assertFalse(called)

    async def test_rvol_tools_call_expected_paths_and_query_params(self) -> None:
        from polybridge_mcp_server.config import PolybridgeMCPConfig
        from polybridge_mcp_server.server import create_server

        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json=[
                    {
                        "model_id": "rvol-public",
                        "model_version": "2026-07-01",
                        "asset": "BTC",
                        "horizon": "1d",
                        "as_of": "2026-07-09T00:00:00Z",
                        "prediction": {"forecast_volatility": 0.42, "unit": "annualized"},
                    }
                ],
            )

        mcp_server = create_server(
            config=PolybridgeMCPConfig(
                api_base_url="https://polybridge.test",
                api_key="unit-test-key",
            ),
            transport=httpx.MockTransport(handler),
        )
        cases = [
            (
                "polybridge_rvol_models",
                {"model_id": "rvol-public", "limit": 2},
                "/v1/rvol/models",
                {"model_id": "rvol-public", "limit": "2"},
            ),
            (
                "polybridge_rvol_assets",
                {"include_inactive": True, "limit": 3},
                "/v1/rvol/assets",
                {"include_inactive": "true", "limit": "3"},
            ),
            (
                "polybridge_rvol_latest",
                {"model": None, "asset": "BTC", "horizon": "1d", "limit": 4},
                "/v1/rvol/latest",
                {"asset": "BTC", "horizon": "1d", "limit": "4"},
            ),
            (
                "polybridge_rvol_history",
                {
                    "model": "public",
                    "model_version": None,
                    "asset": "ETH",
                    "horizon": "7d",
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-09T00:00:00Z",
                    "limit": 5,
                },
                "/v1/rvol/history",
                {
                    "model": "public",
                    "asset": "ETH",
                    "horizon": "7d",
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-09T00:00:00Z",
                    "limit": "5",
                },
            ),
            (
                "polybridge_rvol_actuals",
                {
                    "asset": "BTC",
                    "horizon": "1d",
                    "start": None,
                    "end": "2026-07-09T00:00:00Z",
                    "limit": 6,
                },
                "/v1/rvol/actuals",
                {
                    "asset": "BTC",
                    "horizon": "1d",
                    "end": "2026-07-09T00:00:00Z",
                    "limit": "6",
                },
            ),
            (
                "polybridge_rvol_features_latest",
                {"asset": "BTC", "feature_set_id": "public-features", "limit": 7},
                "/v1/rvol/features/latest",
                {"asset": "BTC", "feature_set_id": "public-features", "limit": "7"},
            ),
        ]

        for tool_name, arguments, expected_path, expected_query in cases:
            await mcp_server.call_tool(tool_name, arguments)
            request = requests.pop(0)
            self.assertEqual(request.url.path, expected_path)
            self.assertEqual(dict(request.url.params), expected_query)
            self.assertEqual(request.headers.get("authorization"), "Bearer unit-test-key")

    async def test_rvol_error_mapping(self) -> None:
        from polybridge_mcp_server.client import PolybridgeClientError, PolybridgeSearchClient
        from polybridge_mcp_server.config import PolybridgeMCPConfig
        from polybridge_mcp_server.tools.rvol import RvolModelsRequest

        cases = [
            (
                401,
                {},
                "PolyBridge rejected the configured API key for RVOL. Check "
                "POLYBRIDGE_API_KEY and make sure the key is active and approved for "
                "rvol:read.",
            ),
            (
                403,
                {},
                "This API key does not include rvol:read. Use an approved key or "
                "request RVOL access.",
            ),
            (429, {}, "PolyBridge RVOL rate limit exceeded. Retry later."),
            (
                429,
                {"Retry-After": "12"},
                "PolyBridge RVOL rate limit exceeded. Retry after 12 second(s).",
            ),
            (422, {}, "PolyBridge RVOL request is invalid: invalid horizon"),
        ]

        for status_code, headers, expected_message in cases:
            with self.subTest(status_code=status_code, headers=headers):

                def handler(request: httpx.Request) -> httpx.Response:
                    return httpx.Response(
                        status_code,
                        json={"detail": "invalid horizon"},
                        headers=headers,
                    )

                client = PolybridgeSearchClient(
                    PolybridgeMCPConfig(
                        api_base_url="https://polybridge.test",
                        api_key="unit-test-key",
                    ),
                    transport=httpx.MockTransport(handler),
                )
                with self.assertRaises(PolybridgeClientError) as error:
                    await client.rvol_models(RvolModelsRequest(limit=1))
                self.assertEqual(str(error.exception), expected_message)

    async def test_rvol_curated_backend_json_is_preserved_without_internal_fields(self) -> None:
        from polybridge_mcp_server.client import PolybridgeSearchClient
        from polybridge_mcp_server.config import PolybridgeMCPConfig
        from polybridge_mcp_server.tools.rvol import RvolLatestRequest

        def field_name(*parts: str) -> str:
            return "_".join(parts)

        internal_model_field = field_name("model", "metadata")
        internal_snapshot_field = field_name("feature", "snapshot", "id")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {
                        "model_id": "rvol-public",
                        "model_version": "2026-07-01",
                        "asset": "BTC",
                        "horizon": "1d",
                        "as_of": "2026-07-09T00:00:00Z",
                        "prediction": {
                            "forecast_variance": 0.12,
                            "forecast_volatility": 0.34,
                            "annualized_volatility": 0.56,
                            "unit": "annualized",
                            internal_snapshot_field: "hidden",
                        },
                        "prediction_value": 0.34,
                        internal_model_field: {"hidden": True},
                    }
                ],
            )

        client = PolybridgeSearchClient(
            PolybridgeMCPConfig(
                api_base_url="https://polybridge.test",
                api_key="unit-test-key",
            ),
            transport=httpx.MockTransport(handler),
        )

        result = await client.rvol_latest(RvolLatestRequest(asset="BTC"))

        self.assertEqual(
            result,
            [
                {
                    "model_id": "rvol-public",
                    "model_version": "2026-07-01",
                    "asset": "BTC",
                    "horizon": "1d",
                    "as_of": "2026-07-09T00:00:00Z",
                    "prediction": {
                        "forecast_variance": 0.12,
                        "forecast_volatility": 0.34,
                        "annualized_volatility": 0.56,
                        "unit": "annualized",
                    },
                    "prediction_value": 0.34,
                }
            ],
        )

    def test_public_docs_and_fixtures_do_not_expose_internal_fields(self) -> None:
        def field_name(*parts: str) -> str:
            return "_".join(parts)

        banned_public_fields = {
            field_name("artifact", "uri"),
            field_name("feature", "contract"),
            field_name("model", "metadata"),
            field_name("source", "freshness"),
            "".join(("prove", "nance")),
            field_name("feature", "snapshot", "id"),
            field_name("price", "series", "key"),
            field_name("iv", "series", "key"),
            field_name("internal", "id"),
            field_name("internal", "uuid"),
        }
        checked_paths = [
            Path("README.md"),
            Path("CHANGELOG.md"),
            Path("manifest.json"),
            Path("pyproject.toml"),
            *Path("src").rglob("*.py"),
            *Path("tests").rglob("*.py"),
        ]

        for path in checked_paths:
            content = path.read_text()
            for field in banned_public_fields:
                self.assertNotIn(field, content, msg=f"{field} appears in {path}")

    def test_readme_copy_is_not_stale_for_rvol(self) -> None:
        readme = Path("README.md").read_text()
        old_version = ".".join(("0", "2", "7"))
        old_asset = f"polybridge-mcp-v{old_version}"

        self.assertNotIn(" ".join(("two", "read-only", "tools")), readme)
        self.assertNotIn(" ".join(("two", "tools")), readme)
        self.assertNotIn(" ".join(("Oracle", "API", "key")), readme)
        self.assertNotIn(old_version, readme)
        self.assertNotIn(old_asset, readme)

    def test_readme_search_limits_match_tool_limits(self) -> None:
        from polybridge_mcp_server.tools.search import (
            ANONYMOUS_SEARCH_TOOL_LIMITS,
            API_KEY_SEARCH_TOOL_LIMITS,
        )

        readme = Path("README.md").read_text()

        self.assertIn(
            f"`top_k_per_dimension <= "
            f"{ANONYMOUS_SEARCH_TOOL_LIMITS.max_top_k_per_dimension}`",
            readme,
        )
        self.assertIn(
            f"`top_k_per_dimension <= "
            f"{API_KEY_SEARCH_TOOL_LIMITS.max_top_k_per_dimension}`",
            readme,
        )

    def test_local_mcpb_build_script_outputs_expected_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            subprocess.run(
                [
                    sys.executable,
                    "scripts/build_mcpb.py",
                    "--dist-dir",
                    temporary_directory,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            artifact_path = (
                Path(temporary_directory) / "polybridge-mcp-v0.3.0.mcpb"
            )
            checksum_path = (
                Path(temporary_directory) / "polybridge-mcp-v0.3.0.mcpb.sha256"
            )

            self.assertTrue(artifact_path.is_file())
            self.assertTrue(checksum_path.is_file())
            self.assertIn(artifact_path.name, checksum_path.read_text())

            with zipfile.ZipFile(artifact_path) as package:
                names = set(package.namelist())
                manifest = json.loads(package.read("manifest.json"))
                pyproject = tomllib.loads(package.read("pyproject.toml").decode())

            self.assertEqual(manifest["version"], "0.3.0")
            self.assertEqual(pyproject["project"]["version"], "0.3.0")
            self.assertTrue(
                {
                    "manifest.json",
                    "pyproject.toml",
                    "assets/icon.png",
                    "src/polybridge_mcp_server/server.py",
                    "src/polybridge_mcp_server/tools/rvol.py",
                    "src/polybridge_contracts/search.py",
                }.issubset(names)
            )
            self.assertFalse(any(name.startswith("tests/") for name in names))
            self.assertFalse(any(name.startswith("scripts/") for name in names))
            self.assertFalse(any(name.startswith("dist/") for name in names))
            self.assertFalse(any(name.startswith(".git/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith((".pyc", ".pyo")) for name in names))
