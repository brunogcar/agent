"""tools/parallel.py — Parallel tool execution meta-tool (v1.0).

Thin @tool facade. Routes all parallel actions to handlers in
parallel_ops/actions/ via the DISPATCH dict. Auto-discovered by
registry.py via the @tool decorator.

v1.0 changes (the @meta_tool refactor):
  - Now a meta-tool with 3 actions: run | race | pipeline.
  - @meta_tool auto-generates the action: Literal[...] type annotation and
    the docstring's action list from DISPATCH.
  - BREAKING: param `tools` renamed to `tasks` (avoids shadowing the
    `tools/` package). Callers passing `tools=` will get a TypeError from
    FastMCP schema validation. Update system_prompt.md docs accordingly.
  - New params: action (run|race|pipeline), timeout (per-call override).
  - All implementation logic moved to parallel_ops/ subpackage.

Parallel IS NOT in PARALLEL_SAFE — nested parallel calls are blocked by
the thread-local _parallel_depth guard in parallel_ops/executor.py.
The router already routes to `parallel` for parallel intent; no router
changes needed for v1.0.
"""
from __future__ import annotations

import time

from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import parallel_ops to trigger DISPATCH auto-discovery BEFORE @meta_tool reads it.
from tools import parallel_ops  # noqa: F401
from tools.parallel_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("parallel", {}),
    doc_sections=[
        "PARALLEL TOOL — Execute multiple tool calls concurrently:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | All tools in parallel, wait for all | parallel(run) | ThreadPoolExecutor, wait for completion |",
        " | First successful result wins | parallel(race) | as_completed, cancel rest on first success |",
        " | Sequential chain (output feeds next) | parallel(pipeline) | NOT parallel — ordered execution |",
        "",
        "Each task is a dict: {name: str, args: dict}",
        "PARALLEL_SAFE tools: web, file, python, python_exec, notify, github, consult, vision, report, agent",
        "NOT parallel-safe: cli, git, memory, browser, tavily, swarm, workflow, parallel",
        "",
        "BREAKING v1.0: param `tools` renamed to `tasks`. action is now required.",
    ],
)
def parallel(
    action: str = "",
    tasks: list[dict] = [],
    max_workers: int = 4,
    allow_unsafe: bool = False,
    timeout: int = -1,
    trace_id: str = "",
) -> dict:
    """Parallel tool execution meta-tool — run | race | pipeline."""
    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "parallel", f"action={action}")

    if not action:
        return {
            "status": "error",
            "error": "action is required (pipeline | race | run)",
            "trace_id": trace_id,
        }

    dispatch = DISPATCH.get("parallel", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return {
            "status": "error",
            "error": f"Unknown action '{action}'. Use: {valid_actions}",
            "trace_id": trace_id,
        }

    handler = op_info["func"]

    kwargs = {
        "tasks": tasks,
        "max_workers": max_workers,
        "allow_unsafe": allow_unsafe,
        "timeout": timeout,
        "trace_id": trace_id,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Parallel action failed: {e}",
            "trace_id": trace_id,
        }

    if not isinstance(result, dict):
        return {
            "status": "error",
            "error": f"Handler returned {type(result).__name__}, expected dict.",
            "trace_id": trace_id,
        }

    if result.get("status") == "error":
        tracer.step(trace_id, "parallel", f"action={action}:failed")
    else:
        tracer.step(trace_id, "parallel", f"action={action}:complete")

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
