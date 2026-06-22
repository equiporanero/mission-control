"""Hermes MCP Bridge — wrapper para invocar Hermes desde el dashboard.

Este módulo actúa como intermediario entre el dashboard y el Hermes MCP.
Permite enviar/recibir mensajes en plataformas reales.
"""

from __future__ import annotations

import subprocess
import json
import logging
from typing import Any

log = logging.getLogger("hermes-bridge")


class HermesBridge:
    """Wrapper que invoca herramientas Hermes MCP vía subprocess."""

    def __init__(self):
        self.mcp_available = self._check_mcp()

    def _check_mcp(self) -> bool:
        """Verifica si Hermes MCP está disponible."""
        try:
            result = subprocess.run(
                ["hermes", "mcp", "call", "channels_list", "{}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except FileNotFoundError:
            log.warning("Hermes CLI not found. Install with: pip install hermes-agent")
            return False
        except Exception as e:
            log.warning("Hermes MCP check failed: %s", e)
            return False

    def _call_mcp(self, tool: str, args: dict) -> dict:
        """Invoca una herramienta MCP de Hermes."""
        if not self.mcp_available:
            return {"error": "Hermes MCP not available", "hint": "hermes mcp serve"}

        try:
            result = subprocess.run(
                ["hermes", "mcp", "call", tool, json.dumps(args)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
            return {"error": result.stderr.strip() or "empty response"}
        except subprocess.TimeoutExpired:
            return {"error": "Hermes MCP timeout"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid response: {e}"}
        except Exception as e:
            return {"error": str(e)}

    # ── Channels ──
    def channels_list(self, platform: str | None = None) -> dict:
        """List available channels."""
        args = {}
        if platform:
            args["platform"] = platform
        return self._call_mcp("channels_list", args)

    # ── Conversations ──
    def conversations_list(
        self, platform: str | None = None, limit: int = 50, search: str | None = None
    ) -> dict:
        """List conversations."""
        args = {"limit": limit}
        if platform:
            args["platform"] = platform
        if search:
            args["search"] = search
        return self._call_mcp("conversations_list", args)

    def conversation_get(self, session_key: str) -> dict:
        """Get one conversation details."""
        return self._call_mcp("conversation_get", {"session_key": session_key})

    # ── Messages ──
    def messages_read(self, session_key: str, limit: int = 30) -> dict:
        """Read messages from a conversation."""
        return self._call_mcp("messages_read", {"session_key": session_key, "limit": limit})

    def messages_send(self, target: str, message: str) -> dict:
        """Send a message to a platform."""
        return self._call_mcp("messages_send", {"target": target, "message": message})

    # ── Events ──
    def events_poll(
        self, after_cursor: int = 0, session_key: str | None = None, limit: int = 20
    ) -> dict:
        """Poll for events."""
        args = {"after_cursor": after_cursor, "limit": limit}
        if session_key:
            args["session_key"] = session_key
        return self._call_mcp("events_poll", args)

    def events_wait(
        self, after_cursor: int = 0, session_key: str | None = None, timeout_ms: int = 30000
    ) -> dict:
        """Wait for next event (long-poll)."""
        args = {"after_cursor": after_cursor, "timeout_ms": timeout_ms}
        if session_key:
            args["session_key"] = session_key
        return self._call_mcp("events_wait", args)

    # ── Permissions ──
    def permissions_list_open(self) -> dict:
        """List pending approvals."""
        return self._call_mcp("permissions_list_open", {})

    def permissions_respond(self, id: str, decision: str) -> dict:
        """Respond to an approval."""
        return self._call_mcp("permissions_respond", {"id": id, "decision": decision})
