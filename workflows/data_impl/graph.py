"""Graph builder and metadata for the data workflow.

v1.0: Split from monolithic workflows/data.py into the data_impl/ subpackage
with per-node modules, mirroring research_impl / understand_impl.

[Decision] Reuses WorkflowState from workflows/base.py (same as research_impl)
because every data field — goal, code, memory_context, output, exec_error,
result, status, trace_id — already exists in WorkflowState. No separate
state.py is needed. The only data-internal state key is `code_generated`
(set by node_execute, read by node_store); it flows as a plain dict key.

[Decision] base.py imports build_data_graph() from the thin facade
(workflows/data.py), which re-exports from here — same pattern as research.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from workflows.base import WorkflowState
from workflows.data_impl.nodes.recall import node_recall
from workflows.data_impl.nodes.execute import node_execute
from workflows.data_impl.nodes.critique import node_critique
from workflows.data_impl.nodes.store import node_store
from workflows.data_impl.nodes.notify import node_notify
from workflows.data_impl.routes import route_after_execute


# [Fix #11] WORKFLOW_METADATA for MCP client introspection.
# Mirrors the research/understand format: nodes (with descriptions) + edges
# (with conditions). The execute->critique/END edge is conditional on exec_error.
WORKFLOW_METADATA = {
    "name": "data",
    "version": "1.0",
    "description": "Data analysis: recall -> execute -> critique -> store -> notify",
    "nodes": [
        {"name": "recall", "description": "Recall relevant past analyses from memory"},
        {"name": "execute", "description": "Generate (if needed) and execute Python code in a sandbox"},
        {"name": "critique", "description": "LLM critique of whether the output answers the goal"},
        {"name": "store", "description": "Store results in episodic (+ procedural for generated code) memory"},
        {"name": "notify", "description": "Notify the user and mark the workflow done"},
    ],
    "edges": [
        {"from": "recall", "to": "execute"},
        {"from": "execute", "to": "critique", "condition": "success (no exec_error)"},
        {"from": "execute", "to": "END", "condition": "failed (exec_error set)"},
        {"from": "critique", "to": "store"},
        {"from": "store", "to": "notify"},
        {"from": "notify", "to": "END"},
    ],
}


def build_data_graph():
    """Build and compile the data workflow LangGraph StateGraph."""
    g = StateGraph(WorkflowState)

    g.add_node("recall", node_recall)
    g.add_node("execute", node_execute)
    g.add_node("critique", node_critique)
    g.add_node("store", node_store)
    g.add_node("notify", node_notify)

    g.set_entry_point("recall")

    g.add_edge("recall", "execute")

    # [Fix #2/#3] Both failure paths now set exec_error, so this conditional
    # edge correctly routes failures to END (was: code-gen failure leaked
    # through to critique because node_error didn't set exec_error).
    g.add_conditional_edges(
        "execute",
        route_after_execute,
        {"critique": "critique", "failed": END},
    )

    # [Fix #10] critique -> store is a direct edge (route_after_critique was
    # dead code — it always returned "store").
    g.add_edge("critique", "store")
    g.add_edge("store", "notify")
    g.add_edge("notify", END)

    return g.compile()
