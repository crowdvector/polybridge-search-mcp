import os
import unittest
from unittest.mock import patch


class PolybridgeMCPSmokeTest(unittest.IsolatedAsyncioTestCase):
    def test_package_imports(self) -> None:
        import polybridge_mcp_server

        self.assertEqual(polybridge_mcp_server.__version__, "0.2.7")

    async def test_server_registers_current_tools_only(self) -> None:
        from polybridge_mcp_server.config import PolybridgeMCPConfig
        from polybridge_mcp_server.server import create_server

        mcp_server = create_server(config=PolybridgeMCPConfig())
        tool_names = {tool.name for tool in await mcp_server.list_tools()}

        self.assertIn("polybridge_search", tool_names)
        self.assertIn("polybridge_forecast", tool_names)
        self.assertFalse(any("rvol" in name.lower() for name in tool_names))

    def test_api_key_env_handling_imports_without_printing_values(self) -> None:
        from polybridge_mcp_server.config import PolybridgeMCPConfig

        with patch.dict(os.environ, {"POLYBRIDGE_API_KEY": " test-key "}, clear=False):
            config = PolybridgeMCPConfig.from_env()

        self.assertEqual(config.api_key, "test-key")
        self.assertTrue(config.has_api_key)
