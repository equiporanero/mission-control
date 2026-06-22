"""AgentContext — the handle every agent receives.

Provides scoped access to shared memory, task queue, event bus, and tools
without exposing raw DB connections or global state.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory import Memory


@dataclass
class AgentContext:
    agent_id: str
    memory: "Memory"
    logger: logging.Logger = field(init=False)

    def __post_init__(self):
        self.logger = logging.getLogger(f"agent.{self.agent_id}")

    # ── Scoped memory (namespace = agent_id) ──

    def store(self, key: str, value: Any) -> None:
        self.memory.put(self.agent_id, key, value)

    def recall(self, key: str, default: Any = None) -> Any:
        return self.memory.get(self.agent_id, key, default)

    def forget(self, key: str) -> bool:
        return self.memory.delete(self.agent_id, key)

    # ── Global memory (shared namespace) ──

    def shared_store(self, key: str, value: Any) -> None:
        self.memory.put("__global__", key, value)

    def shared_recall(self, key: str, default: Any = None) -> Any:
        return self.memory.get("__global__", key, default)

    # ── Task queue ──

    def submit_task(self, target_agent: str, kind: str, payload: Any) -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        self.memory.push_task(task_id, target_agent, kind, payload)
        self.emit("task_submitted", {"task_id": task_id, "target": target_agent, "kind": kind})
        return task_id

    def claim_next(self) -> dict | None:
        return self.memory.claim_task(self.agent_id)

    def finish_task(self, task_id: str, result: Any, status: str = "done") -> None:
        self.memory.complete_task(task_id, result, status)
        self.emit("task_completed", {"task_id": task_id, "status": status})

    # ── Events ──

    def emit(self, kind: str, data: Any = None) -> None:
        self.memory.emit(self.agent_id, kind, data)
