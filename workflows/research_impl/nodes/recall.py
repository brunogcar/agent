"""Node: recall — Recall relevant memories before hitting the web."""
from __future__ import annotations

from workflows.base import WorkflowState, node_step


def node_recall(state: WorkflowState) -> dict:
    """Recall relevant memories before hitting the web."""
    from core.memory_engine import memory

    goal = state.get("goal", "")
    node_step(state, "recall", "checking memory", goal=goal[:60])

    results = memory.recall(
        query=goal,
        top_k=5,
        trace_id=state.get("trace_id", "")
    )

    if results:
        ctx = "\n".join(
            f"[{r['type']}|score={r['score']:.1f}] {r['text']}"
            for r in results
        )
        node_step(state, "recall", f"found {len(results)} memories")
        return {"memory_context": ctx}

    node_step(state, "recall", "no relevant memories found")
    return {"memory_context": ""}
