# Mission Control — Agentic OS

Local multi-agent orchestrator with dual control panel for Hermes (messaging bridge) and Claude (LLM processing).

![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green) ![License: MIT](https://img.shields.io/badge/license-MIT-purple)

## Architecture

```
┌─────────────────────────────────────────────┐
│              Dashboard (FastAPI)             │
│   Mission Control · Hermes · Claude · Kanban │
├─────────────────────────────────────────────┤
│            Orquestador (async loop)          │
│     dispatch → run → reap → timeout check    │
├──────────┬──────────┬───────────────────────┤
│  Hermes  │  Claude  │  Echo (test agent)     │
│ messaging│   LLM    │  pipeline validation   │
├──────────┴──────────┴───────────────────────┤
│         Shared Memory (SQLite WAL)           │
│    KV store · Task queue · Event bus         │
└─────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install -r requirements.txt
python run_dashboard.py
# Open http://127.0.0.1:8560
```

## Connecting Claude (LLM)

Set your OpenRouter API key:

```bash
export OPENROUTER_API_KEY="sk-or-..."
# Or configure via dashboard: Claude panel → Configuration → Paste API key
```

## Connecting Hermes (Messaging)

In a separate terminal:

```bash
hermes mcp serve
```

This connects to your Telegram, Discord, Slack, WhatsApp, etc. accounts. Then in the dashboard, Hermes tab will show live conversations and allow you to send messages.

## Orchestrator

```bash
python orquestador.py                                    # run the event loop
python orquestador.py --status                           # print system state
python orquestador.py --submit echo ping '{"msg":"hi"}'  # submit a task
```

## Creating Agents

Add a folder in `agents/<name>/` with an `agent.py`:

```python
MANIFEST = {
    "name": "my-agent",
    "version": "0.1.0",
    "capabilities": ["..."],
}

async def run(ctx, task):
    # ctx.store(), ctx.recall(), ctx.emit(), ctx.submit_task()
    return {"result": "..."}
```

## Dashboard Views

- **Mission Control** — System status + dual Hermes/Claude panel
- **Hermes** — Conversations, channels, send messages, permissions
- **Claude** — Chat interface, model config, task history
- **Kanban** — Task board (Pending → Running → Done/Failed/Timeout)
- **Events** — Filterable event stream

## License

MIT
