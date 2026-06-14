"""workflows/deep_research_core/graph.py
Build and compile the DeepResearch LangGraph StateGraph.
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.nodes.decompose import node_decompose as node_decompose_goal
from workflows.deep_research_core.nodes.search import node_search
from workflows.deep_research_core.nodes.synthesize import node_synthesize
from workflows.deep_research_core.routes import route_after_synthesize
from core.config import cfg
from core.memory import memory
from tools.notify import notify
from core.tracer import tracer
from workflows.deep_research_core.budget import format_audit


def _node_recall(state: DeepResearchState) -> DeepResearchState:
    """Recall relevant memories before starting research."""
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    try:
        results = memory.recall(query=goal, top_k=5, trace_id=tid)
        lines = []
        for r in results:
            t = r.get("type", "unknown")
            s = r.get("score", 0)
            txt = r.get("text", "")
            lines.append(f"[{t}|score={s:.1f}] {txt}")
        context = chr(10).join(lines)
        return {**state, "memory_context": context}
    except Exception:
        return {**state, "memory_context": ""}


def _node_report(state: DeepResearchState) -> DeepResearchState:
    """Build final report from knowledge_base and budget audit."""
    knowledge = state.get("knowledge_base", "")
    synthesis = state.get("synthesis", "")
    report_text = synthesis if synthesis else knowledge
    budget_events = state.get("budget_events", [])
    audit = format_audit(budget_events)
    report_lines = ["# Deep Research Report" + chr(10), report_text, chr(10) + "---" + chr(10), audit]
    completeness = state.get("completeness", 0)
    threshold = state.get("completeness_threshold", 85)
    status = "success" if completeness >= threshold else "incomplete"
    return {"report": chr(10).join(report_lines), "result": report_text, "status": status}


def _node_store(state: DeepResearchState) -> DeepResearchState:
    """Store final result to semantic memory."""
    tid = state.get("trace_id", "")
    result = state.get("result", "")
    try:
        memory.store_semantic(text="Deep Research: " + result[:800], importance=6, tags="deep_research", trace_id=tid)
    except Exception:
        pass
    return state


def _node_distill(state: DeepResearchState) -> DeepResearchState:
    """Workflow distillation deferred to v2."""
    # TODO: Implement when sleep_learn exports distill_workflow and tracer.get_traces is wired up.
    return state


def _node_notify(state: DeepResearchState) -> DeepResearchState:
    """Send notification that research is complete."""
    msg = state.get("result", "Deep research complete")
    try:
        notify(action="send", title="DeepResearch", message=msg[:500])
    except Exception:
        pass
    return state


def build_deep_research_graph() -> StateGraph:
    """Build the DeepResearch LangGraph with cyclic conditional edges."""
    workflow = StateGraph(DeepResearchState)
    workflow.add_node("recall", _node_recall)
    workflow.add_node("decompose", node_decompose_goal)
    workflow.add_node("search", node_search)
    workflow.add_node("synthesize", node_synthesize)
    workflow.add_node("report", _node_report)
    workflow.add_node("store", _node_store)
    workflow.add_node("distill", _node_distill)
    workflow.add_node("notify", _node_notify)
    workflow.set_entry_point("recall")
    workflow.add_edge("recall", "decompose")
    workflow.add_edge("decompose", "search")
    workflow.add_edge("search", "synthesize")
    workflow.add_conditional_edges("synthesize", route_after_synthesize, {"search": "search", "report": "report"})
    workflow.add_edge("report", "store")
    workflow.add_edge("store", "distill")
    workflow.add_edge("distill", "notify")
    workflow.add_edge("notify", END)
    return workflow.compile()
