"""Hermes Agent — Multi-agent hub: real messaging bridge + MCP management.

Capabilities:
  - Messaging: Poll conversations from Telegram, Discord, Slack, WhatsApp (via Hermes MCP)
  - Send messages to any connected channel
  - Route incoming messages to other agents
  - MCP Management: Browse Nous catalogue, install/uninstall, toggle, auth flow

This agent is both a message router AND the MCP management control room.
Note: Messaging ops are proxied through the dashboard API which calls Hermes MCP.
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AgentContext

MANIFEST = {
    "name": "hermes",
    "version": "0.3.0",
    "description": "Multi-agent hub — real Hermes MCP bridge + MCP catalogue management",
    "capabilities": [
        "messaging",
        "channels",
        "events",
        "send",
        "conversations",
        "mcp_browse",
        "mcp_install",
        "mcp_uninstall",
        "mcp_toggle",
        "mcp_auth",
    ],
    "color": "green",
    "icon": "▲",
}


async def run(ctx: "AgentContext", task: dict) -> Any:
    kind = task["kind"]
    payload = task["payload"]

    # ── Messaging ──
    if kind == "send_message":
        ctx.emit("send_message", {"target": payload["target"], "message": payload["message"]})
        return {"status": "queued", "target": payload["target"]}

    elif kind == "poll_events":
        cursor = payload.get("cursor", 0)
        ctx.emit("poll_events", {"cursor": cursor})
        return {"status": "polled", "cursor": cursor}

    elif kind == "route_message":
        target_agent = payload.get("route_to", "claude")
        task_id = ctx.submit_task(target_agent, "process_message", {
            "from": payload.get("from", "unknown"),
            "platform": payload.get("platform", "unknown"),
            "message": payload.get("message", ""),
            "session_key": payload.get("session_key", ""),
        })
        ctx.emit("message_routed", {"task_id": task_id, "to": target_agent})
        return {"status": "routed", "task_id": task_id, "to": target_agent}

    # ── MCP Management ──
    elif kind == "mcp_browse":
        # Browse Nous-approved MCP catalogue
        from core.mcp_manager import MCPManager
        mgr = MCPManager()
        query = payload.get("query", "")
        results = mgr.browse_catalogue(query)
        ctx.emit("mcp_browse", {"query": query, "count": len(results)})
        return {"status": "browse", "results": results}

    elif kind == "mcp_list":
        from core.mcp_manager import MCPManager
        mgr = MCPManager()
        installed = mgr.list_installed()
        ctx.emit("mcp_list", {"count": len(installed)})
        return {"status": "listed", "installed": installed}

    elif kind == "mcp_install":
        from core.mcp_manager import MCPManager
        mgr = MCPManager()
        name = payload.get("name")
        result = mgr.install(name)
        ctx.emit("mcp_installed", {"name": name, "success": "error" not in result})
        return result

    elif kind == "mcp_uninstall":
        from core.mcp_manager import MCPManager
        mgr = MCPManager()
        name = payload.get("name")
        result = mgr.uninstall(name)
        ctx.emit("mcp_uninstalled", {"name": name, "success": "error" not in result})
        return result

    elif kind == "mcp_toggle":
        from core.mcp_manager import MCPManager
        mgr = MCPManager()
        name = payload.get("name")
        enabled = payload.get("enabled", True)
        result = mgr.toggle(name, enabled)
        ctx.emit("mcp_toggled", {"name": name, "enabled": enabled})
        return result

    elif kind == "mcp_auth":
        from core.mcp_manager import MCPManager
        mgr = MCPManager()
        name = payload.get("name")
        action = payload.get("action", "check")
        if action == "check":
            result = mgr.auth_status(name)
        elif action == "start":
            result = mgr.start_auth(name)
        elif action == "complete":
            token = payload.get("token", "")
            result = mgr.complete_auth(name, token)
        else:
            result = {"error": f"unknown auth action: {action}"}
        ctx.emit("mcp_auth", {"name": name, "action": action})
        return result

    else:
        ctx.logger.warning("Unknown task kind: %s", kind)
        return {"status": "unknown_kind", "kind": kind}
