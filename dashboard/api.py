"""Dashboard API — FastAPI backend for Mission Control dual panel (Hermes + Claude)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH, AGENTS_DIR, DASHBOARD_HOST, DASHBOARD_PORT
from core.memory import Memory
from core.registry import Registry
from core.mcp_manager import MCPManager

app = FastAPI(title="Mission Control")
memory = Memory(DB_PATH)
registry = Registry()
registry.discover(AGENTS_DIR)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ── System State ──

@app.get("/api/state")
async def get_state():
    state = memory.get("__system__", "state", {})
    agents = []
    for m in registry.list_agents():
        running = memory.list_tasks(status="running", agent_id=m.name)
        pending = memory.list_tasks(status="pending", agent_id=m.name)
        done = memory.list_tasks(status="done", agent_id=m.name)
        agents.append({
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "capabilities": m.capabilities,
            "tasks_running": len(running),
            "tasks_pending": len(pending),
            "tasks_done": len(done),
            "status": "online" if m.name in state.get("agents_registered", []) else "offline",
        })
    return {"system": state, "agents": agents, "ts": time.time()}


@app.get("/api/tasks")
async def get_tasks(status: str | None = None, agent_id: str | None = None, limit: int = 50):
    tasks = memory.list_tasks(status=status, agent_id=agent_id)[:limit]
    for t in tasks:
        for field in ("payload", "result"):
            if isinstance(t.get(field), str):
                try:
                    t[field] = json.loads(t[field])
                except (json.JSONDecodeError, TypeError):
                    pass
    return {"tasks": tasks, "total": len(tasks)}


@app.get("/api/events")
async def get_events(since: float = 0, limit: int = 50, src: str | None = None):
    events = memory.events_since(since, limit=limit)
    if src:
        events = [e for e in events if src in e.get("src", "")]
    return {"events": events}


@app.get("/api/memory/{ns}")
async def get_memory_ns(ns: str):
    data = memory.list_ns(ns)
    return {"namespace": ns, "entries": data}


@app.post("/api/tasks")
async def create_task(request: Request):
    body = await request.json()
    import uuid
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    memory.push_task(
        task_id,
        body["agent_id"],
        body.get("kind", "manual"),
        body.get("payload", {}),
    )
    memory.emit("dashboard", "task_created", {"task_id": task_id, "agent": body["agent_id"]})
    return {"task_id": task_id}


# ── Hermes Bridge (proxies to Hermes MCP via CLI) ──

def _hermes_mcp(tool: str, args: dict) -> dict:
    """Call a Hermes MCP tool via the hermes CLI (stdio protocol)."""
    try:
        cmd = ["hermes", "mcp", "call", tool, json.dumps(args)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"error": result.stderr.strip() or "empty response", "raw": result.stdout[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        return {"error": "hermes CLI not found"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/hermes/channels")
async def hermes_channels(platform: str | None = None):
    args = {}
    if platform:
        args["platform"] = platform
    return _hermes_mcp("channels_list", args)


@app.get("/api/hermes/conversations")
async def hermes_conversations(platform: str | None = None, limit: int = 20, search: str | None = None):
    args = {"limit": limit}
    if platform:
        args["platform"] = platform
    if search:
        args["search"] = search
    return _hermes_mcp("conversations_list", args)


@app.get("/api/hermes/messages/{session_key}")
async def hermes_messages(session_key: str, limit: int = 30):
    return _hermes_mcp("messages_read", {"session_key": session_key, "limit": limit})


@app.post("/api/hermes/send")
async def hermes_send(request: Request):
    body = await request.json()
    result = _hermes_mcp("messages_send", {
        "target": body["target"],
        "message": body["message"],
    })
    memory.emit("hermes", "message_sent", {"target": body["target"], "preview": body["message"][:100]})
    return result


@app.get("/api/hermes/events")
async def hermes_events(after_cursor: int = 0, limit: int = 20):
    return _hermes_mcp("events_poll", {"after_cursor": after_cursor, "limit": limit})


@app.get("/api/hermes/permissions")
async def hermes_permissions():
    return _hermes_mcp("permissions_list_open", {})


# ── Claude Agent Control ──

@app.post("/api/claude/generate")
async def claude_generate(request: Request):
    body = await request.json()
    import uuid
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    memory.push_task(task_id, "claude", "generate", {"prompt": body["prompt"]})
    memory.emit("dashboard", "claude_generate", {"task_id": task_id, "prompt_preview": body["prompt"][:100]})
    return {"task_id": task_id}


@app.post("/api/claude/process")
async def claude_process(request: Request):
    body = await request.json()
    import uuid
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    memory.push_task(task_id, "claude", "process_message", {
        "message": body["message"],
        "from": body.get("from", "dashboard"),
        "platform": body.get("platform", "web"),
        "auto_reply": body.get("auto_reply", False),
        "session_key": body.get("session_key", ""),
    })
    memory.emit("dashboard", "claude_process", {"task_id": task_id})
    return {"task_id": task_id}


@app.get("/api/claude/config")
async def claude_config():
    model = memory.get("claude", "model") or "anthropic/claude-sonnet-4-20250514"
    has_key = bool(memory.get("__secrets__", "openrouter_api_key"))
    return {"model": model, "has_api_key": has_key}


@app.post("/api/claude/config")
async def claude_config_update(request: Request):
    body = await request.json()
    if "model" in body:
        memory.put("claude", "model", body["model"])
    if "api_key" in body and body["api_key"]:
        memory.put("__secrets__", "openrouter_api_key", body["api_key"])
    memory.emit("dashboard", "claude_config_updated", {"model": body.get("model", "unchanged")})
    return {"status": "updated"}


# ── MCP Management (via Hermes) ──

mcp_mgr = MCPManager()


@app.get("/api/mcp/catalogue")
async def mcp_browse(query: str = ""):
    results = mcp_mgr.browse_catalogue(query)
    memory.emit("hermes", "mcp_browse", {"query": query, "count": len(results)})
    return {"results": results}


@app.get("/api/mcp/installed")
async def mcp_list():
    installed = mcp_mgr.list_installed()
    return {"installed": installed}


@app.post("/api/mcp/install")
async def mcp_install(request: Request):
    body = await request.json()
    result = mcp_mgr.install(body["name"])
    memory.emit("hermes", "mcp_installed", {"name": body["name"], "success": "error" not in result})
    return result


@app.post("/api/mcp/uninstall")
async def mcp_uninstall(request: Request):
    body = await request.json()
    result = mcp_mgr.uninstall(body["name"])
    memory.emit("hermes", "mcp_uninstalled", {"name": body["name"], "success": "error" not in result})
    return result


@app.post("/api/mcp/toggle")
async def mcp_toggle(request: Request):
    body = await request.json()
    result = mcp_mgr.toggle(body["name"], body.get("enabled", True))
    memory.emit("hermes", "mcp_toggled", {"name": body["name"], "enabled": body.get("enabled")})
    return result


@app.post("/api/mcp/auth")
async def mcp_auth(request: Request):
    body = await request.json()
    name = body["name"]
    action = body.get("action", "check")
    if action == "check":
        result = mcp_mgr.auth_status(name)
    elif action == "start":
        result = mcp_mgr.start_auth(name)
    elif action == "complete":
        result = mcp_mgr.complete_auth(name, body.get("token", ""))
    else:
        result = {"error": f"unknown action: {action}"}
    memory.emit("hermes", "mcp_auth", {"name": name, "action": action})
    return result


# ── SSE Stream ──

@app.get("/api/stream")
async def event_stream():
    async def generate():
        last_ts = time.time()
        while True:
            await asyncio.sleep(2)
            events = memory.events_since(last_ts, limit=20)
            state = memory.get("__system__", "state", {})
            if events:
                last_ts = max(e["ts"] for e in events)
            payload = json.dumps({"events": events, "system": state, "ts": time.time()})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main():
    import os
    import uvicorn
    port = int(os.environ.get("PORT", DASHBOARD_PORT))
    uvicorn.run(app, host=DASHBOARD_HOST, port=port)


if __name__ == "__main__":
    main()
