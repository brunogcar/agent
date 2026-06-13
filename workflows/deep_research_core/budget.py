"""Budget tracking for the DeepResearch workflow.

All functions are pure: they receive the current state dict and return
a *partial* state dict that LangGraph merges.  No in-place mutation.
"""
from __future__ import annotations

from typing import Any

from core.config import cfg


def decrement_api_calls(state: dict[str, Any]) -> dict[str, Any]:
    """Reduce the Tavily API call budget by one."""
    current = state.get("budget_api_calls", 0)
    return {"budget_api_calls": max(0, current - 1)}


def decrement_browser_actions(state: dict[str, Any]) -> dict[str, Any]:
    """Reduce the browser action budget by one."""
    current = state.get("budget_browser_actions", 0)
    return {"budget_browser_actions": max(0, current - 1)}


def log_event(
    state: dict[str, Any],
    tool: str,
    action: str,
    reason: str = "",
) -> dict[str, Any]:
    """Append a budget/telemetry event to the audit trail.

    Args:
        state: Current workflow state.
        tool: Tool name (e.g. ``"tavily"``, ``"web"``, ``"browser"``).
        action: What happened (e.g. ``"selected"``, ``"fallback"``).
        reason: Human-readable context (e.g. truncated query).

    Returns:
        Partial state dict with the updated ``budget_events`` list.
    """
    events: list[dict[str, Any]] = list(state.get("budget_events", []))
    events.append(
        {
            "iteration": state.get("iteration", 0),
            "tool": tool,
            "action": action,
            "reason": reason,
        }
    )
    return {"budget_events": events}


def is_api_budget_exhausted(state: dict[str, Any]) -> bool:
    """Return ``True`` if no Tavily calls remain."""
    return state.get("budget_api_calls", 0) <= 0


def is_browser_budget_exhausted(state: dict[str, Any]) -> bool:
    """Return ``True`` if no browser actions remain."""
    return state.get("budget_browser_actions", 0) <= 0


def format_audit(events: list[dict[str, Any]]) -> str:
    """Render budget events as a markdown list."""
    lines = []
    for e in events:
        line = (
            f"- Iteration {e.get('iteration', '?')}: "
            f"{e.get('action', '?')} ({e.get('tool', '?')})"
        )
        if e.get("reason"):
            line += f" — {e['reason']}"
        lines.append(line)
    return "\n".join(lines) if lines else "_No budget events recorded._"
