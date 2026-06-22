"""Echo agent — minimal example that validates the agent contract.

Drop tasks into this agent to test the pipeline end-to-end.
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AgentContext

MANIFEST = {
    "name": "echo",
    "version": "0.1.0",
    "description": "Returns the payload it receives — for pipeline testing",
    "capabilities": ["echo", "ping"],
}


async def run(ctx: "AgentContext", task: dict) -> Any:
    ctx.logger.info("Echo received: %s", task["kind"])
    await asyncio.sleep(0.1)
    ctx.store("last_echo", task["payload"])
    ctx.emit("echo_processed", {"input": task["payload"]})
    return {"echoed": task["payload"]}
