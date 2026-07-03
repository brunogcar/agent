"""tools/parallel.py — Parallel tool execution meta-tool.

Allows the LLM to run multiple independent tool calls concurrently.
Imports tool functions directly — no registry dependency.
"""

from __future__ import annotations

from registry import tool
from core.contracts import ok, fail
from core.parallel_executor import dispatch_parallel, PARALLEL_SAFE

# Import tools we can dispatch to (explicit mapping — no runtime discovery)
from tools.web import web
from tools.git import git
from tools.file import file
from tools.python_exec import python
from tools.notify import notify
from tools.memory import memory
from tools.cli import cli

_TOOL_MAP = {
    "web": web,
    "git": git,
    "file": file,
    "python": python,
    "python_exec": python,
    "notify": notify,
    "memory": memory,
    "cli": cli,
}

@tool
def parallel(
    tools: list[dict],
    max_workers: int = 4,
    allow_unsafe: bool = False,
    trace_id: str = "",
) -> dict:
    """
    Execute multiple tool calls in parallel.

    Args:
        tools: List of tool call specs. Each spec is a dict with:
            - name: str — tool name
            - args: dict — arguments to pass
        max_workers: Max concurrent threads (1-8, default 4)
        allow_unsafe: If True, allow tools not in PARALLEL_SAFE
        trace_id: Trace ID for observability

    Returns:
        ToolResult with data containing results and errors.
    """
    if not isinstance(tools, list):
        return fail("tools must be a list", trace_id=trace_id)

    if not tools:
        return fail("No tools provided", trace_id=trace_id)

    calls = []
    for i, spec in enumerate(tools):
        if not isinstance(spec, dict):
            return fail(f"Tool spec at index {i} must be a dict", trace_id=trace_id)

        name = spec.get("name")
        args = spec.get("args", {})

        if not name:
            return fail(f"Tool spec at index {i} missing 'name'", trace_id=trace_id)

        fn = _TOOL_MAP.get(name)
        if not fn:
            return fail(f"Tool '{name}' not found", trace_id=trace_id)

        if not allow_unsafe and name not in PARALLEL_SAFE:
            return fail(
                f"Tool '{name}' is not parallel-safe. Set allow_unsafe=True to override.",
                trace_id=trace_id,
            )

        calls.append((name, fn, args))

    return dispatch_parallel(calls, max_workers=max_workers, trace_id=trace_id)
