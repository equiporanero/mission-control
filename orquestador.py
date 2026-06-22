"""
Orquestador Central — Hermes Core

Main event loop that:
  1. Discovers and registers agents from agents/
  2. Dispatches pending tasks to agent coroutines
  3. Enforces concurrency limits and timeouts
  4. Exposes system state via the Memory API (consumed by the dashboard)

Usage:
    python orquestador.py                  # run the loop
    python orquestador.py --status         # print current state and exit
    python orquestador.py --submit <agent> <kind> '<json_payload>'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import (
    AGENTS_DIR,
    DB_PATH,
    LOGS_DIR,
    MAX_CONCURRENT_AGENTS,
    TASK_TIMEOUT_SEC,
    TICK_INTERVAL_SEC,
)
from core.context import AgentContext
from core.memory import Memory
from core.registry import Registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "orquestador.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("orquestador")


class Orquestador:
    def __init__(self):
        self.memory = Memory(DB_PATH)
        self.registry = Registry()
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._shutdown = asyncio.Event()

    # ── Lifecycle ──

    async def start(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)

        found = self.registry.discover(AGENTS_DIR)
        log.info("Discovered %d agents: %s", len(found), found)

        self.memory.emit("orquestador", "started", {
            "agents": found,
            "max_concurrent": MAX_CONCURRENT_AGENTS,
        })
        self._update_system_state("running")

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._request_shutdown())

        log.info("Mission Control online — tick=%.1fs, max_agents=%d",
                 TICK_INTERVAL_SEC, MAX_CONCURRENT_AGENTS)
        await self._loop()

    def _request_shutdown(self):
        log.info("Shutdown requested")
        self._shutdown.set()

    async def _loop(self):
        while not self._shutdown.is_set():
            self._reap_finished()
            await self._dispatch_pending()
            self._check_timeouts()
            self._update_system_state("running")

            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=TICK_INTERVAL_SEC
                )
            except asyncio.TimeoutError:
                pass

        await self._drain()
        self._update_system_state("stopped")
        self.memory.emit("orquestador", "stopped")
        log.info("Mission Control offline")

    # ── Dispatch ──

    async def _dispatch_pending(self):
        for agent_name in self.registry.names():
            if len(self._running_tasks) >= MAX_CONCURRENT_AGENTS:
                break

            agent_reg = self.registry.get(agent_name)
            ctx = AgentContext(agent_id=agent_name, memory=self.memory)
            task_data = ctx.claim_next()

            if task_data is None:
                continue

            task_id = task_data["id"]
            if task_id in self._running_tasks:
                continue

            log.info("Dispatching task %s → %s (kind=%s)",
                     task_id, agent_name, task_data["kind"])
            self.memory.emit("orquestador", "task_dispatched", {
                "task_id": task_id, "agent": agent_name,
            })

            coro = self._run_agent(agent_reg.run_fn, ctx, task_data)
            self._running_tasks[task_id] = asyncio.create_task(coro)

    async def _run_agent(self, run_fn, ctx: AgentContext, task_data: dict):
        task_id = task_data["id"]
        try:
            result = await asyncio.wait_for(
                run_fn(ctx, task_data), timeout=TASK_TIMEOUT_SEC
            )
            ctx.finish_task(task_id, result, "done")
            log.info("Task %s completed", task_id)
        except asyncio.TimeoutError:
            ctx.finish_task(task_id, {"error": "timeout"}, "timeout")
            log.warning("Task %s timed out after %ds", task_id, TASK_TIMEOUT_SEC)
        except Exception as exc:
            ctx.finish_task(task_id, {"error": str(exc)}, "failed")
            log.error("Task %s failed: %s", task_id, exc, exc_info=True)

    # ── Housekeeping ──

    def _reap_finished(self):
        done = [tid for tid, t in self._running_tasks.items() if t.done()]
        for tid in done:
            self._running_tasks.pop(tid, None)

    def _check_timeouts(self):
        now = time.time()
        stale = self.memory.list_tasks(status="running")
        for t in stale:
            if now - t["updated_at"] > TASK_TIMEOUT_SEC * 2:
                self.memory.complete_task(t["id"], {"error": "stale"}, "timeout")
                log.warning("Reaped stale task %s", t["id"])

    async def _drain(self):
        if not self._running_tasks:
            return
        log.info("Draining %d running tasks...", len(self._running_tasks))
        await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
        self._running_tasks.clear()

    # ── State ──

    def _update_system_state(self, status: str):
        self.memory.put("__system__", "state", {
            "status": status,
            "agents_registered": self.registry.names(),
            "tasks_running": list(self._running_tasks.keys()),
            "ts": time.time(),
        })

    def print_status(self):
        state = self.memory.get("__system__", "state", {})
        tasks = self.memory.list_tasks()
        agents = self.registry.list_agents()

        print("\n═══ Mission Control Status ═══")
        print(f"  State:  {state.get('status', 'unknown')}")
        print(f"  Agents: {len(agents)} registered")
        for a in agents:
            print(f"    • {a.name} v{a.version} — {a.capabilities}")
        print(f"  Tasks:  {len(tasks)} total")
        for t in tasks[:10]:
            print(f"    [{t['status']:>8}] {t['id']} → {t['agent_id']} ({t['kind']})")
        recent = self.memory.events_since(time.time() - 3600, limit=10)
        print(f"  Events (last hour): {len(recent)}")
        for e in recent[:5]:
            print(f"    {e['src']:>16} | {e['kind']}")
        print()


# ── CLI ──

def cli():
    parser = argparse.ArgumentParser(description="Mission Control — Hermes Core")
    parser.add_argument("--status", action="store_true", help="Print state and exit")
    parser.add_argument("--submit", nargs=3, metavar=("AGENT", "KIND", "PAYLOAD"),
                        help="Submit a task and exit")
    args = parser.parse_args()

    orc = Orquestador()

    if args.status:
        orc.registry.discover(AGENTS_DIR)
        orc.print_status()
        return

    if args.submit:
        agent, kind, payload_str = args.submit
        import uuid
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        orc.memory.push_task(task_id, agent, kind, json.loads(payload_str))
        orc.memory.emit("cli", "task_submitted", {
            "task_id": task_id, "agent": agent, "kind": kind,
        })
        print(f"Submitted: {task_id} → {agent} ({kind})")
        return

    asyncio.run(orc.start())


if __name__ == "__main__":
    cli()
