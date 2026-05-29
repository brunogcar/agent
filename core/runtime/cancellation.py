"""
core/cancellation.py — Centralized async cancellation checks.
Prevents ghost mutations (file writes, git commits, memory stores) 
when a workflow is cancelled mid-flight.
"""
from __future__ import annotations

import asyncio
from core.tracer import tracer

def ensure_not_cancelled(trace_id: str = "") -> None:
    """
    Check if the current async task has been cancelled.
    Raises asyncio.CancelledError if cancelled.
    Safely ignores the check if called from a synchronous context (no event loop).
    """
    try:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task(loop)
        # hasattr check protects against edge cases where task is None or lacks cancelling()
        if task and hasattr(task, "cancelling") and task.cancelling() > 0:
            if trace_id:
                tracer.step(trace_id, "cancellation", "Task cancelled — aborting side effect")
            raise asyncio.CancelledError("Workflow cancelled — aborting side effect")
    except RuntimeError:
        # No running event loop (called from synchronous code/tests) — safe to proceed
        pass