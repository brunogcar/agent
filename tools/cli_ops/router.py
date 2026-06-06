"""router.py — Router dispatch logic for cli meta-tool (Layer 3).

Uses the Router model to classify commands that don't match patterns or shell whitelist.
"""

from __future__ import annotations

import json

from core.config import cfg
from core.llm import llm

# Router system prompt
_ROUTER_SYSTEM = """You are a command router for an MCP agent. Given a natural-language command,
decide ONE of two things:

Option A — the command maps to a simple tool call:
  {"route": "dispatch", "tool_name": "", "action": "", "params": {}}
  Allowed tool_name values: file, git, web, memory, python, notify, lms, system.

Option B — the command is too complex for a single tool call and needs the Executor:
  {"route": "escalate", "reason": ""}

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
    try:
        response = llm.complete(
            role="router",
            system=_ROUTER_SYSTEM,
            user=command,
            timeout=15,
            temperature=0.0,
            max_tokens=256,
        )
        if not response.ok:
            return {"route": "escalate", "reason": f"Router LLM error: {response.error}"}

        content = response.text.strip()

        # Parse JSON response
        if content.startswith("```json"):
            content = content[7:].strip()
        if content.startswith("```"):
            content = content[3:].strip()

        return json.loads(content)

    except Exception as e:
        # If Router fails, fall through to Executor
        return {"route": "escalate", "reason": f"Router error: {e}"}
