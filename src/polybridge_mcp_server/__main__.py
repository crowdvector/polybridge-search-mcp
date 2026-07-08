"""CLI entrypoint for the PolyBridge MCP server."""

from polybridge_mcp_server.server import create_server


def main() -> None:
    create_server().run("stdio")


if __name__ == "__main__":
    main()
