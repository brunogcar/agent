"""workflows/deep_research_core/nodes/search.py
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
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.budget import (
    decrement_api_calls,
    decrement_browser_actions,
    log_event,
)
from workflows.deep_research_core.constants import JS_HEAVY_HINTS

logger = logging.getLogger(__name__)


def _is_complex_query(query: str) -> bool:
    """Heuristic: queries with 8+ words or comparison keywords are complex."""
    q = query.lower()
    return len(query.split()) >= 8 or any(
        w in q for w in ("compare", "vs", "versus", "difference", "pros and cons")
    )


def _is_js_heavy(query: str) -> bool:
    """Heuristic: queries likely to hit JS-rendered sites.

    NOTE: This is used in _extract_evidence for content-based fallback,
    NOT in _select_tool. Browser is expensive (NOT_PARALLEL_SAFE) and
    should only be used when web returns short/empty content.
    """
    q = query.lower()
    return any(h in q for h in JS_HEAVY_HINTS)


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


def _execute_search_with_fallback(query: str, state: DeepResearchState) -> dict:
    """Execute search with tavily -> web fallback on failure or empty results."""
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
    """Attempt to extract text via browser for JS-heavy or short-content pages."""
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
    state: DeepResearchState,
    iteration: int,
    seen_urls: set,
) -> list[dict]:
    """Extract evidence from search results, with deduplication and fallback."""
    evidence = []
    data = search_result.get("data", {})
    results = data.get("results", [])

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
        if len(text) < 300 or _is_js_heavy(query):
            browser_text = _try_browser_fallback(url, trace_id)
            if browser_text and len(browser_text) >= 100:
                text = browser_text
                tool = "browser"

        summary = _summarize_evidence(text, query, goal)
        citations.add(trace_id, url=url, title=title, snippet=summary[:300])
        evidence.append({
            "query": query,
            "url": url,
            "title": title,
            "summary": summary,
            "source": tool,
        })

    return evidence


def node_search(state: DeepResearchState) -> DeepResearchState:
    """Execute pending sub-queries, extract evidence, manage budget."""
    queries = state.get("pending_queries", [])
    if not queries:
        return {
            "extracted_evidence": [],
            "pending_queries": [],
            "failed_sources": list(state.get("failed_sources", [])),
        }

    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    failed = list(state.get("failed_sources", []))
    updates: dict = {}
    all_evidence: list[dict] = []
    seen_urls: set = set()
    empty_this_iteration = True

    for query in queries:
        search_result = _execute_search_with_fallback(query, {**state, **updates})
        if search_result.get("status") == "success":
            updates.update(decrement_api_calls({**state, **updates}))
            new_evidence = _extract_evidence(
                search_result, query, "tavily", goal, tid, failed,
                {**state, **updates}, state.get("iteration", 0) + 1, seen_urls,
            )
            all_evidence.extend(new_evidence)
            if new_evidence:
                empty_this_iteration = False
            else:
                log_event({**state, **updates}, "empty_results", {"query": query, "tool": "tavily"})
        else:
            log_event({**state, **updates}, "search_error", {"query": query, "error": search_result.get("error", "unknown")})

    updates.update(decrement_browser_actions({**state, **updates}))
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
    return updates
