"""MCP ツールの登録。"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from forms_mcp.google_clients import GoogleServices
from forms_mcp.tools import drive, forms, responses, watches


def register_all(mcp: MCPServer, services: GoogleServices, *, pubsub_topic: str | None = None) -> None:
    forms.register(mcp, services)
    responses.register(mcp, services)
    watches.register(mcp, services, default_topic=pubsub_topic)
    drive.register(mcp, services)
