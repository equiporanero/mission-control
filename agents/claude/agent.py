"""Claude Agent — LLM processing via OpenRouter or Anthropic API.

Capabilities:
  - Process messages routed from Hermes (or any agent)
  - Generate responses using Claude models
  - Optionally reply back through Hermes

Reads API key from shared memory (namespace __secrets__) or env var.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AgentContext

MANIFEST = {
    "name": "claude",
    "version": "0.1.0",
    "description": "LLM processing — generates responses via Claude API",
    "capabilities": ["llm", "process_message", "generate", "summarize", "reply"],
    "color": "purple",
    "icon": "◆",
}

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"


async def run(ctx: "AgentContext", task: dict) -> Any:
    kind = task["kind"]
    payload = task["payload"]

    if kind == "process_message":
        message = payload.get("message", "")
        platform = payload.get("platform", "unknown")
        sender = payload.get("from", "unknown")
        session_key = payload.get("session_key", "")

        ctx.emit("processing", {
            "message_preview": message[:100],
            "platform": platform,
            "from": sender,
        })

        response = await _call_llm(ctx, message)

        if payload.get("auto_reply") and session_key:
            ctx.submit_task("hermes", "send_message", {
                "target": f"{platform}:{session_key}",
                "message": response,
            })
            ctx.emit("auto_replied", {"platform": platform, "to": sender})

        return {
            "status": "processed",
            "input": message[:200],
            "output": response[:500],
            "model": _get_model(ctx),
        }

    elif kind == "generate":
        prompt = payload.get("prompt", "")
        ctx.emit("generating", {"prompt_preview": prompt[:100]})
        response = await _call_llm(ctx, prompt)
        return {"status": "generated", "output": response, "model": _get_model(ctx)}

    elif kind == "summarize":
        text = payload.get("text", "")
        prompt = f"Summarize the following concisely:\n\n{text}"
        response = await _call_llm(ctx, prompt)
        return {"status": "summarized", "output": response, "model": _get_model(ctx)}

    else:
        ctx.logger.warning("Unknown task kind: %s", kind)
        return {"status": "unknown_kind", "kind": kind}


def _get_model(ctx: "AgentContext") -> str:
    return ctx.recall("model") or DEFAULT_MODEL


def _get_api_key(ctx: "AgentContext") -> str | None:
    key = ctx.memory.get("__secrets__", "openrouter_api_key")
    if key:
        return key
    return os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


async def _call_llm(ctx: "AgentContext", message: str) -> str:
    """Call LLM via OpenRouter (httpx). Falls back to mock if no API key."""
    api_key = _get_api_key(ctx)

    if not api_key:
        ctx.logger.info("No API key configured — returning mock response")
        await asyncio.sleep(0.2)
        return f"[mock] Processed: {message[:100]}..."

    try:
        import httpx
    except ImportError:
        ctx.logger.warning("httpx not installed — returning mock response")
        return f"[mock-no-httpx] {message[:100]}..."

    model = _get_model(ctx)
    url = "https://openrouter.ai/api/v1/chat/completions"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json={
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "max_tokens": 1024,
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
