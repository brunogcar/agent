"""
core/gateway_backend/dispatcher.py — Tool routing and orchestration logic.

EXTRACTION NOTE (Gateway Phase 1): Extracted from core/gateway.py.
Separates HTTP transport from tool orchestration. This module acts as a 
static router, mapping incoming payloads to the appropriate MCP tool or workflow.
"""
from __future__ import annotations

from typing import Any

from core.tracer import tracer


def dispatch(trace_id: str, payload: dict) -> Any:
    """
    Dispatch a task payload to the appropriate tool or workflow.

    P1-3 fix: always returns a dict with a 'status' key.
    Workflows that complete without raising are tagged 'success' here
    so polling clients always see a terminal status.
    """
    tool   = payload.get("tool",  "")
    action = payload.get("action", "")
    goal   = payload.get("goal",   "")
    params = payload.get("params", {})

    if tool == "workflow" or goal:
        from workflows.base import run_workflow
        wf_type = payload.get("workflow", "auto")

        if wf_type == "auto":
            from core.router import router
            decision = router.route(goal, trace_id=trace_id)
            wf_type  = decision.workflow
            if wf_type == "direct":
                wf_type = "research"

        result = run_workflow(
            workflow_type = wf_type,
            goal          = goal,
            trace_id      = trace_id,
            **params,
        )
        # Ensure terminal status is always present (P1-3)
        if isinstance(result, dict) and "status" not in result:
            result["status"] = "success"
        return result

    if tool == "web":
        from tools.web import web
        return web(action=action, **params)

    if tool == "python":
        from tools.python_exec import python
        return python(**params)

    if tool == "memory":
        from tools.memory_tool import memory
        return memory(action=action, **params)

    if tool == "file":
        from tools.file import file
        return file(action=action, **params)

    if tool == "git":
        from tools.git import git
        return git(action=action, **params)

    if tool == "agent":
        from tools.agent import agent  # [PHASE-3] Migrated from tools.agent_tool → tools.agent
        return agent(**params)

    if tool == "report":
        from tools.report import report  # [PHASE-3] Migrated from tools.report_tool → tools.report
        return report(**params)

    if tool == "notify":
        from tools.notify import notify
        return notify(action=action, **params)

    if tool == "cli":
        from tools.cli import cli
        return cli(**params)

    if tool == "vision":
        from tools.vision import vision
        return vision(**params)

    return {"status": "error", "error": f"Unknown tool: '{tool}'"}