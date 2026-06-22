"""Claude Agent — LLM processing via OpenRouter or Anthropic API.

Capabilities:
  - Process messages routed from Hermes (or any agent)
  - Generate responses using Claude models
  - Optionally reply back through Hermes

Reads API key from shared memory (namespace __secrets__) or env var.
Uses OpenRouter API for multi-model access.
"""

from __future__ import annotations

import asyncio
import os
import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AgentContext

MANIFEST = {
    "name": "claude",
    "version": "0.2.0",
    "description": "LLM processing — real Claude via OpenRouter or Anthropic",
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
    stored = ctx.memory.get("__secrets__", "claude_model")
    return stored or DEFAULT_MODEL


def _get_api_key(ctx: "AgentContext") -> str | None:
    key = ctx.memory.get("__secrets__", "openrouter_api_key")
    if key:
        return key
    return os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


async def _call_llm(ctx: "AgentContext", message: str) -> str:
    """Call LLM via OpenRouter. Falls back to mock if no API key."""
    api_key = _get_api_key(ctx)

    if not api_key:
        ctx.logger.info("No API key configured — returning mock response")
        await asyncio.sleep(0.5)
        return f"[Mock response from Claude]\n\nYou asked: {message[:80]}...\n\n[To use real Claude, set OPENROUTER_API_KEY env var or configure via dashboard]"

    try:
        import httpx
    except ImportError:
        ctx.logger.warning("httpx not installed — returning mock response")
        return f"[Mock — httpx not available] {message[:100]}..."

    model = _get_model(ctx)
    url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "max_tokens": 1024,
            }, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://mission-control.local",
                "X-Title": "Mission Control Agentic OS",
            })

            if resp.status_code != 200:
                ctx.logger.error("OpenRouter error: %d %s", resp.status_code, resp.text[:200])
                return f"[LLM Error {resp.status_code}] Check your API key and quota"

            data = resp.json()
            if "error" in data:
                ctx.logger.error("API error: %s", data["error"])
                return f"[API Error] {data['error'].get('message', 'Unknown error')}"

            return data["choices"][0]["message"]["content"]
    except asyncio.TimeoutError:
        return "[Timeout] LLM request took too long. Try again."
    except Exception as e:
        ctx.logger.error("LLM call failed: %s", e)
        return f"[Error] {str(e)[:100]}"
