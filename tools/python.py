"""tools/python.py — Python execution meta-tool (v1.0).

Thin @tool facade. Routes all python actions to handlers in
python_ops/actions/ via the DISPATCH dict. Auto-discovered by
registry.py via the @tool decorator.

v1.0 changes (the @meta_tool refactor + un-multiplex):
  - Now a meta-tool with 5 actions: run | run_data | eval | profile | lint.
  - @meta_tool auto-generates the action: Literal[...] type annotation and
    the docstring's action list from DISPATCH.
  - BREAKING: `mode` parameter renamed to `action` (matches all other
    @meta_tool tools).
  - New params: trace_id (observability), timeout (override
    cfg.execution_timeout for subprocess), json_schema (JSON schema string
    for structured output enforcement).
  - All implementation logic moved to python_ops/ subpackage.

Parallel-safety: python IS in PARALLEL_SAFE. Each action's thread-safety
is handled internally: run uses _STDOUT_LOCK; eval is fast/lockless;
run_data/profile/lint use subprocess isolation.
"""
from __future__ import annotations

import time

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

# Import python_ops to trigger DISPATCH auto-discovery BEFORE @meta_tool reads it.
from tools import python_ops  # noqa: F401
from tools.python_ops._registry import DISPATCH


@tool
@meta_tool(
    DISPATCH.get("python", {}),
    doc_sections=[
        "PYTHON TOOL — Code execution with security layers:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Pure logic, no imports | python(run) | Strict sandbox, whitelisted builtins only |",
        " | Data analysis with imports | python(run_data) | Controlled imports (stdlib in-process, heavy in subprocess) |",
        " | Quick expression eval | python(eval) | Expressions only (no statements), even more restrictive than run |",
        " | Performance profiling | python(profile) | cProfile timing breakdown |",
        " | Code quality check | python(lint) | ruff --select E,F (syntax + lint) before execution |",
        "",
        "NOT parallel-safe for run_data (subprocess), but run/eval/lint are safe.",
        "ALWAYS use print() to return output — variables are not captured (except in eval).",
    ],
)
def python(
    action: str = "",
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
) -> dict:
    """Python code execution meta-tool — run | run_data | eval | profile | lint."""
    action = action.strip().lower() if action else ""

    tracer.step(trace_id, "python", f"action={action}")

    if not action:
        return fail("action is required (run | run_data | eval | profile | lint)", trace_id=trace_id)

    if not code or not code.strip():
        return fail("No code provided", trace_id=trace_id)

    dispatch = DISPATCH.get("python", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    handler = op_info["func"]

    kwargs = {
        "code": code,
        "trace_id": trace_id,
        "timeout": timeout,
        "json_schema": json_schema,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        return fail(f"Python action failed: {e}", trace_id=trace_id)

    if not isinstance(result, dict):
        return fail(
            f"Handler returned {type(result).__name__}, expected dict.",
            trace_id=trace_id,
        )

    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id

    if result.get("status") == "error":
        tracer.step(trace_id, "python", f"action={action}:failed")
    else:
        tracer.step(trace_id, "python", f"action={action}:complete")

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
