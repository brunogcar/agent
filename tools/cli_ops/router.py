"""
router.py — Router dispatch logic for cli meta-tool (Layer 3).

Uses the Router model to classify commands that don't match patterns or shell whitelist.
"""

from __future__ import annotations

import json

from core.config import cfg

# Router system prompt
_ROUTER_SYSTEM = """You are a command router for an MCP agent. Given a natural-language command,
decide ONE of two things:

Option A — the command maps to a simple tool call:
  {"route": "dispatch", "tool_name": "<tool>", "action": "<action>", "params": {}}
  Allowed tool_name values: file, git, web, memory, python, notify, lms, system.

Option B — the command is too complex for a single tool call and needs the Executor:
  {"route": "escalate", "reason": "<one sentence why>"}

Use Option A for: status checks, reads, searches, single-step writes, calculations.
Use Option B for: multi-step tasks, code generation, analysis, research, anything
  that requires reasoning or multiple tool calls to complete.

Output ONLY valid JSON. No explanation, no markdown."""

def _call_router(command: str) -> dict | None:
    """Send command to Router model for classification.

    Returns:
        dict with 'route' key ('dispatch' or 'escalate')
        or None if there's an error
    """
    import requests

    try:
        response = requests.post(
            f"{cfg.lm_studio_base_url}/chat/completions",
            json={
                "model": cfg.router_model,
                "messages": [
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user", "content": command},
                ],
                "temperature": 0.0,
                "max_tokens": 256,
                "stream": False,
            },
            timeout=15,
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        if content.startswith("```json"):
            content = content[7:].strip()
        if content.startswith("```"):
            content = content[3:].strip()

        return json.loads(content)

    except Exception as e:
        # If Router fails, fall through to Executor
        return {"route": "escalate", "reason": f"Router error: {e}"}