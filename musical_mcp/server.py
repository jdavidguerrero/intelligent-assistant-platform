"""
Musical Intelligence MCP Server — entrypoint.

This is the main entrypoint for the MCP server. It:
    1. Configures logging (stderr only — stdout is reserved for JSON-RPC)
    2. Creates the FastMCP instance with musical domain identity
    3. Registers all handlers (tools, resources, prompts) from handlers.py
    4. Starts the transport (stdio by default, SSE via MCP_TRANSPORT=sse)

Running:
    # Via Python (development)
    python -m musical_mcp.server

    # Via project venv (Claude Desktop config)
    /path/to/.venv/bin/python -m musical_mcp.server

    # SSE transport (future cloud / OpenDock)
    MCP_TRANSPORT=sse python -m musical_mcp.server

Claude Desktop config (~/.../claude_desktop_config.json):
    {
        "mcpServers": {
            "musical-intelligence": {
                "command": "/absolute/path/.venv/bin/python",
                "args": ["-m", "musical_mcp.server"],
                "cwd": "/absolute/path/to/intelligent-assistant-platform",
                "env": {
                    "API_BASE_URL": "http://localhost:8000",
                    "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/db"
                }
            }
        }
    }
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from musical_mcp.handlers import register_all
from musical_mcp.transport import configure_logging, get_transport_mode

# ---------------------------------------------------------------------------
# Logging — configure FIRST before any other imports that might log
# ---------------------------------------------------------------------------

configure_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

# Server identity: used in MCP client UIs as the connector name
_SERVER_NAME = "musical-intelligence"
_SERVER_VERSION = "1.0.0"

mcp = FastMCP(
    _SERVER_NAME,
    instructions=(
        "Musical Intelligence Server — access your music production knowledge base, "
        "log practice sessions, analyze tracks, suggest chord progressions, and "
        "plan DJ sets. All musical tools from the intelligent-assistant-platform "
        "are available here. Use search_production_knowledge for 'how to' questions. "
        "Use log_practice_session after finishing a practice session. "
        "Use prepare_for_set before a DJ performance."
    ),
)

# Register all handlers onto the mcp instance
register_all(mcp)

logger.info(
    "Musical Intelligence MCP Server v%s initialized — %d tools registered",
    _SERVER_VERSION,
    len(mcp._tool_manager._tools),  # type: ignore[attr-defined]
)

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Start the MCP server.

    Transport is determined by MCP_TRANSPORT env var:
        stdio (default) — for Claude Desktop and local tools
        sse             — for future cloud / OpenDock deployment
    """
    transport = get_transport_mode()
    logger.info("Starting Musical Intelligence MCP Server (transport=%s)", transport)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
