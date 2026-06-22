"""MCP Manager — browse, install, toggle, manage Model Context Protocol servers.

Integrates with local MCP ecosystem: discovery, metadata, enable/disable,
auth state, and one-click install.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class MCPServer:
    name: str
    description: str
    protocol: str  # stdio, http, sse
    enabled: bool
    version: str = "0.1.0"
    auth_required: bool = False
    auth_status: str = "none"  # none, pending, authorized
    capabilities: list[str] = None
    install_cmd: str = ""

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "protocol": self.protocol,
            "enabled": self.enabled,
            "version": self.version,
            "auth_required": self.auth_required,
            "auth_status": self.auth_status,
            "capabilities": self.capabilities or [],
            "install_cmd": self.install_cmd,
        }


# Nous-approved MCP catalogue (curated + installable)
NOUS_CATALOGUE = [
    MCPServer(
        name="linear",
        description="GitHub Linear issues, projects, and comments.",
        protocol="stdio",
        enabled=False,
        capabilities=["read", "write", "oauth"],
        install_cmd="npm install -g @modelcontextprotocol/server-linear",
    ),
    MCPServer(
        name="github",
        description="GitHub PR/issue management + repo browsing.",
        protocol="stdio",
        enabled=False,
        capabilities=["read", "write", "oauth"],
        install_cmd="npm install -g @modelcontextprotocol/server-github",
    ),
    MCPServer(
        name="stripe",
        description="Stripe charges, customers, webhooks.",
        protocol="http",
        enabled=False,
        capabilities=["read", "oauth"],
        install_cmd="docker pull mcps/stripe; docker run -e STRIPE_API_KEY=$KEY mcps/stripe",
    ),
    MCPServer(
        name="n8n",
        description="n8n workflow automation — create, run, trigger.",
        protocol="http",
        enabled=False,
        capabilities=["read", "write", "oauth"],
        install_cmd="npm install -g @modelcontextprotocol/server-n8n",
    ),
    MCPServer(
        name="filesystem",
        description="Local filesystem read/write with safety constraints.",
        protocol="stdio",
        enabled=False,
        capabilities=["read", "write"],
        install_cmd="npm install -g @modelcontextprotocol/server-filesystem",
    ),
    MCPServer(
        name="postgres",
        description="PostgreSQL queries, schema introspection.",
        protocol="stdio",
        enabled=False,
        capabilities=["read", "write"],
        install_cmd="npm install -g @modelcontextprotocol/server-postgres",
    ),
    MCPServer(
        name="slack",
        description="Slack messages, channels, users.",
        protocol="stdio",
        enabled=False,
        capabilities=["read", "write", "oauth"],
        install_cmd="npm install -g @modelcontextprotocol/server-slack",
    ),
    MCPServer(
        name="gmail",
        description="Gmail read/send with OAuth.",
        protocol="stdio",
        enabled=False,
        capabilities=["read", "write", "oauth"],
        install_cmd="npm install -g @modelcontextprotocol/server-gmail",
    ),
]


class MCPManager:
    def __init__(self):
        self.local_servers: dict[str, MCPServer] = {}
        self._init_local()

    def _init_local(self):
        """Discover installed MCPs from system."""
        # In a real implementation, would query system MCPs
        # For now, load from /usr/local/bin, ~/.local/bin, etc.
        pass

    def browse_catalogue(self, query: str = "") -> list[dict]:
        """Browse Nous-approved MCP catalogue."""
        servers = NOUS_CATALOGUE
        if query:
            servers = [
                s
                for s in servers
                if query.lower() in s.name.lower()
                or query.lower() in s.description.lower()
            ]
        return [s.to_dict() for s in servers]

    def list_installed(self) -> list[dict]:
        """List MCPs currently installed + enabled."""
        return [s.to_dict() for s in self.local_servers.values()]

    def install(self, name: str) -> dict:
        """Install an MCP from catalogue."""
        server = next((s for s in NOUS_CATALOGUE if s.name == name), None)
        if not server:
            return {"error": f"MCP '{name}' not found in catalogue"}

        # Dry run for now — real implementation would execute install_cmd
        self.local_servers[name] = MCPServer(
            name=server.name,
            description=server.description,
            protocol=server.protocol,
            enabled=True,
            version=server.version,
            auth_required=server.auth_required,
            capabilities=server.capabilities,
        )
        return {"status": "installed", "name": name, "version": server.version}

    def uninstall(self, name: str) -> dict:
        """Uninstall an MCP."""
        if name not in self.local_servers:
            return {"error": f"MCP '{name}' not installed"}
        del self.local_servers[name]
        return {"status": "uninstalled", "name": name}

    def toggle(self, name: str, enabled: bool) -> dict:
        """Enable/disable an MCP."""
        if name not in self.local_servers:
            return {"error": f"MCP '{name}' not installed"}
        self.local_servers[name].enabled = enabled
        return {"status": "toggled", "name": name, "enabled": enabled}

    def auth_status(self, name: str) -> dict:
        """Check OAuth/auth state for an MCP."""
        if name not in self.local_servers:
            return {"error": f"MCP '{name}' not installed"}
        server = self.local_servers[name]
        return {
            "name": name,
            "auth_required": server.auth_required,
            "auth_status": server.auth_status,
        }

    def start_auth(self, name: str) -> dict:
        """Initiate OAuth flow for an MCP."""
        if name not in self.local_servers:
            return {"error": f"MCP '{name}' not installed"}
        server = self.local_servers[name]
        if not server.auth_required:
            return {"error": f"MCP '{name}' does not require auth"}
        server.auth_status = "pending"
        # Real implementation would open OAuth URL
        return {"status": "auth_pending", "name": name}

    def complete_auth(self, name: str, token: str) -> dict:
        """Complete OAuth for an MCP."""
        if name not in self.local_servers:
            return {"error": f"MCP '{name}' not installed"}
        server = self.local_servers[name]
        server.auth_status = "authorized"
        # Real implementation would validate + store token
        return {"status": "authorized", "name": name}
