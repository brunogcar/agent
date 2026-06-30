"""Web action: search_and_read — Search + parallel scrape with dedup.

Composite action: runs search, deduplicates URLs while preserving rank order,
then fans out to scrape each result in parallel via ThreadPoolExecutor.
The final aggregated result is piped through prune_tool_dict().

NOTE: This action directly imports _action_search and _action_scrape from
sibling modules. This is intentional cross-action coupling for performance
(direct calls avoid facade overhead). If search/scrape signatures change,
update this file accordingly.
"""
from __future__ import annotations

import concurrent.futures
from typing import Optional

from core.config import cfg
from core.contracts import fail, ok
from tools.web_ops._registry import register_action
from tools.web_ops.actions.scrape import _action_scrape
from tools.web_ops.actions.search import _action_search


@register_action(
    "web",
    "search_and_read",
    help_text="""search_and_read — Search then scrape top results in parallel.
Required: query
Optional: max_results (default 5, upper bound from cfg.web_max_search_results), max_chars
Returns: {query, results: [{url, title, text, word_count}], scraped_count, attempted, duplicates_removed}""",
    examples=[
        'web(action="search_and_read", query="ChromaDB persistent client")',
        'web(action="search_and_read", query="FastMCP", max_results=10)',
    ],
)
def _action_search_and_read(
    query: str = "",
    max_results: int = 5,
    max_chars: Optional[int] = None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Search then scrape top results in parallel.

    1. Run search(query, n) where n = min(max_results, cfg.web_max_search_results)
    2. Deduplicate URLs while preserving rank order
    3. Fan out to scrape each URL via ThreadPoolExecutor(max_workers=min(len(urls), 4))
    4. Reassemble results in original URL order
    5. Pipe final result through prune_tool_dict()

    Uses concurrent.futures.wait() with cfg.worker_timeout global timeout
    to prevent unbounded blocking on slow pages.
    """
    if not query:
        return fail("action='search_and_read' requires query=")

    if max_chars is None:
        max_chars = cfg.web_max_text_chars

    # Phase 1: Search
    n = min(max_results, cfg.web_max_search_results)
    search_result = _action_search(query=query, max_results=n, trace_id=trace_id)
    if search_result.get("status") != "success":
        return search_result

    raw_results = search_result.get("data", {}).get("results", [])
    if not raw_results:
        return fail("No search results", query=query)

    # Phase 2: Deduplicate URLs while preserving rank order
    seen_urls = set()
    urls = []
    for r in raw_results:
        u = r.get("url", "")
        if u and u not in seen_urls:
            seen_urls.add(u)
            urls.append(u)

    # Phase 3: Parallel scrape with global timeout
    def _fetch_one(u: str) -> tuple[str, dict]:
        return u, _action_scrape(url=u, max_chars=max_chars, trace_id=trace_id)

    results_map: dict[str, dict] = {}
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(urls), 4))
    try:
        futures = {ex.submit(_fetch_one, u): u for u in urls}
        # Global timeout via wait() — not as_completed()
        done, not_done = concurrent.futures.wait(
            futures, timeout=cfg.worker_timeout
        )

        for future in done:
            u = futures[future]
            try:
                _, result = future.result()
                results_map[u] = result
            except Exception as e:
                results_map[u] = fail(f"Scrape failed: {e}", url=u)

        for future in not_done:
            u = futures[future]
            results_map[u] = fail(f"Scrape timeout for {u}", url=u)
    finally:
        # shutdown(wait=False) prevents blocking on slow threads after
        # wait() has already returned. The threads will finish in background
        # and be cleaned up by the executor.
        ex.shutdown(wait=False)

    # Phase 4: Reassemble in original URL order
    scraped = []
    for u in urls:
        result = results_map.get(u, {})
        if result.get("status") == "success" and result.get("data", {}).get("text"):
            scraped.append({
                "url": u,
                "title": result.get("data", {}).get("title", ""),
                "text": result["data"]["text"],
                "word_count": result.get("data", {}).get("word_count", 0),
            })

    result = ok({
        "query": query,
        "results": scraped,
        "scraped_count": len(scraped),
        "attempted": len(urls),
        "duplicates_removed": len(raw_results) - len(urls),
    })

    # Phase 5: Prune final aggregated result
    from core.memory_backend.pruner import prune_tool_dict
    return prune_tool_dict("web", result, trace_id)
