"""workflows/deep_research_core/nodes/search.py
Iterative search node with multi-tier fallback.
"""
from __future__ import annotations
from typing import List, Dict, Any, Set
from workflows.deep_research_core.state import DeepResearchState
from workflows.deep_research_core.budget import decrement_api_calls, log_event
from workflows.deep_research_core.constants import (
    JS_HEAVY_HINTS,
    JS_WALL_INDICATORS,
    SEARCH_SYSTEM_PROMPT,
    SEARCH_USER_TEMPLATE,
)
from core.llm import llm
from core.citations import citations
from tools.tavily import tavily
from tools.web import web
from tools.browser import browser


def _is_js_wall(text: str) -> bool:
    """Detect if a page requires JavaScript to render content."""
    if not text:
        return True
    lowered = text.lower()
    return any(indicator in lowered for indicator in JS_WALL_INDICATORS)


def node_search(state: DeepResearchState) -> DeepResearchState:
    """Execute pending sub-queries with multi-tier fallback.

    Fallback chain per query:
      tavily (if budget) -> web (if tavily fails/empty) -> browser (if JS wall/short)

    Browser is NOT_PARALLEL_SAFE; the sequential for-loop guarantees safety.
    """
    queries = state.get("pending_queries", [])
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    iteration = state.get("iteration", 0)

    # Always increment iteration — even if no queries remain.
    # This prevents the route from staying at iteration 0 forever.
    if not queries:
        return {
            "extracted_evidence": [],
            "pending_queries": [],
            "iteration": iteration + 1,
            "consecutive_empty_iterations": state.get("consecutive_empty_iterations", 0) + 1,
        }

    failed = list(state.get("failed_sources", []))
    updates = {
        "extracted_evidence": list(state.get("extracted_evidence", [])),
        "budget_events": list(state.get("budget_events", [])),
    }
    seen_urls: Set[str] = set()
    empty_this_iteration = True
    browser_used = False

    for query in queries:
        tool = _select_tool(query, {**state, **updates})
        search_result, actual_tool = _execute_search_with_fallback(
            query, tool, tid, {**state, **updates}
        )

        # Only decrement API budget for tavily calls that succeeded
        if actual_tool == "tavily" and search_result.get("status") == "success":
            updates.update(decrement_api_calls({**state, **updates}))

        new_evidence = _extract_evidence(
            search_result, query, actual_tool, goal, tid, failed,
            seen_urls, iteration + 1
        )

        if new_evidence:
            empty_this_iteration = False
            updates["extracted_evidence"].extend(new_evidence)
            if any(ev.get("tool") == "browser" for ev in new_evidence):
                browser_used = True
        elif search_result.get("status") == "success":
            # Search succeeded but nothing was extractable — log for telemetry
            updates["budget_events"] = list(updates.get("budget_events", [])) + [
                {"action": "empty_results", "reason": f"No extractable evidence for: {query[:60]}"}
            ]

    # Decrement browser budget if any fallback was used
    if browser_used:
        current_browser = state.get("budget_browser_calls", 0)
        if current_browser > 0:
            updates["budget_browser_calls"] = current_browser - 1

    # Track consecutive empty iterations for stuck-loop detection
    consecutive = state.get("consecutive_empty_iterations", 0)
    if empty_this_iteration:
        consecutive += 1
    else:
        consecutive = 0

    updates["pending_queries"] = []
    updates["failed_sources"] = failed
    updates["iteration"] = iteration + 1
    updates["consecutive_empty_iterations"] = consecutive
    return updates


def _select_tool(query: str, state: DeepResearchState) -> str:
    """Choose primary search tool based on query complexity and budget."""
    if not state.get("budget_api_calls", 0):
        return "web"
    if _is_complex_query(query) or _is_js_heavy(query):
        return "tavily"
    return "tavily"


def _is_complex_query(query: str) -> bool:
    return len(query) > 80 or any(hint in query.lower() for hint in JS_HEAVY_HINTS)


def _is_js_heavy(query: str) -> bool:
    return any(hint in query.lower() for hint in JS_HEAVY_HINTS)


def _execute_search_with_fallback(
    query: str, preferred_tool: str, trace_id: str, state: DeepResearchState
) -> tuple[dict, str]:
    """Execute search with fallback: tavily -> web.

    Returns (result, actual_tool_used).
    """
    result = _execute_search(query, preferred_tool, trace_id)
    if result.get("status") == "success" and result.get("data", {}).get("results"):
        return result, preferred_tool

    # Fallback to web if tavily failed or returned empty
    if preferred_tool != "web":
        log_event(
            state, "fallback",
            f"Tavily empty/failed for '{query[:60]}', falling back to web"
        )
        result = _execute_search(query, "web", trace_id)
        if result.get("status") == "success":
            return result, "web"

    return result, preferred_tool


def _execute_search(query: str, tool: str, trace_id: str) -> dict:
    if tool == "tavily":
        return tavily(
            action="search",
            query=query,
            max_results=5,
            include_answer=False,
            trace_id=trace_id,
        )
    return web(
        action="search",
        query=query,
        max_results=5,
        trace_id=trace_id,
    )


def _extract_evidence(
    search_result: dict,
    query: str,
    tool: str,
    goal: str,
    tid: str,
    failed: List[dict],
    seen_urls: Set[str],
    iteration: int,
) -> List[dict]:
    """Extract evidence from search results with deduplication and browser fallback.

    Args:
        search_result: Raw tool output dict.
        query: The sub-query that produced this result.
        tool: Tool name that produced the result (may differ from fallback).
        goal: Original research goal.
        tid: Trace ID for citations.
        failed: Mutable list of failed source records (updated in-place).
        seen_urls: Mutable set of already-processed URLs (updated in-place).
        iteration: Current iteration number (1-based) for telemetry.

    Returns:
        List of evidence dicts, each with keys: query, url, title, summary, tool.
    """
    evidence = []
    if not search_result or search_result.get("status") != "success":
        return evidence

    data = search_result.get("data", {})
    results = data.get("results", []) if isinstance(data, dict) else []

    if not results:
        return evidence

    for idx, r in enumerate(results[:3]):
        url = r.get("url", "")
        title = r.get("title", "")

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        if any(f.get("url") == url for f in failed):
            continue

        # Get text based on primary tool
        if tool == "tavily":
            text = r.get("content", "") or r.get("text", "")
        else:
            read_result = web(action="read", url=url, trace_id=tid)
            if read_result.get("status") != "success":
                failed.append({
                    "url": url,
                    "reason": "read_failed",
                    "iteration": iteration,
                })
                continue
            text = read_result.get("data", {}).get("text", "")

        # Browser fallback for JS walls or very short content
        if (not text or len(text) < 100 or _is_js_wall(text)) and tool != "browser":
            browser_text = _try_browser_fallback(url, tid)
            if browser_text and len(browser_text) >= 100:
                text = browser_text
                tool = "browser"

        if not text or len(text) < 100:
            failed.append({
                "url": url,
                "reason": "no_content" if not text else "too_short",
                "iteration": iteration,
            })
            continue

        summary = _summarize_evidence(text, query, goal, tid)

        # Register citation
        citations.add(tid, url=url, title=title, snippet=summary[:300])

        evidence.append({
            "query": query,
            "url": url,
            "title": title,
            "summary": summary,
            "tool": tool,
        })

    return evidence


def _try_browser_fallback(url: str, trace_id: str) -> str:
    """Attempt browser extraction for JS-heavy pages.

    Browser is protected by a global threading.Lock in tools/browser.py.
    This function is only called from the sequential node_search loop,
    so deadlock is impossible.
    """
    try:
        nav = browser(
            action="navigate", url=url, trace_id=trace_id,
            timeout=30, headless=True,
        )
        if nav.get("status") != "success":
            return ""
        txt = browser(
            action="text_content", selector="body", trace_id=trace_id,
            timeout=30,
        )
        if txt.get("status") == "success":
            return txt.get("data", {}).get("text", "")
    except Exception:
        pass
    return ""


def _summarize_evidence(text: str, query: str, goal: str, tid: str) -> str:
    """Summarise extracted text into 2–3 bullet points."""
    prompt = SEARCH_USER_TEMPLATE.format(query=query, goal=goal, text=text[:3000])
    result = llm.complete(
        role="executor",
        system=SEARCH_SYSTEM_PROMPT,
        user=prompt,
        trace_id=tid,
        max_tokens=300,
    )
    if result.ok:
        return result.text.strip()
    return text[:500]
