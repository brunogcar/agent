"""Node: store — Store research findings in memory.

[Fix #7] Semantic memory now stores full result (was truncated to 800 chars).
v1.1.1: Added try/except around memory.store_* — non-fatal (same pattern
as data workflow Fix #8).
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step
from core.tracer import tracer


def node_store(state: WorkflowState) -> dict:
    """Store research findings in semantic and episodic memory."""
    from core.memory_engine import memory

    result = state.get("result", "")
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")

    if not result:
        return {}

    node_step(state, "store", "saving to semantic memory")

    try:
        memory.store_semantic(
            text=f"Research on '{goal}':\n{result}",
            importance=6,
            tags="research,auto",
            trace_id=tid,
        )
    except Exception as e:
        tracer.error(tid, "store", f"semantic store failed: {e}")

    try:
        memory.store_episodic(
            text=f"Completed research workflow: '{goal[:60]}'",
            importance=5,
            goal=goal,
            outcome="success",
            tools_used="web,agent,memory",
            trace_id=tid,
        )
    except Exception as e:
        tracer.error(tid, "store", f"episodic store failed: {e}")

    return {}
