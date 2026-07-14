"""Node: recall — Recall relevant memories before hitting the web.

v1.1.1: Added try/except around memory.recall — non-fatal (same pattern
as data workflow Fix #8). Was: memory failure crashed the workflow.
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step
from core.tracer import tracer


def node_recall(state: WorkflowState) -> dict:
    """Recall relevant memories before hitting the web."""
    from core.memory_engine import memory

    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    node_step(state, "recall", "checking memory", goal=goal[:60])

    try:
        results = memory.recall(
            query=goal,
            top_k=5,
            trace_id=tid,
        )
    except Exception as e:
        tracer.error(tid, "recall", f"memory recall failed, proceeding without context: {e}")
        return {"memory_context": ""}

    if results:
        ctx = "\n".join(
            f"[{r['type']}|score={r['score']:.1f}] {r['text']}"
            for r in results
        )
        node_step(state, "recall", f"found {len(results)} memories")
        return {"memory_context": ctx}

    node_step(state, "recall", "no relevant memories found")
    return {"memory_context": ""}
