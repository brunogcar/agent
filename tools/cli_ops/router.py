"""Router dispatch logic for cli meta-tool (Layer 3).

Uses the Router model to classify commands that don't match patterns
or shell whitelist. Generates the allowed tool list dynamically from
DISPATCH to prevent drift.
"""
from __future__ import annotations

import json

from core.config import cfg
from core.llm import llm
from tools.cli_ops._registry import DISPATCH


def _build_router_system() -> str:
    """Build router system prompt with current DISPATCH tool names."""
    allowed_tools = ", ".join(sorted(DISPATCH.keys()))
    return f"""You are a command router for an MCP agent. Given a natural-language command,
decide ONE of two things:

Option A — the command maps to a simple tool call:
  {{"route": "dispatch", "tool_name": "", "action": "", "params": {{}}}}
  Allowed tool_name values: {allowed_tools}.

Option B — the command is too complex for a single tool call and needs the Executor:
  {{"route": "escalate", "reason": ""}}

Use Option A for: status checks, reads, searches, single-step writes, calculations.
Use Option B for: multi-step tasks, code generation, analysis, research, anything
that requires reasoning or multiple tool calls to complete.

Output ONLY valid JSON. No explanation, no markdown."""


def _call_router(command: str) -> dict | None:
    """Send command to Router model for classification.

    Returns:
        dict with 'route' key ('dispatch' or 'escalate'),
        or None if there's an unrecoverable error.
    """
    try:
        response = llm.complete(
            role="router",
            system=_build_router_system(),
            user=command,
            timeout=15,
            temperature=0.0,
            max_tokens=256,
        )
        if not response.ok:
            return {
                "route": "escalate",
                "reason": f"Router LLM error: {response.error}",
            }

        content = response.text.strip()

        # Strip markdown code fences if present
        if content.startswith("```json"):
            content = content[7:].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()

        parsed = json.loads(content)

        # Validate route field
        route = parsed.get("route")
        if route not in ("dispatch", "escalate"):
            return {
                "route": "escalate",
                "reason": f"Router returned invalid route: {route}",
            }

        return parsed

    except json.JSONDecodeError as e:
        return {"route": "escalate", "reason": f"Router returned invalid JSON: {e}"}
    except Exception as e:
        return {"route": "escalate", "reason": f"Router error: {e}"}
