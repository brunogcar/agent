"""Node: store — Store research findings in memory.

[Fix #7] Semantic memory now stores full result (was truncated to 800 chars).
The 800-char limit made semantic memory nearly useless for long research results.
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step


def node_store(state: WorkflowState) -> dict:
    """Store research findings in semantic and episodic memory.

    [Fix #7] Was: result[:800] — truncated to 800 chars, making semantic memory
    nearly useless for long research results. Now stores the full result.
    Episodic memory still stores a short summary (it's for event tracking, not
    content retrieval).
    """
    from core.memory_engine import memory

    result = state.get("result", "")
    goal = state.get("goal", "")

    if not result:
        return {}

    node_step(state, "store", "saving to semantic memory")

    # [Fix #7] Store full result in semantic memory (was result[:800]).
    # Semantic memory is for content retrieval — truncation defeats the purpose.
    memory.store_semantic(
        text=f"Research on '{goal}':\n{result}",
        importance=6,
        tags="research,auto",
        trace_id=state.get("trace_id", "")
    )

    # Episodic memory stores a short summary (it's for event tracking).
    memory.store_episodic(
        text=f"Completed research workflow: '{goal[:60]}'",
        importance=5,
        goal=goal,
        outcome="success",
        tools_used="web,agent,memory",
        trace_id=state.get("trace_id", "")
    )

    return {}
