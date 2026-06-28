"""
₿RS Signals — MCP Server
========================
Model Context Protocol server wrapping the BRS Signals API.

Quick start:
    export BRS_API_KEY=va_yourkey_here

    # stdio (for Claude Desktop, Cursor, etc.)
    python mcp_brs/server.py
    # or: python -m mcp_brs

    # SSE / HTTP (for remote agents, teams)
    python mcp_brs/server.py --transport sse --port 8080

Install deps:
    pip install mcp httpx

Configure your MCP client (Claude Desktop, Cursor, etc.) with:
    {
        "mcpServers": {
            "brs-signals": {
                "command": "python3",
                "args": ["mcp_brs/server.py"],
                "cwd": "/path/to/4.BRS-Signals",
                "env": {
                    "BRS_API_KEY": "va_yourkey_here"
                }
            }
        }
    }

For remote/SSE mode, use a URL-based config instead:
    {
        "mcpServers": {
            "brs-signals": {
                "url": "http://your-server:8080/sse"
            }
        }
    }
"""

from mcp_brs.server import mcp, main

__all__ = ["mcp", "main"]
