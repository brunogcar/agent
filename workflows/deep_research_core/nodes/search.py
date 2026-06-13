"""Search node: execute sub-queries, extract evidence, track budget.

Runs sequentially (never in a ThreadPoolExecutor) because browser
actions are NOT_PARALLEL_SAFE.  Tavily and web are parallel-safe, but
for v1 we keep the loop simple and sequential to avoid state-merge
complexity inside a single node.
"""
from __future__ import annotations

import logging
from typing import Any

from core.config import cfg
from core.llm import llm
from core.runtime.activity_tracker import tracker
from tools.tavily import tavily
from tools.web import web
from workflows.deep_research_core.budget import (
    decrement_api_calls,
    is_api_budget_exhausted,
    log_event,
)
from workflows.deep_research_core.constants import (
    COMPLEX_QUERY_HINTS,
    JS_HEAVY_HINTS,
)
from workflows.deep_research_core.state import DeepResearchState
from workflows.base import node_step

logger = logging.getLogger(__name__)


def node_search(state: DeepResearchState) -> DeepResearchState:
    """Execute all pending sub-queries and extract structured evidence.

    For each sub-query:
    1. Select the best tool (Tavily vs. web) based on budget and heuristics.
    2. Run the search.
    3. Scrape / extract text from the top 3 result URLs.
    4. Summarise each page with the executor LLM.
    5. Update budget and telemetry.

    Browser fallback is **deferred to v2**; for v1 we rely on
    ``web(action="read")`` and Tavily's built-in content extraction.

    Args:
        state: Workflow state with ``pending_queries`` and budget fields.

    Returns:
        Partial state update with ``extracted_evidence``, cleared
        ``pending_queries``, incremented ``iteration``, and updated budget.
    """
    queries = state.get("pending_queries", [])
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    iteration = state.get("iteration", 0)
    failed = list(state.get("failed_sources", []))

    if not queries:
        node_step(state, "search", "no pending queries to process")
        return {
            "extracted_evidence": [],
            "pending_queries": [],
            "iteration": iteration + 1,
            "failed_sources": failed,
        }

    node_step(state, "search", f"processing {len(queries)} sub-queries")

    evidence: list[dict[str, Any]] = []
    updates: dict[str, Any] = {}

    for query in queries:
        tool = _select_tool(query, {**state, **updates})
        node_step(state, "search", f"tool={tool} query={query[:40]}")

        # -- Execute search ------------------------------------------
        search_result = _execute_search(query, tool)

        # -- Budget bookkeeping --------------------------------------
        if tool == "tavily" and search_result.get("status") == "success":
            updates.update(decrement_api_calls({**state, **updates}))
            updates.update(
                log_event(
                    {**state, **updates},
                    tool="tavily",
                    action="search",
                    reason=query[:60],
                )
            )
        else:
            updates.update(
                log_event(
                    {**state, **updates},
                    tool=tool,
                    action="search",
                    reason=query[:60],
                )
            )

        # -- Extract evidence from results ----------------------------
        if search_result.get("status") == "success":
            new_evidence = _extract_evidence(
                search_result, query, tool, goal, tid, failed, {**state, **updates}
            )
            evidence.extend(new_evidence)
        else:
            # Log the search failure but keep looping
            logger.warning("Search failed for query %r: %s", query, search_result.get("error"))
            updates.update(
                log_event(
                    {**state, **updates},
                    tool=tool,
                    action="search_failed",
                    reason=str(search_result.get("error", "unknown"))[:100],
                )
            )

    updates.update(
        {
            "extracted_evidence": evidence,
            "pending_queries": [],
            "failed_sources": failed,
            "iteration": iteration + 1,
        }
    )

    node_step(state, "search", f"extracted {len(evidence)} evidence items")
    return updates


def _select_tool(query: str, state: dict[str, Any]) -> str:
    """Choose the best search tool for a sub-query.

    Heuristic (v1, hard-coded):
    1. Tavily if API key is configured, budget remains, and the query looks complex.
    2. Web (SearXNG) as the free default.

    Browser is **not** used for search in v1; it will be introduced in v2
    for known JS-heavy URLs.

    Args:
        query: Sub-query string.
        state: Current state (used for budget checks).

    Returns:
        Tool name: ``"tavily"`` or ``"web"``.
    """
    if (
        cfg.tavily_api_key
        and not is_api_budget_exhausted(state)
        and _is_complex_query(query)
    ):
        return "tavily"
    return "web"


def _is_complex_query(query: str) -> bool:
    """Simple heuristic: multi-part questions are complex."""
    q = query.lower()
    return any(hint in q for hint in COMPLEX_QUERY_HINTS)


def _is_js_heavy(query: str) -> bool:
    """Simple heuristic: keywords suggesting JS-heavy sites."""
    q = query.lower()
    return any(hint in q for hint in JS_HEAVY_HINTS)


def _execute_search(query: str, tool: str) -> dict[str, Any]:
    """Dispatch a search call to the selected tool.

    Args:
        query: Search query string.
        tool: ``"tavily"`` or ``"web"``.

    Returns:
        Standard tool result dict (``status``, ``data``, ``error``).
    """
    if tool == "tavily":
        return tavily(action="search", query=query, max_results=5)
    return web(action="search", query=query, max_results=5)


def _extract_evidence(
    search_result: dict[str, Any],
    query: str,
    tool: str,
    goal: str,
    trace_id: str,
    failed: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Turn raw search results into structured, summarised evidence.

    For each of the top 3 result URLs:
    1. Extract text (Tavily ``content`` field or ``web(action="read")``).
    2. Skip URLs that are already in ``failed_sources``.
    3. Summarise with the executor LLM.
    4. Record failures (404, no content, etc.).

    Args:
        search_result: Raw tool output dict.
        query: The sub-query that produced these results.
        tool: Tool name used for the search.
        goal: Original research goal (for context in summarisation).
        trace_id: Active trace ID.
        failed: Mutable list of failed sources (appended in place).
        state: Current state (for budget checks if browser fallback were used).

    Returns:
        List of evidence dicts, each with ``query``, ``url``, ``title``,
        ``summary``, and ``tool_used``.
    """
    evidence: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    data = search_result.get("data") or {}
    results = list(data.get("results", []))

    for idx, r in enumerate(results[:3], start=1):
        url = str(r.get("url", "")).strip()
        if not url:
            continue

        # Skip previously-failed URLs
        if any(f.get("url") == url for f in failed):
            continue

        title = str(r.get("title", "")).strip()
        text = ""

        # -- Text extraction strategy --------------------------------
        if tool == "tavily" and r.get("content"):
            text = str(r.get("content", "")).strip()
        elif tool == "web":
            scrape = web(action="read", url=url)
            if scrape.get("status") == "success":
                scrape_data = scrape.get("data") or {}
                text = str(scrape_data.get("text", "")).strip()
                title = str(scrape_data.get("title", title)).strip()

        if not text or len(text) < 100:
            failed.append(
                {
                    "url": url,
                    "reason": "no_content" if not text else "too_short",
                    "iteration": state.get("iteration", 0),
                }
            )
            continue

        # -- Summarise with executor LLM -----------------------------
        try:
            with tracker.inference_slot(timeout=30.0):
                resp = llm.complete(
                    role="executor",
                    system=(
                        "You are a research assistant.  Summarise the given text "
                        "in 2-3 bullet points relevant to the query and goal."
                    ),
                    user=(
                        f"Query: {query}\n"
                        f"Goal: {goal}\n\n"
                        f"Text:\n{text[:4000]}"
                    ),
                    max_tokens=cfg.worker_max_tokens,
                    timeout=cfg.worker_timeout,
                    trace_id=trace_id,
                )
                summary = resp.text if resp.ok else text[:500]
        except Exception as exc:
            logger.warning("LLM summarisation failed for %s: %s", url, exc)
            summary = text[:500]

        evidence.append(
            {
                "query": query,
                "url": url,
                "title": title,
                "summary": summary,
                "tool_used": tool,
            }
        )

    return evidence
