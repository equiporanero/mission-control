"""Hermes Agent — bridge to messaging platforms via Hermes MCP.

Capabilities:
  - Poll conversations and events from Telegram, Discord, Slack, WhatsApp, etc.
  - Send messages to any connected channel
  - Route incoming messages to other agents for processing

This agent is designed to be called by the orchestrator OR queried
directly by the dashboard API for live status.
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AgentContext

MANIFEST = {
    "name": "hermes",
    "version": "0.1.0",
    "description": "Messaging bridge — Telegram, Discord, Slack, WhatsApp via Hermes",
    "capabilities": ["messaging", "channels", "events", "send", "conversations"],
    "color": "green",
    "icon": "▲",
}


async def run(ctx: "AgentContext", task: dict) -> Any:
    kind = task["kind"]
    payload = task["payload"]

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

    else:
        ctx.logger.warning("Unknown task kind: %s", kind)
        return {"status": "unknown_kind", "kind": kind}
