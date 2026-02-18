"""
Musical Intelligence MCP Server package.

Exposes the platform's musical capabilities via the Model Context Protocol.
Any MCP-compatible client (Claude Desktop, future DAW plugins, OpenDock hardware)
can query the same intelligence brain through this package.

Architecture:
    server.py    — FastMCP instance + startup entrypoint
    handlers.py  — Tool/resource/prompt handler implementations
    schemas.py   — Shared constants, URI prefixes, structured log types
    transport.py — Transport configuration (stdio / SSE) + logging setup
"""
