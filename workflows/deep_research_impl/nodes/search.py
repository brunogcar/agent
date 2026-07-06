"""workflows/deep_research_impl/nodes/search.py
Search node: execute sub-queries, extract evidence, manage budget.
"""
from __future__ import annotations
import logging
from typing import Optional

from core.config import cfg
from core.citations import citations
from tools.web import web
from tools.tavily import tavily
from tools.browser import browser
from core.llm import llm
from workflows.deep_research_impl.state import DeepResearchState
from workflows.deep_research_impl.budget import (
    decrement_api_calls,
    decrement_browser_actions,
    log_event,
    is_browser_budget_exhausted,
)
from workflows.deep_research_impl.constants import JS_HEAVY_HINTS

logger = logging.getLogger(__name__)

def _is_complex_query(query: str) -> bool:
    """Heuristic: queries with 8+ words or comparison keywords are complex."""
    q = query.lower()
    return len(query.split()) >= 8 or any(
        w in q for w in ("compare", "vs", "versus", "difference", "pros and cons")
    )

def _is_js_wall(text: str) -> bool:
    """Heuristic: check if returned page content indicates a JS wall or is too short.

    Returns True if the text is empty, very short (< 100 chars), or contains
    common JavaScript-required indicators.
    """
    if not text or len(text) < 100:
        return True
    indicators = (
        "enable javascript", "javascript required", "js required",
        "please enable", "browser does not support javascript",
        "loading...", "please wait", "turn on javascript",
    )
    lower = text.lower()
    return any(ind in lower for ind in indicators)

def _select_tool(state: DeepResearchState, query: str) -> str:
    """Choose search tool based on budget and complexity.

    Browser is NEVER selected here -- it is only used as a fallback in
    _extract_evidence when web returns short or JS-walled content.
    """
    if not cfg.tavily_api_key:
        return "web"
    if _is_complex_query(query) and state.get("budget_api_calls", 0) > 0:
        return "tavily"
    if state.get("budget_api_calls", 0) > 0:
        return "tavily"
    return "web"

def _execute_search(query: str, tool: str, trace_id: str) -> dict:
    """Execute a single search query with the selected tool."""
    if tool == "tavily":
        return tavily(
            action="search",
            query=query,
            max_results=5,
            include_answer=False,
            trace_id=trace_id,
        )
    elif tool == "web":
        return web(
            action="search",
            query=query,
            max_results=5,
            trace_id=trace_id,
        )
    else:
        return {"status": "error", "error": f"Unknown tool: {tool}"}

def _execute_search_with_fallback(query: str, state: DeepResearchState) -> tuple[dict, str, dict]:
    """Execute search with tavily -> web fallback on failure or empty results.

    Returns (result, actual_tool, state_updates).
    """
    tid = state.get("trace_id", "")
    tool = _select_tool(state, query)
    updates: dict = {}

    if tool == "tavily":
        # [P0 #4] Decrement API budget on ATTEMPT, not success. Tavily is a
        # paid API that charges per call regardless of outcome; decrementing
        # only on success meant failed calls consumed real quota but never
        # reduced the tracker, so the workflow kept retrying Tavily thinking
        # it had headroom. Web (SearXNG) is free and must NOT decrement.
        updates.update(decrement_api_calls({**state, **updates}))
        result = _execute_search(query, "tavily", tid)
        if result.get("status") != "success" or not result.get("data", {}).get("results"):
            updates = log_event(
                {**state, **updates}, "search", "fallback",
                reason="tavily->web: " + result.get("error", "empty_results")
            )
            result = _execute_search(query, "web", tid)
            return result, "web", updates
        return result, "tavily", updates

    return _execute_search(query, tool, tid), tool, updates

def _try_browser_fallback(url: str, tid: str, state: dict) -> tuple[str, dict]:
    """Attempt to extract text via browser for JS-heavy or short-content pages.

    Returns (text, state_updates). Respects browser budget.
    """
    updates: dict = {}
    if is_browser_budget_exhausted(state):
        return "", updates
    try:
        updates.update(decrement_browser_actions(state))
        state = {**state, **updates}
        nav = browser(action="navigate", url=url, trace_id=tid, timeout=30, headless=True)
        if nav.get("status") != "success":
            return "", updates
        updates.update(decrement_browser_actions(state))
        state = {**state, **updates}
        txt = browser(action="text_content", selector="body", trace_id=tid, timeout=30)
        if txt.get("status") != "success":
            return "", updates
        return txt.get("data", {}).get("text", ""), updates
    except Exception:
        return "", updates

def _summarize_evidence(text: str, query: str, goal: str) -> str:
    """Summarize extracted text into 2-3 bullet points relevant to query and goal."""
    prompt = f"""Summarize the following text into 2-3 bullet points relevant to the query
'{query}' and the overall research goal '{goal}'. Be concise and factual.

Text:
{text[:3000]}"""
    try:
        result = llm.complete(
            role="summarize",
            system="You are a research assistant. Summarize text concisely.",
            user=prompt,
            max_tokens=300,
            timeout=30,
        )
        if result.ok:
            return result.text.strip()
    except Exception:
        pass
    return text[:500]

def _extract_evidence(
    search_result: dict,
    query: str,
    tool: str,
    goal: str,
    trace_id: str,
    failed: list,
    state: dict,
    iteration: int,
    seen_urls: set,
) -> tuple[list[dict], dict]:
    """Extract evidence from search results, with deduplication and fallback."""
    evidence = []
    data = search_result.get("data", {})
    results = data.get("results", [])
    updates: dict = {}

    for idx, r in enumerate(results[:3]):
        url = r.get("url", "")
        if not url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        if any(f.get("url") == url for f in failed):
            continue

        title = r.get("title", "")
        text = r.get("text", "") or r.get("content", "")

        if not text or len(text) < 100:
            failed.append({
                "url": url,
                "reason": "no_content" if not text else "too_short",
                "iteration": iteration,
            })
            continue

        # Browser fallback for JS-heavy queries or very short content
        if len(text) < 300 or _is_js_wall(text):
            browser_text, browser_updates = _try_browser_fallback(url, trace_id, {**state, **updates})
            if browser_text and len(browser_text) >= 100:
                text = browser_text
                tool = "browser"
            updates.update(browser_updates)

        summary = _summarize_evidence(text, query, goal)
        try:
            citations.add(trace_id, url=url, title=title, snippet=summary[:300])
        except Exception:
            pass  # Citation tracking is best-effort
        evidence.append({
            "query": query,
            "url": url,
            "title": title,
            "summary": summary,
            "source": tool,
        })

    return evidence, updates

def node_search(state: DeepResearchState) -> DeepResearchState:
    """Execute pending sub-queries, extract evidence, manage budget."""
    queries = state.get("pending_queries", [])
    if not queries:
        return {
            "extracted_evidence": [],
            "pending_queries": [],
            "failed_sources": list(state.get("failed_sources", [])),
            "seen_urls": list(state.get("seen_urls", [])),
            "budget_api_calls": state.get("budget_api_calls", 0),
            "budget_browser_actions": state.get("budget_browser_actions", 0),
            "budget_events": list(state.get("budget_events", [])),
        }

    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    failed = list(state.get("failed_sources", []))
    # Initialize updates with current budget state so keys are always present
    updates: dict = {
        "budget_api_calls": state.get("budget_api_calls", 0),
        "budget_browser_actions": state.get("budget_browser_actions", 0),
        "budget_events": list(state.get("budget_events", [])),
    }
    all_evidence: list[dict] = []
    seen_urls: set = set(state.get("seen_urls", []))
    empty_this_iteration = True

    for query in queries:
        search_result, actual_tool, search_updates = _execute_search_with_fallback(query, {**state, **updates})
        updates.update(search_updates)
        if search_result.get("status") == "success":
            # [P0 #4] API budget is now decremented in _execute_search_with_fallback
            # at Tavily ATTEMPT time (paid API charges per call regardless of outcome).
            # Web (SearXNG) is free and never decrements. Nothing to do here on success.
            new_evidence, extract_updates = _extract_evidence(
                search_result, query, actual_tool, goal, tid, failed,
                {**state, **updates}, state.get("iteration", 0) + 1, seen_urls,
            )
            updates.update(extract_updates)
            all_evidence.extend(new_evidence)
            if new_evidence:
                empty_this_iteration = False
            else:
                updates.update(log_event(
                    {**state, **updates}, "search", "empty_results",
                    reason="query=" + query + ", tool=" + actual_tool
                ))
        else:
            updates.update(log_event(
                {**state, **updates}, "search", "error",
                reason="query=" + query + ", error=" + search_result.get("error", "unknown")
            ))

    updates["extracted_evidence"] = all_evidence
    updates["pending_queries"] = []

    # Track consecutive empty iterations for stuck-loop detection
    current_empty = state.get("consecutive_empty_iterations", 0)
    if empty_this_iteration:
        updates["consecutive_empty_iterations"] = current_empty + 1
    else:
        updates["consecutive_empty_iterations"] = 0

    updates["failed_sources"] = failed
    updates["iteration"] = state.get("iteration", 0) + 1
    updates["seen_urls"] = list(seen_urls)
    return updates
