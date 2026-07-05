"""Node: synthesize — LLM synthesis of web results + memory."""
from __future__ import annotations

from workflows.base import WorkflowState, node_step, node_error


def node_synthesize(state: WorkflowState) -> dict:
    """Synthesize web results + memory into a coherent answer.

    Uses agent(action="dispatch", role="research") to synthesize scraped
    web content and recalled memories into a single coherent response.
    """
    from tools.agent import agent

    goal = state.get("goal", "")
    search_results = state.get("search_results", "")
    memory_context = state.get("memory_context", "")

    if not search_results and not memory_context:
        return node_error(state, "synthesize",
                          "No source material to synthesize from")

    # Build content block for the executor
    content_parts = []
    if memory_context:
        content_parts.append(f"MEMORY:\n{memory_context}")
    if search_results:
        content_parts.append(f"WEB SOURCES:\n{search_results}")
    content = "\n\n".join(content_parts)

    node_step(state, "synthesize", "calling research agent",
              content_chars=len(content))

    r = agent(
        action  = "dispatch",
        role    = "research",
        task    = f"Synthesise the provided sources to answer: {goal}",
        content = content,
        trace_id = state.get("trace_id", ""),
    )

    if r.get("status") != "success":
        return node_error(state, "synthesize",
                          f"Agent failed: {r.get('error', 'unknown')}")

    node_step(state, "synthesize", "synthesis complete",
              elapsed=r.get("elapsed", 0))
    return {"result": r["text"]}
