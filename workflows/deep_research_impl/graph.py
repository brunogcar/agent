"""workflows/deep_research_impl/graph.py
Build and compile the DeepResearch LangGraph StateGraph.
"""
from __future__ import annotations
from typing import Optional

from langgraph.graph import StateGraph
from workflows.deep_research_impl.state import DeepResearchState
from workflows.deep_research_impl.nodes.decompose import node_decompose_goal
from workflows.deep_research_impl.nodes.search import node_search
from workflows.deep_research_impl.nodes.synthesize import node_synthesize
from workflows.deep_research_impl.routes import route_after_synthesize
from workflows.deep_research_impl.budget import log_event
from core.config import cfg
from core.memory import memory
from tools.notify import notify

def build_deep_research_graph() -> StateGraph:
    """Construct and return the compiled DeepResearch LangGraph."""
    workflow = StateGraph(DeepResearchState)

    # Nodes
    workflow.add_node("recall", _node_recall)
    workflow.add_node("decompose", node_decompose_goal)
    workflow.add_node("search", node_search)
    workflow.add_node("synthesize", node_synthesize)
    workflow.add_node("report", _node_report)
    workflow.add_node("notify", _node_notify)
    workflow.add_node("store", _node_store)
    workflow.add_node("distill", _node_distill)

    # Edges
    workflow.add_edge("recall", "decompose")
    workflow.add_edge("decompose", "search")
    workflow.add_edge("search", "synthesize")
    workflow.add_conditional_edges(
        "synthesize",
        route_after_synthesize,
        {
            "decompose": "decompose",  # Loop back
            "report": "report",         # Exit
        },
    )
    workflow.add_edge("report", "notify")
    workflow.add_edge("notify", "store")
    workflow.add_edge("store", "distill")
    workflow.set_entry_point("recall")

    return workflow.compile()

def _node_recall(state: DeepResearchState) -> DeepResearchState:
    """Recall relevant memories from episodic and semantic collections."""
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    try:
        results = memory.recall(query=goal, top_k=5, trace_id=tid)
        if not results:
            return {**state, "memory_context": ""}
        lines = []
        for r in results:
            t = r.get("type", "semantic")
            s = r.get("score", 0.0)
            txt = r.get("text", "")
            lines.append(f"[{t}|score={s:.2f}] {txt}")
        return {**state, "memory_context": "\n".join(lines)}
    except Exception:
        return {**state, "memory_context": ""}

def _node_report(state: DeepResearchState) -> DeepResearchState:
    """Build final report from knowledge base."""
    kb = state.get("knowledge_base", "")
    synthesis = state.get("synthesis", "")
    report = synthesis or kb
    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", 85.0)
    status = "success" if completeness >= threshold else "incomplete"
    return {
        **state,
        "report": report,
        "result": report,
        "status": status,
    }

def _node_notify(state: DeepResearchState) -> DeepResearchState:
    """Notify user that research is complete."""
    tid = state.get("trace_id", "")
    result = state.get("result", "")
    status = state.get("status", "unknown")
    msg = result or f"DeepResearch {status}: {tid}"
    try:
        notify(
            action="send",
            title="DeepResearch",
            message=msg[:500],
        )
    except Exception:
        pass
    return state

def _node_store(state: DeepResearchState) -> DeepResearchState:
    """Store final result to semantic and episodic memory."""
    tid = state.get("trace_id", "")
    result = state.get("result", "")
    goal = state.get("goal", "")
    status = state.get("status", "unknown")
    try:
        memory.store_semantic(
            text=f"Deep Research: {result[:800]}",
            importance=6,
            tags="deep_research",
            trace_id=tid,
        )
        memory.store_episodic(
            text=f"Completed deep research workflow: '{goal[:60]}'",
            importance=5,
            goal=goal,
            outcome=status,
            tools_used="tavily,web,browser,llm",
            trace_id=tid,
        )
    except Exception:
        pass
    return state

def _node_distill(state: DeepResearchState) -> DeepResearchState:
    """Placeholder for workflow distillation (sleep_learn integration).

    TODO: Wire up sleep_learn.distill_workflow when available.
    """
    return state
