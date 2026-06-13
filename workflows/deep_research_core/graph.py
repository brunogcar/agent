"""DeepResearch LangGraph StateGraph builder.

Defines a 4-node cyclic graph:

    decompose -> search -> synthesize -> [route] -> search  (loop)
                                          |
                                        report -> END

The conditional edge from ``synthesize`` uses a ``path_map`` so that
LangGraph validates routing keys at compile time, preventing silent
runtime hangs.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from workflows.deep_research_core.nodes.decompose import node_decompose
from workflows.deep_research_core.nodes.search import node_search
from workflows.deep_research_core.nodes.synthesize import node_synthesize
from workflows.deep_research_core.routes import route_after_synthesize
from workflows.deep_research_core.state import DeepResearchState

logger = logging.getLogger(__name__)


def build_deep_research_graph() -> StateGraph:
    """Build and compile the DeepResearch cyclic graph.

    Returns:
        Compiled LangGraph StateGraph ready for ``invoke()``.
    """
    g = StateGraph(DeepResearchState)

    # -- Nodes -------------------------------------------------------
    g.add_node("decompose", node_decompose)
    g.add_node("search", node_search)
    g.add_node("synthesize", node_synthesize)
    g.add_node("report", _node_report)

    # -- Entry point -------------------------------------------------
    g.set_entry_point("decompose")

    # -- Linear edges ------------------------------------------------
    g.add_edge("decompose", "search")
    g.add_edge("search", "synthesize")

    # -- Cyclic conditional edge --------------------------------------
    # path_map guarantees compile-time validation of route strings
    g.add_conditional_edges(
        "synthesize",
        route_after_synthesize,
        {"search": "search", "report": "report", "failed": END},
    )

    # -- Exit --------------------------------------------------------
    g.add_edge("report", END)

    return g.compile()


def _node_report(state: DeepResearchState) -> DeepResearchState:
    """Produce the final report with budget audit appendix.

    This is a lightweight terminal node that formats the accumulated
    synthesis and telemetry into the final ``report`` and ``result``
    fields.  It does not call external tools.
    """
    from workflows.deep_research_core.budget import format_audit

    goal = state.get("goal", "")
    synthesis = state.get("synthesis", "")
    knowledge_base = state.get("knowledge_base", "")
    budget_events = state.get("budget_events", [])

    # Prefer the full knowledge_base if it exists, else the last synthesis
    findings = knowledge_base or synthesis

    report_lines = [
        f"# Deep Research: {goal}",
        "",
        "## Findings",
        "",
        findings,
        "",
        "## Budget Audit",
        "",
        format_audit(budget_events),
    ]

    report_text = "\n".join(report_lines)

    return {
        "report": report_text,
        "result": report_text,
        "status": "success",
    }
