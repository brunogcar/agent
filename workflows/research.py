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

import json

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from langgraph.graph import StateGraph, END
from workflows.base   import WorkflowState, node_step, node_error, node_done
from workflows.helpers.citations import citations
from core.memory_backend.procedural.distill import distill_workflow


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
    """Search the web for relevant URLs."""
    from tools.web import web
    goal = state.get("goal", "")
    node_step(state, "search", "searching web for URLs", query=goal[:60])

    result = web(action="search", query=goal, max_results=3)

    if result.get("status") != "success" or not result.get("results"):
        err = result.get("error", "no results returned")
        node_step(state, "search", f"search failed: {err}")
        return {**state, "search_results": ""}

    valid_urls = []
    for r in result["results"]:
        if r.get("url"):
            valid_urls.append({"url": r["url"], "title": r.get("title", ""), "snippet": r.get("snippet", "")})
            
    if not valid_urls:
        node_step(state, "search", "no valid URLs found")
        return {**state, "search_results": ""}

    # Store as JSON string for the parallel scraper node
    return {**state, "search_results": json.dumps(valid_urls)}

def _scrape_and_summarize(url: str, title: str, goal: str, trace_id: str) -> dict:
    """Worker function: scrape URL and summarize with Executor."""
    from tools.web import web
    from core.llm import llm
    from core.runtime.activity_tracker import tracker
    from core.config import cfg
    
    # 1. Scrape
    scrape_res = web(action="read", url=url)
    if scrape_res.get("status") != "success":
        return {"url": url, "title": title, "status": "failed", "error": scrape_res.get("error", "scrape failed")}
        
    text = scrape_res.get("text", "")
    if len(text) < 300:
        return {"url": url, "title": title, "status": "failed", "error": "too short"}
        
    # Truncate to web_max_text_chars to prevent context overflow
    text = text[:cfg.web_max_text_chars]
    
    # 2. Summarize (with inference slot)
    try:
        with tracker.inference_slot(timeout=30.0):
            resp = llm.complete(
                role="executor",
                system="You are a research assistant. Summarize the given web page in 3-5 bullet points, focusing strictly on facts relevant to the user's goal. Do not include introductory filler.",
                user=f"Goal: {goal}\n\nSummarize the following text:\n\n{text}",
                max_tokens=cfg.worker_max_tokens,
                timeout=cfg.worker_timeout,
                trace_id=trace_id
            )
        if not resp.ok:
            return {"url": url, "title": title, "status": "failed", "error": f"LLM failed: {resp.error}"}
            
        return {"url": url, "title": title, "status": "success", "summary": resp.text}
    except TimeoutError:
        return {"url": url, "title": title, "status": "failed", "error": "inference slot timeout"}
    except Exception as e:
        return {"url": url, "title": title, "status": "failed", "error": str(e)}

def node_parallel_scrape(state: WorkflowState) -> WorkflowState:
    """Coordinator: scrape and summarize URLs in parallel."""
    from core.config import cfg
    from workflows.helpers.citations import citations
    
    raw_results = state.get("search_results", "")
    if not raw_results:
        return {**state, "search_results": ""}
        
    try:
        urls_data = json.loads(raw_results)
    except Exception:
        return {**state, "search_results": ""}
        
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    
    node_step(state, "parallel_scrape", f"spawning {len(urls_data)} workers")
    
    dossier_parts = []
    citation_idx = 1
    
    with ThreadPoolExecutor(max_workers=cfg.max_concurrent_workers) as executor:
        future_to_data = {
            executor.submit(_scrape_and_summarize, item["url"], item.get("title", ""), goal, tid): item 
            for item in urls_data
        }
        
        for future in as_completed(future_to_data, timeout=cfg.worker_timeout + 30):
            item = future_to_data[future]
            try:
                res = future.result(timeout=cfg.worker_timeout)
            except TimeoutError:
                res = {"url": item["url"], "title": item.get("title", ""), "status": "failed", "error": "global timeout"}
            except Exception as e:
                res = {"url": item["url"], "title": item.get("title", ""), "status": "failed", "error": str(e)}
                
            if res["status"] == "success":
                # Register citation
                if tid and res["url"]:
                    citations.add(tid, url=res["url"], title=res["title"], snippet=res["summary"][:200])
                
                dossier_parts.append(
                    f"### [Source {citation_idx}] {res['title']}\n"
                    f"URL: {res['url']}\n\n"
                    f"{res['summary']}\n"
                )
                citation_idx += 1
            else:
                node_step(state, "parallel_scrape", f"worker failed for {item['url']}: {res['error']}")
                
    if not dossier_parts:
        node_step(state, "parallel_scrape", "all workers failed")
        return {**state, "search_results": ""}
        
    dossier = "\n\n".join(dossier_parts)
    
    # Hard cap the dossier to prevent context explosion at synthesis time
    max_dossier_chars = cfg.web_max_text_chars * 2
    if len(dossier) > max_dossier_chars:
        dossier = dossier[:max_dossier_chars] + "\n\n[...TRUNCATED DUE TO LENGTH...]"
        
    node_step(state, "parallel_scrape", f"built dossier with {citation_idx-1} sources ({len(dossier)} chars)")
    return {**state, "search_results": dossier}


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


def node_distill(state: WorkflowState) -> WorkflowState:
    """Extract procedural rules from the completed research workflow."""
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    result = state.get("result", "")
    
    if not result or state.get("status") == "failed":
        return state
        
    trace_text = f"GOAL: {goal}\n\nOUTCOME: Success\n\nSYNTHESIS:\n{result[:2000]}"
    
    try:
        # Non-blocking best-effort distillation
        distill_workflow(trace_text=trace_text, trace_id=tid)
    except Exception:
        pass  # Never fail the workflow if distillation fails
        
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
    g.add_node("parallel_scrape", node_parallel_scrape)
    g.add_node("synthesize", node_synthesize)
    g.add_node("store",      node_store)
    g.add_node("distill",    node_distill)
    g.add_node("notify",     node_notify)

    g.set_entry_point("recall")

    g.add_edge("recall",  "search")
    g.add_edge("search", "parallel_scrape")

    g.add_conditional_edges(
        "parallel_scrape",
        route_after_search,
        {"synthesize": "synthesize", "failed": END},
    )

    g.add_conditional_edges(
        "synthesize",
        route_after_synthesize,
        {"store": "store", "failed": END},
    )

    g.add_edge("store",   "distill")
    g.add_edge("distill", "notify")
    g.add_edge("notify", END)

    return g.compile()

