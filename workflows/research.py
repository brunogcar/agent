"""workflows/research.py -- Research workflow.

Pattern:
  recall -> search -> scrape -> synthesize -> report -> store -> distill -> notify

Each node is a pure function WorkflowState -> WorkflowState.
LangGraph wires them into a directed graph with conditional edges.

Browser Fallback (Phase 8):
  When web(read) returns < 300 chars, the worker marks the URL for browser
  fallback. After the parallel pool closes, browser(navigate + text_content)
  is called sequentially (browser is NOT_PARALLEL_SAFE).

Usage:
  from workflows.base import run_workflow

  result = run_workflow(
      workflow_type = "research",
      goal = "What are the best practices for ChromaDB in production?",
  )
  print(result["result"])
"""
from __future__ import annotations

import json
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from langgraph.graph import StateGraph, END
from workflows.base import WorkflowState, node_step, node_error, node_done
from core.citations import citations
from core.memory_backend.procedural.distill import distill_workflow

# Thread-local guard to prevent nested parallel scrape (deadlock prevention)
_parallel_scrape_active = threading.local()


def _is_nested_parallel() -> bool:
    """Check if node_parallel_scrape is already active in this thread.

    Prevents deadlock when a worker thread calls node_parallel_scrape
    recursively (e.g. via autocode tool invocation).
    """
    return getattr(_parallel_scrape_active, "active", False)


# -- Nodes --------------------------------------------------------------------

def node_recall(state: WorkflowState) -> WorkflowState:
    """Recall relevant memories before hitting the web."""
    from core.memory_engine import memory

    goal = state.get("goal", "")
    node_step(state, "recall", "checking memory", goal=goal[:60])

    results = memory.recall(
        query=goal,
        top_k=5,
        trace_id=state.get("trace_id", "")
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
        # Mark for browser fallback instead of failing immediately
        return {"url": url, "title": title, "status": "needs_browser", "error": "too short"}

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


def _browser_fallback_scrape(url: str, title: str, goal: str, trace_id: str) -> dict:
    """Sequential browser fallback for JS-heavy pages. Called outside the thread pool."""
    from tools.browser import browser
    from core.llm import llm
    from core.runtime.activity_tracker import tracker
    from core.config import cfg

    # Generate a stable trace ID for this fallback session so navigate + text_content
    # share the same browser context. If trace_id is empty, use a local UUID.
    fallback_tid = trace_id or f"fb_{uuid.uuid4().hex[:8]}"

    try:
        # Navigate
        nav_res = browser(
            action="navigate",
            url=url,
            trace_id=fallback_tid,
            timeout=cfg.research_browser_fallback_timeout,
        )
        if nav_res.get("status") != "success":
            return {"url": url, "title": title, "status": "failed", "error": nav_res.get("error", "browser navigate failed")}

        # Extract text
        text_res = browser(
            action="text_content",
            selector="body",
            trace_id=fallback_tid,
            timeout=cfg.research_browser_fallback_timeout,
        )
        if text_res.get("status") != "success":
            return {"url": url, "title": title, "status": "failed", "error": text_res.get("error", "browser text_content failed")}

        text = text_res.get("data", {}).get("text", "")
        if len(text) < 300:
            return {"url": url, "title": title, "status": "failed", "error": "browser text too short"}

        text = text[:cfg.web_max_text_chars]

        # Summarize
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

    except Exception as e:
        return {"url": url, "title": title, "status": "failed", "error": f"browser fallback: {e}"}


def node_parallel_scrape(state: WorkflowState) -> WorkflowState:
    """Coordinator: scrape and summarize URLs in parallel, with sequential browser fallback."""
    from core.config import cfg
    from core.citations import citations

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

    # Guard against nested parallel execution (prevents ThreadPoolExecutor deadlock)
    if _is_nested_parallel():
        node_step(state, "parallel_scrape", "nested parallel scrape rejected")
        return {**state, "search_results": ""}
    _parallel_scrape_active.active = True
    try:
        dossier_parts = []
        citation_idx = 1
        needs_browser = []

        # 1. Parallel web scraping
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
                elif res["status"] == "needs_browser":
                    needs_browser.append({"url": res["url"], "title": res["title"]})
                else:
                    node_step(state, "parallel_scrape", f"worker failed for {item['url']}: {res['error']}")

        # 2. Sequential browser fallback (respects browser's global lock)
        for item in needs_browser[:cfg.research_browser_fallback_max]:
            res = _browser_fallback_scrape(item["url"], item["title"], goal, tid)
            if res["status"] == "success":
                if tid and res["url"]:
                    citations.add(tid, url=res["url"], title=res["title"], snippet=res["summary"][:200])

                dossier_parts.append(
                    f"### [Source {citation_idx}] {res['title']}\n"
                    f"URL: {res['url']}\n\n"
                    f"{res['summary']}\n"
                )
                citation_idx += 1
                node_step(state, "parallel_scrape", f"browser fallback succeeded for {item['url']}")
            else:
                node_step(state, "parallel_scrape", f"browser fallback failed for {item['url']}: {res['error']}")

        if not dossier_parts:
            node_step(state, "parallel_scrape", "all workers failed")
            return {**state, "search_results": ""}

        dossier = "\n\n".join(dossier_parts)

        # Hard cap the dossier to prevent context explosion at synthesis time.
        # Cut at paragraph boundary to preserve markdown structure and citations.
        max_dossier_chars = cfg.web_max_text_chars * 2
        if len(dossier) > max_dossier_chars:
            trunc_point = dossier.rfind("\n\n", 0, max_dossier_chars)
            if trunc_point == -1:
                trunc_point = dossier.rfind("\n", 0, max_dossier_chars)
            if trunc_point == -1:
                trunc_point = max_dossier_chars
            dossier = dossier[:trunc_point] + "\n\n[... dossier truncated: " + str(len(dossier) - trunc_point) + " chars omitted ...]"

        node_step(state, "parallel_scrape", f"built dossier with {citation_idx-1} sources ({len(dossier)} chars)")
        return {**state, "search_results": dossier}
    finally:
        _parallel_scrape_active.active = False


def node_synthesize(state: WorkflowState) -> WorkflowState:
    """Synthesize web results + memory into a coherent answer.

    Uses agent(role="research") to synthesize scraped web content and
    recalled memories into a single coherent response. The research role
    has a 120s timeout and uses the Executor model (capable, slower).
    """
    from tools.agent import agent  # thin facade; prompts/roles live in agent_ops/  # [PHASE-3] Migrated from tools.agent_tool → tools.agent

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

    if not r.get("status") == "success":
        return node_error(state, "synthesize",
                          f"Agent failed: {r.get('error', 'unknown')}")

    node_step(state, "synthesize", "synthesis complete",
              elapsed=r.get("elapsed", 0))
    return {**state, "result": r["text"]}


def node_report(state: WorkflowState) -> WorkflowState:
    """Generate research dossier report with citations."""
    from tools.report import report as report_tool

    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    result = state.get("result", "")

    if not result:
        return state

    sources = citations.get_sources(tid) if tid else []
    source_list = [{"title": s.get("title", "Untitled"), "url": s.get("url", "")} for s in sources]

    sections = [
        {"title": "Research Goal", "content": goal},
        {"title": "Findings", "content": result[:20000] if result else "No findings generated."},
    ]

    try:
        report_tool(
            action="report",
            trace_id=tid,
            title=f"Research: {goal[:60]}",
            data=None,
            config={"sections": sections, "sources": source_list},
            preset="research",
        )
        node_step(state, "report", "generated research dossier")
    except Exception as e:
        node_step(state, "report", f"report generation failed: {e}")

    return state


def node_store(state: WorkflowState) -> WorkflowState:
    """Store research findings in semantic memory."""
    from core.memory_engine import memory

    result = state.get("result", "")
    goal = state.get("goal", "")

    if not result:
        return state

    node_step(state, "store", "saving to semantic memory")

    memory.store_semantic(
        text = f"Research on '{goal}':\n{result[:800]}",
        importance = 6,
        tags = "research,auto",
        trace_id = state.get("trace_id", "")
    )

    memory.store_episodic(
        text = f"Completed research workflow: '{goal[:60]}'",
        importance = 5,
        goal = goal,
        outcome = "success",
        tools_used = "web,agent,memory",
        trace_id = state.get("trace_id", "")
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

    goal = state.get("goal", "")
    result = state.get("result", "")
    tid = state.get("trace_id", "")
    sources = citations.get_sources(tid) if tid else []

    notify(
        action = "send",
        title = "Research complete",
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
    """After synthesis: generate report, then store."""
    if state.get("status") == "failed":
        return "failed"
    return "report"


# -- Graph builder ------------------------------------------------------------

def build_research_graph() -> StateGraph:
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
        {"report": "report", "failed": END},
    )

    g.add_edge("report", "store")
    g.add_edge("store", "distill")
    g.add_edge("distill", "notify")
    g.add_edge("notify", END)

    return g.compile()
