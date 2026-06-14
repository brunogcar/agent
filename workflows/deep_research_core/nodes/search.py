"""workflows/deep_research_core/nodes/search.py"""
from __future__ import annotations
import logging
from core.config import cfg
from core.citations import citations
from tools.web import web
from tools.tavily import tavily
from tools.browser import browser
from core.llm import llm
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.budget import decrement_api_calls, decrement_browser_actions, log_event
from workflows.deep_research_core.constants import JS_HEAVY_HINTS

logger = logging.getLogger(__name__)

def _is_complex_query(query: str) -> bool:
    q = query.lower()
    return len(query.split()) >= 8 or any(w in q for w in ("compare", "vs", "versus", "difference", "pros and cons"))

def _is_js_heavy(query: str) -> bool:
    q = query.lower()
    return any(h in q for h in JS_HEAVY_HINTS)

def _is_js_wall(text: str) -> bool:
    if not text or len(text.strip()) < 50:
        return True
    indicators = ["enable javascript", "enable js", "javascript required", "js required", "please enable", "turn on javascript", "javascript is disabled"]
    return any(ind in text.lower() for ind in indicators)

def _select_tool(state: DeepResearchState, query: str) -> str:
    if not cfg.tavily_api_key:
        return "web"
    if _is_js_heavy(query) and state.get("budget_browser_actions", 0) > 0:
        return "browser"
    if _is_complex_query(query) and state.get("budget_api_calls", 0) > 0:
        return "tavily"
    if state.get("budget_api_calls", 0) > 0:
        return "tavily"
    return "web"

def _execute_search(query: str, tool: str, trace_id: str) -> dict:
    if tool == "tavily":
        return tavily(action="search", query=query, max_results=5, include_answer=False, trace_id=trace_id)
    elif tool == "web":
        return web(action="search", query=query, max_results=5, trace_id=trace_id)
    elif tool == "browser":
        return web(action="search", query=query, max_results=5, trace_id=trace_id)
    else:
        return {"status": "error", "error": "Unknown tool: " + tool}

def _execute_search_with_fallback(query: str, state: DeepResearchState) -> dict:
    tid = state.get("trace_id", "")
    tool = _select_tool(state, query)
    if tool == "tavily":
        result = _execute_search(query, "tavily", tid)
        if result.get("status") != "success" or not result.get("data", {}).get("results"):
            log_event(state, "search_fallback", {"from": "tavily", "to": "web", "reason": result.get("error", "empty_results")})
            result = _execute_search(query, "web", tid)
        return result
    return _execute_search(query, tool, tid)

def _try_browser_fallback(url: str, tid: str) -> str:
    try:
        nav = browser(action="navigate", url=url, trace_id=tid, timeout=30, headless=True)
        if nav.get("status") != "success":
            return ""
        txt = browser(action="text_content", selector="body", trace_id=tid, timeout=30)
        if txt.get("status") != "success":
            return ""
        return txt.get("data", {}).get("text", "")
    except Exception:
        return ""

def _summarize_evidence(text: str, query: str, goal: str) -> str:
    prompt = f"Summarize into 2-3 bullet points for query '{query}' and goal '{goal}'.\n\nText:\n{text[:3000]}"
    try:
        result = llm.complete(role="summarize", system="You are a research assistant. Summarize text concisely.", user=prompt, max_tokens=300, timeout=30)
        if result.ok:
            return result.text.strip()
    except Exception:
        pass
    return text[:500]

def _extract_evidence(search_result: dict, query: str, tool: str, goal: str, trace_id: str, failed: list, state: DeepResearchState, iteration: int, seen_urls: set) -> list[dict]:
    evidence = []
    data = search_result.get("data", {})
    results = data.get("results", [])
    for idx, r in enumerate(results[:3]):
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        if any(f.get("url") == url for f in failed):
            continue
        title = r.get("title", "")
        text = r.get("text", "") or r.get("content", "")
        if not text or len(text) < 100:
            failed.append({"url": url, "reason": "no_content" if not text else "too_short", "iteration": iteration})
            continue
        if len(text) < 300 or _is_js_heavy(query):
            browser_text = _try_browser_fallback(url, trace_id)
            if browser_text and len(browser_text) >= 100:
                text = browser_text
                tool = "browser"
        summary = _summarize_evidence(text, query, goal)
        citations.add(trace_id, url=url, title=title, snippet=summary[:300])
        evidence.append({"query": query, "url": url, "title": title, "summary": summary, "source": tool})
    return evidence

def node_search(state: DeepResearchState) -> DeepResearchState:
    queries = state.get("pending_queries", [])
    # Always increment iteration ? even empty-query passes count as iterations
    updates = {
        "iteration": state.get("iteration", 0) + 1,
    }
    if not queries:
        updates["extracted_evidence"] = []
        updates["pending_queries"] = []
        updates["failed_sources"] = list(state.get("failed_sources", []))
        updates["consecutive_empty_iterations"] = state.get("consecutive_empty_iterations", 0) + 1
        return updates
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    failed = list(state.get("failed_sources", []))
    all_evidence: list[dict] = []
    seen_urls: set = set()
    for query in queries:
        search_result = _execute_search_with_fallback(query, {**state, **updates})
        if search_result.get("status") == "success":
            updates.update(decrement_api_calls({**state, **updates}))
            new_evidence = _extract_evidence(search_result, query, "tavily", goal, tid, failed, {**state, **updates}, updates["iteration"], seen_urls)
            all_evidence.extend(new_evidence)
            if not new_evidence:
                log_event({**state, **updates}, "empty_results", {"query": query, "tool": "tavily"})
        else:
            log_event({**state, **updates}, "search_error", {"query": query, "error": search_result.get("error", "unknown")})
    updates.update(decrement_browser_actions({**state, **updates}))
    updates["extracted_evidence"] = all_evidence
    updates["pending_queries"] = []
    updates["failed_sources"] = failed
    if not all_evidence:
        updates["consecutive_empty_iterations"] = state.get("consecutive_empty_iterations", 0) + 1
    else:
        updates["consecutive_empty_iterations"] = 0
    return updates
