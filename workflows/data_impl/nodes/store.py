"""Node: store — Store analysis results in episodic + procedural memory.

[Fix #1]  Returns {} (side effects only) instead of `return state`.
[Fix #5]  Procedural memory is stored ONLY for LLM-generated code, not for
          user-provided code. node_execute sets `code_generated` to indicate
          this. Previously ALL successful executions stored procedural memory,
          polluting it with user code.
[Fix #8]  memory.store_* calls are wrapped in try/except so a memory backend
          failure does not crash the workflow. Storage is best-effort.
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step
from core.tracer import tracer


def node_store(state: WorkflowState) -> dict:
    """Store analysis results in episodic memory (+ procedural for generated code)."""
    from core.memory_engine import memory

    goal = state.get("goal", "")
    result = state.get("result", "") or state.get("output", "")
    code = state.get("code", "")
    tid = state.get("trace_id", "")

    if not result:
        return {}

    node_step(state, "store", "saving results to memory")

    try:
        memory.store_episodic(
            text=f"Data analysis: '{goal[:60]}'\nResult: {result[:400]}",
            importance=6,
            goal=goal,
            outcome="success",
            tools_used="python,agent,memory",
            trace_id=tid,
        )
    except Exception as e:
        # [Fix #8] Memory failure is non-fatal — log and continue.
        tracer.error(tid, "store", f"episodic store failed: {e}")

    # [Fix #5] Only store procedural memory for LLM-generated code that worked.
    if code and result and state.get("code_generated"):
        try:
            memory.store_procedural(
                text=f"Working data code for '{goal[:60]}':\n{code[:400]}",
                importance=6,
                tags="data,python,working-code",
                trace_id=tid,
            )
        except Exception as e:
            tracer.error(tid, "store", f"procedural store failed: {e}")

    return {}
