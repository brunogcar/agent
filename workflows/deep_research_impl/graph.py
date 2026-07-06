"""workflows/deep_research_impl/graph.py
Build and compile the DeepResearch LangGraph StateGraph.

[v1.1] Added WORKFLOW_METADATA for MCP client introspection (mirrors research /
understand / data). Converted inline _node_* helpers to partial-dict returns
(P1 #7). Wired citations into _node_report + _node_notify so sources collected
by node_search actually surface in the report and artifacts (they were collected
and discarded). Fixed _node_recall silent memory failure (P1 #8) and
_node_store 800-char truncation (P1 #10).
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
from core.tracer import tracer
from core.memory_engine import memory
from core.citations import citations
from tools.notify import notify


# [v1.1] WORKFLOW_METADATA for MCP client introspection.
# Deep research is cyclic: synthesize -> route (decompose loop OR report exit).
WORKFLOW_METADATA = {
    "name": "deep_research",
    "version": "1.1",
    "description": "Iterative deep research: recall -> decompose -> search -> synthesize (loop) -> report -> notify -> store -> distill",
    "nodes": [
        {"name": "recall", "description": "Recall relevant memories from episodic + semantic collections"},
        {"name": "decompose", "description": "Planner LLM breaks goal into 3-5 sub-queries"},
        {"name": "search", "description": "Execute sub-queries via Tavily -> web -> browser fallback, extract evidence"},
        {"name": "synthesize", "description": "Synthesize evidence + evaluate completeness + check convergence"},
        {"name": "report", "description": "Build final report from synthesis + knowledge base, append sources"},
        {"name": "notify", "description": "Notify user of completion, surface source URLs as artifacts"},
        {"name": "store", "description": "Store full result in semantic + episodic memory"},
        {"name": "distill", "description": "Placeholder for sleep_learn workflow distillation"},
    ],
    "edges": [
        {"from": "recall", "to": "decompose"},
        {"from": "decompose", "to": "search"},
        {"from": "search", "to": "synthesize"},
        {"from": "synthesize", "to": "decompose", "condition": "continue loop (below threshold or not converged)"},
        {"from": "synthesize", "to": "report", "condition": "exit (completeness >= threshold AND converged, OR hard cap, OR stuck)"},
        {"from": "report", "to": "notify"},
        {"from": "notify", "to": "store"},
        {"from": "store", "to": "distill"},
    ],
}


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

def _node_recall(state: DeepResearchState) -> dict:
    """Recall relevant memories from episodic and semantic collections.

    [P1 #8] Memory failure now logged via tracer.error (was silent).
    [P1 #7] Returns partial dict (was {**state, ...}).
    """
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    try:
        results = memory.recall(query=goal, top_k=5, trace_id=tid)
        if not results:
            return {"memory_context": ""}
        lines = []
        for r in results:
            t = r.get("type", "semantic")
            s = r.get("score", 0.0)
            txt = r.get("text", "")
            lines.append(f"[{t}|score={s:.2f}] {txt}")
        return {"memory_context": "\n".join(lines)}
    except Exception as e:
        # [P1 #8] Log the failure instead of silently returning empty context.
        tracer.error(tid, "recall", f"memory recall failed: {e}")
        return {"memory_context": ""}

def _node_report(state: DeepResearchState) -> dict:
    """Build final report from knowledge base + synthesis, append sources.

    [v1.1] Now appends a Sources section from the citation tracker (sources
    were collected by node_search via citations.add() but never surfaced
    before). Returns partial dict (was {**state, ...}).
    """
    tid = state.get("trace_id", "")
    kb = state.get("knowledge_base", "")
    synthesis = state.get("synthesis", "")
    report = synthesis or kb
    completeness = state.get("completeness", 0.0)
    threshold = state.get("completeness_threshold", 85.0)
    status = "success" if completeness >= threshold else "incomplete"

    # [v1.1] Surface collected sources in the report.
    sources = citations.get_sources(tid) if tid else []
    if sources:
        src_list = "\n".join(
            f"[{s['number']}] {s.get('title', s['url'])} — {s['url']}"
            for s in sources
        )
        report = f"{report}\n\n## Sources\n{src_list}"

    return {
        "report": report,
        "result": report,
        "status": status,
    }

def _node_notify(state: DeepResearchState) -> dict:
    """Notify user that research is complete; surface source URLs as artifacts.

    [P1 #7] Returns partial dict (was `return state`).
    [v1.1] Returns artifacts = source URLs (mirrors research workflow's notify).
    [P1 #8] notify() failure logged via tracer.error (was silent pass).
    """
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
    except Exception as e:
        tracer.error(tid, "notify", f"notification failed: {e}")

    # [v1.1] Surface source URLs as artifacts (list[str], like research).
    sources = citations.get_sources(tid) if tid else []
    artifacts = [s["url"] for s in sources if s.get("url")]
    return {"artifacts": artifacts}

def _node_store(state: DeepResearchState) -> dict:
    """Store full result to semantic and episodic memory.

    [P1 #10] Store full result (was result[:800] — truncated, made semantic
    memory nearly useless for long research; same fix as research workflow #7).
    [P1 #7] Returns partial dict (was {**state, ...}).
    [P1 #8] Memory failure logged via tracer.error (was silent pass).
    """
    tid = state.get("trace_id", "")
    result = state.get("result", "")
    goal = state.get("goal", "")
    status = state.get("status", "unknown")
    try:
        # [P1 #10] Full result — semantic memory is for content retrieval.
        memory.store_semantic(
            text=f"Deep Research: {result}",
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
    except Exception as e:
        tracer.error(tid, "store", f"memory store failed: {e}")
    return {}

def _node_distill(state: DeepResearchState) -> dict:
    """Placeholder for workflow distillation (sleep_learn integration).

    TODO: Wire up sleep_learn.distill_workflow when available.
    """
    return {}
