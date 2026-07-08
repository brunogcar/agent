"""Graph builder and metadata for the research workflow.

v1.0: Split from monolithic workflows/research.py into research_impl/ subpackage
with per-node modules. Adds WORKFLOW_METADATA for MCP client introspection.

v1.1: Wired trim_state_node between synthesize and report. After synthesize
produces `result`, the raw `search_results` (up to 40KB — 5 pages × 8KB) is no
longer needed (report, store, distill, notify all use `result`). The trim node
evicts oversized `search_results` to episodic memory, keeping a preview.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from workflows.base import WorkflowState, trim_state_node
from workflows.research_impl.nodes.recall import node_recall
from workflows.research_impl.nodes.search import node_search
from workflows.research_impl.nodes.parallel_scrape import node_parallel_scrape
from workflows.research_impl.nodes.synthesize import node_synthesize
from workflows.research_impl.nodes.report import node_report
from workflows.research_impl.nodes.store import node_store
from workflows.research_impl.nodes.distill import node_distill
from workflows.research_impl.nodes.notify import node_notify
from workflows.research_impl.routes import route_after_search, route_after_synthesize


# [WORKFLOW_METADATA] Structured metadata for MCP client introspection.
# Allows clients to display workflow structure, node descriptions, and
# routing logic without reading source code.
WORKFLOW_METADATA = {
    "name": "research",
    "version": "1.1",
    "description": "Quick web research: search → parallel scrape → synthesize → trim → report",
    "nodes": [
        {"name": "recall", "description": "Recall relevant memories from ChromaDB"},
        {"name": "search", "description": "SearXNG web search for URLs (deduplicated)"},
        {"name": "parallel_scrape", "description": "Scrape top results in parallel with browser fallback"},
        {"name": "synthesize", "description": "LLM synthesis of findings via agent(research)"},
        {"name": "trim", "description": "Evict oversized `search_results` to episodic memory (v1.1: chonkie-aware, keeps preview)"},
        {"name": "report", "description": "Generate cited research dossier"},
        {"name": "store", "description": "Store in semantic + episodic memory"},
        {"name": "distill", "description": "Distill procedural rules for future runs"},
        {"name": "notify", "description": "Notify user of completion"},
    ],
    "edges": [
        {"from": "recall", "to": "search"},
        {"from": "search", "to": "parallel_scrape"},
        {"from": "parallel_scrape", "to": "synthesize", "condition": "has_results"},
        {"from": "parallel_scrape", "to": "END", "condition": "no_results"},
        {"from": "synthesize", "to": "trim", "condition": "success"},
        {"from": "synthesize", "to": "END", "condition": "failed"},
        {"from": "trim", "to": "report"},
        {"from": "report", "to": "store"},
        {"from": "store", "to": "distill"},
        {"from": "distill", "to": "notify"},
        {"from": "notify", "to": "END"},
    ],
}


def build_research_graph():
    """Build and compile the research workflow graph."""
    g = StateGraph(WorkflowState)
    g.add_node("recall", node_recall)
    g.add_node("search", node_search)
    g.add_node("parallel_scrape", node_parallel_scrape)
    g.add_node("synthesize", node_synthesize)
    g.add_node("report", node_report)
    g.add_node("store", node_store)
    g.add_node("distill", node_distill)
    g.add_node("notify", node_notify)

    g.set_entry_point("recall")

    g.add_edge("recall", "search")
    g.add_edge("search", "parallel_scrape")

    g.add_conditional_edges(
        "parallel_scrape",
        route_after_search,
        {"synthesize": "synthesize", "failed": END},
    )

    g.add_conditional_edges(
        "synthesize",
        route_after_synthesize,
        {"trim": "trim", "failed": END},
    )

    # v1.1: trim node between synthesize and report. After synthesize produces
    # `result`, the raw `search_results` (up to 40KB) is no longer needed —
    # report, store, distill, and notify all use `result`. trim_state_node
    # evicts oversized `search_results` to episodic memory, keeping a preview.
    # Under-threshold search_results passes through unchanged (returns {}).
    g.add_node("trim", trim_state_node)
    g.add_edge("trim", "report")
    g.add_edge("report", "store")
    g.add_edge("store", "distill")
    g.add_edge("distill", "notify")
    g.add_edge("notify", END)

    return g.compile()
