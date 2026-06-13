"""workflows/deep_research_core/graph.py
LangGraph builder for the DeepResearch cyclic workflow.
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.nodes.decompose import node_decompose
from workflows.deep_research_core.nodes.search import node_search
from workflows.deep_research_core.nodes.synthesize import node_synthesize
from workflows.deep_research_core.routes import route_after_synthesize
from core.citations import citations


def build_deep_research_graph():
    graph = StateGraph(DeepResearchState)

    # Pre-research: recall relevant memories
    graph.add_node("recall", _node_recall)

    # Core cyclic loop
    graph.add_node("decompose", node_decompose)
    graph.add_node("search", node_search)
    graph.add_node("synthesize", node_synthesize)
    graph.add_node("report", _node_report)

    # Post-research: store, distill, notify
    graph.add_node("store", _node_store)
    graph.add_node("distill", _node_distill)
    graph.add_node("notify", _node_notify)

    graph.set_entry_point("recall")
    graph.add_edge("recall", "decompose")
    graph.add_edge("decompose", "search")
    graph.add_edge("search", "synthesize")
    graph.add_conditional_edges(
        "synthesize",
        route_after_synthesize,
        path_map={"search": "search", "report": "report"},
    )
    graph.add_edge("report", "store")
    graph.add_edge("store", "distill")
    graph.add_edge("distill", "notify")
    graph.add_edge("notify", END)
    return graph.compile()


def _node_recall(state: DeepResearchState) -> DeepResearchState:
    """Recall relevant memories before starting research."""
    from core.memory import memory
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    try:
        memories = memory.recall(query=goal, top_k=5, trace_id=tid)
        context = "\n\n".join([m.get("text", "") for m in memories]) if memories else ""
    except Exception:
        context = ""
    return {"memory_context": context}


def _node_report(state: DeepResearchState) -> DeepResearchState:
    """Generate final report with citations and budget audit."""
    from workflows.deep_research_core.budget import format_audit
    knowledge_base = state.get("knowledge_base", "")
    synthesis = state.get("synthesis", "")
    tid = state.get("trace_id", "")
    budget_events = state.get("budget_events", [])
    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", 85.0)

    # Build report body
    report_text = knowledge_base or synthesis or "No results generated."

    # Append numbered citations
    sources = citations.get_sources(tid)
    if sources:
        report_text += "\n\n## Sources\n"
        for src in sources:
            report_text += f"[{src['number']}] {src['title']} — {src['url']}\n"

    # Budget audit
    report_lines = [report_text, "", "## Budget Audit", format_audit(budget_events)]
    full_report = "\n".join(report_lines)

    # Determine status — do not claim success if completeness is below threshold
    status = "success" if completeness >= threshold else "incomplete"

    return {
        "report": full_report,
        "result": full_report,
        "status": status,
    }


def _node_store(state: DeepResearchState) -> DeepResearchState:
    """Store research result to semantic memory."""
    from core.memory import memory
    result = state.get("result", "")
    tid = state.get("trace_id", "")
    if result:
        try:
            memory.store_semantic(
                text=result, importance=6, tags="deep_research", trace_id=tid
            )
        except Exception:
            pass
    return {}


def _node_distill(state: DeepResearchState) -> DeepResearchState:
    """Distill workflow into procedural rule.

    Gracefully skips if core.sleep_learn.distill_workflow is unavailable.
    """
    from core.tracer import tracer
    tid = state.get("trace_id", "")
    try:
        from core.sleep_learn import distill_workflow
        trace_text = tracer.get_trace(tid)
        if trace_text:
            distill_workflow(trace_text=trace_text, trace_id=tid)
    except (ImportError, AttributeError):
        pass  # distill_workflow not available in this environment
    return {}


def _node_notify(state: DeepResearchState) -> DeepResearchState:
    """Notify user of completion."""
    from tools.notify import notify
    tid = state.get("trace_id", "")
    result = state.get("result", "")
    status = state.get("status", "success")
    if result:
        msg = (
            f"DeepResearch {'complete' if status == 'success' else 'finished'}: "
            f"{result[:200]}"
        )
        try:
            notify(message=msg, trace_id=tid)
        except Exception:
            pass
    return {}
