"""Node: search — Search the web for relevant URLs.

[Fix #12] Now deduplicates URLs from search results.
"""
from __future__ import annotations

import json

from workflows.base import WorkflowState, node_step


def node_search(state: WorkflowState) -> dict:
    """Search the web for relevant URLs."""
    from tools.web import web
    from core.config import cfg

    goal = state.get("goal", "")
    node_step(state, "search", "searching web for URLs", query=goal[:60])

    result = web(action="search", query=goal, max_results=cfg.web_max_search_results)

    if result.get("status") != "success" or not result.get("results"):
        err = result.get("error", "no results returned")
        node_step(state, "search", f"search failed: {err}")
        return {"search_results": ""}

    # [Fix #12] Deduplicate URLs — SearXNG may return the same URL from
    # different search engines. Track seen URLs to avoid duplicate scraping.
    seen_urls = set()
    valid_urls = []
    for r in result["results"]:
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        valid_urls.append({"url": url, "title": r.get("title", ""), "snippet": r.get("snippet", "")})

    if not valid_urls:
        node_step(state, "search", "no valid URLs found")
        return {"search_results": ""}

    # Store as JSON string for the parallel scraper node
    return {"search_results": json.dumps(valid_urls)}
