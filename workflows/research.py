"""
workflows/research.py -- Research workflow.

Pattern:
  recall -> search -> scrape -> synthesize -> store -> notify

Each node is a pure function WorkflowState -> WorkflowState.
LangGraph wires them into a directed graph with conditional edges.

Usage:
    from workflows.base import run_workflow

    result = run_workflow(
        workflow_type = "research",
        goal          = "What are the best practices for ChromaDB in production?",
    )
    print(result["result"])
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from workflows.base   import WorkflowState, node_step, node_error, node_done
from core.citations   import citations


# -- Nodes --------------------------------------------------------------------

def node_recall(state: WorkflowState) -> WorkflowState:
    """Recall relevant memories before hitting the web."""
    from core.memory import memory

    goal = state.get("goal", "")
    node_step(state, "recall", "checking memory", goal=goal[:60])

    results = memory.recall(
        query=goal,
        top_k=5,
        trace_id=state.get("trace_id", ""),
    )

    if results:
        ctx = "\n".join(
            f"[{r['type']}|score={r['score']:.1f}] {r['text']}"
            for r in results
        )
        node_step(state, "recall", f"found {len(results)} memories")
        return {**state, "memory_context": ctx}

    node_step(state, "recall", "no relevant memories found")
    return {**state, "memory_context": ""}


def node_search(state: WorkflowState) -> WorkflowState:
    """Search the web for relevant sources. Filters 403/empty results."""
    from tools.web import web

    goal = state.get("goal", "")
    node_step(state, "search", "searching web", query=goal[:60])

    result = web(action="search_and_read", query=goal, max_results=3)

    if result.get("status") != "success" or not result.get("results"):
        err = result.get("error", "no results returned")
        node_step(state, "search", f"search failed: {err}")
        return {**state, "search_results": ""}

    # Filter out 403/access-denied/empty responses
    MIN_CHARS = 300
    ACCESS_DENIED = ["403 forbidden", "access denied", "just a moment",
                     "enable javascript", "please verify", "captcha"]
    valid = []
    for r in result["results"]:
        text  = r.get("text", "")
        lower = text.lower()
        if len(text) < MIN_CHARS:
            node_step(state, "search",
                      f"skipped {r.get('url','')[:50]} -- too short ({len(text)} chars)")
            continue
        if any(marker in lower[:200] for marker in ACCESS_DENIED):
            node_step(state, "search",
                      f"skipped {r.get('url','')[:50]} -- access denied")
            continue
        valid.append(r)

    if not valid:
        node_step(state, "search", "all results filtered (403/empty)")
        return {**state, "search_results": ""}

    parts = []
    tid   = state.get("trace_id", "")
    for r in valid:
        url   = r.get("url",   "")
        title = r.get("title", "")
        text  = r.get("text",  "")
        # Register source for citation tracking
        if tid and url:
            snippet = text[:200].replace("\n", " ")
            citations.add(tid, url=url, title=title, snippet=snippet)
        parts.append(
            f"SOURCE: {title} {citations.cite(tid, url)}\nURL: {url}\n\n"
            f"{text[:2000]}"
        )
    combined = "\n\n---\n\n".join(parts)
    node_step(state, "search",
              f"scraped {len(valid)} valid sources, {citations.count(tid)} citations",
              filtered=result.get('scraped_count',0) - len(valid))
    return {**state, "search_results": combined}


def node_synthesize(state: WorkflowState) -> WorkflowState:
    """Synthesize web results + memory into a coherent answer."""
    from tools.agent_tool import agent

    goal           = state.get("goal", "")
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
        role     = "research",
        task     = f"Synthesise the provided sources to answer: {goal}",
        content  = content,
        trace_id = state.get("trace_id", ""),
    )

    if not r.get("status") == "success":
        return node_error(state, "synthesize",
                          f"Agent failed: {r.get('error', 'unknown')}")

    node_step(state, "synthesize", "synthesis complete",
              elapsed=r.get("elapsed", 0))
    return {**state, "result": r["text"]}


def node_store(state: WorkflowState) -> WorkflowState:
    """Store research findings in semantic memory."""
    from core.memory import memory

    result = state.get("result", "")
    goal   = state.get("goal", "")

    if not result:
        return state

    node_step(state, "store", "saving to semantic memory")

    memory.store_semantic(
        text       = f"Research on '{goal}':\n{result[:800]}",
        importance = 6,
        tags       = "research,auto",
        trace_id   = state.get("trace_id", ""),
    )

    memory.store_episodic(
        text       = f"Completed research workflow: '{goal[:60]}'",
        importance = 5,
        goal       = goal,
        outcome    = "success",
        tools_used = "web,agent,memory",
        trace_id   = state.get("trace_id", ""),
    )

    return state


def node_notify(state: WorkflowState) -> WorkflowState:
    """Send completion notification and mark workflow done."""
    from tools.notify import notify
    from workflows.base import node_done

    goal    = state.get("goal", "")
    result  = state.get("result", "")
    tid     = state.get("trace_id", "")
    sources = citations.get_sources(tid) if tid else []

    notify(
        action  = "send",
        title   = "Research complete",
        message = f"{goal[:50]}: {result[:80]}...",
    )
    return node_done(state, result=result or "Research complete",
                     artifacts=[{"sources": sources}])


# -- Routing ------------------------------------------------------------------

def route_after_search(state: WorkflowState) -> str:
    """After search: always synthesize (even with empty results from memory)."""
    sr = state.get("search_results", "")
    mc = state.get("memory_context", "")
    if not sr and not mc:
        return "failed"
    return "synthesize"


def route_after_synthesize(state: WorkflowState) -> str:
    if state.get("status") == "failed":
        return "failed"
    return "store"


# -- Graph builder ------------------------------------------------------------

def build_research_graph() -> StateGraph:
    """Build and compile the research workflow graph."""
    g = StateGraph(WorkflowState)

    g.add_node("recall",     node_recall)
    g.add_node("search",     node_search)
    g.add_node("synthesize", node_synthesize)
    g.add_node("store",      node_store)
    g.add_node("notify",     node_notify)

    g.set_entry_point("recall")

    g.add_edge("recall", "search")

    g.add_conditional_edges(
        "search",
        route_after_search,
        {"synthesize": "synthesize", "failed": END},
    )

    g.add_conditional_edges(
        "synthesize",
        route_after_synthesize,
        {"store": "store", "failed": END},
    )

    g.add_edge("store",  "notify")
    g.add_edge("notify", END)

    return g.compile()

