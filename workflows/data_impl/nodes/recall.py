"""Node: recall — Recall relevant past analyses from memory before execution.

[Fix #8] memory.recall is wrapped in try/except so a memory backend failure
does not crash the workflow. The workflow proceeds with empty context.
Mirrors deep_research's _node_recall graceful-failure pattern.
[Fix #1] Returns a partial update dict (was {**state, ...}).
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step


def node_recall(state: WorkflowState) -> dict:
    """Check memory for relevant prior analysis or patterns."""
    from core.memory_engine import memory

    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    node_step(state, "recall", "checking memory", goal=goal[:60])

    try:
        results = memory.recall(
            query=goal,
            top_k=3,
            trace_id=tid,
        )
    except Exception as e:
        # [Fix #8] Memory failure is non-fatal — proceed without context.
        node_step(state, "recall", f"memory recall failed, proceeding without context: {e}")
        return {"memory_context": ""}

    if results:
        ctx = "\n".join(
            f"[{r['type']}] {r['text']}"
            for r in results
        )
        node_step(state, "recall", f"found {len(results)} relevant memories")
        return {"memory_context": ctx}

    node_step(state, "recall", "no prior context found")
    return {"memory_context": ""}
