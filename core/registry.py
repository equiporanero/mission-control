"""Agent registry — discovers, loads, and tracks agent modules.

Each agent lives in agents/<name>/ and exposes an agent.py with:
    MANIFEST = {"name": ..., "version": ..., "capabilities": [...]}
    async def run(ctx: AgentContext) -> None: ...
"""

import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

log = logging.getLogger("mission-control.registry")


@dataclass
class AgentManifest:
    name: str
    version: str = "0.1.0"
    capabilities: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class RegisteredAgent:
    manifest: AgentManifest
    run_fn: Callable[..., Coroutine]
    module_path: Path


class Registry:
    def __init__(self):
        self._agents: dict[str, RegisteredAgent] = {}

    def discover(self, agents_dir: Path) -> list[str]:
        found = []
        if not agents_dir.is_dir():
            return found

        for child in sorted(agents_dir.iterdir()):
            agent_file = child / "agent.py"
            if not agent_file.is_file():
                continue
            name = child.name
            try:
                self._load_agent(name, agent_file)
                found.append(name)
            except Exception as e:
                log.warning("Failed to load agent %s: %s", name, e)
        return found

    def _load_agent(self, name: str, path: Path) -> None:
        spec = importlib.util.spec_from_file_location(f"agents.{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        raw: dict[str, Any] = getattr(mod, "MANIFEST", {})
        manifest = AgentManifest(
            name=raw.get("name", name),
            version=raw.get("version", "0.1.0"),
            capabilities=raw.get("capabilities", []),
            description=raw.get("description", ""),
        )

        run_fn = getattr(mod, "run", None)
        if run_fn is None:
            raise ValueError(f"Agent {name} missing async def run(ctx)")

        self._agents[name] = RegisteredAgent(
            manifest=manifest, run_fn=run_fn, module_path=path
        )
        log.info("Registered agent: %s v%s", manifest.name, manifest.version)

    def get(self, name: str) -> RegisteredAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[AgentManifest]:
        return [a.manifest for a in self._agents.values()]

    def names(self) -> list[str]:
        return list(self._agents.keys())
