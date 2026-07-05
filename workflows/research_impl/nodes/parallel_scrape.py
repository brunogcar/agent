"""Node: parallel_scrape — Scrape and summarize URLs in parallel.

[Fix #4] Replaced as_completed(timeout=) with concurrent.futures.wait(timeout=).
  as_completed timeout is per-future, not global — subsequent futures can hang.
  wait() with timeout is truly global — all pending futures are checked.

[Fix #5] Cancel pending futures on timeout to prevent zombie threads.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

from workflows.base import WorkflowState, node_step
from workflows.research_impl.helpers import (
    _is_nested_parallel,
    _set_parallel_active,
    _scrape_and_summarize,
    _browser_fallback_scrape,
)


def node_parallel_scrape(state: WorkflowState) -> dict:
    """Coordinator: scrape and summarize URLs in parallel, with sequential browser fallback."""
    from core.config import cfg
    from core.citations import citations

    raw_results = state.get("search_results", "")
    if not raw_results:
        return {"search_results": ""}

    try:
        urls_data = json.loads(raw_results)
    except Exception:
        return {"search_results": ""}

    goal = state.get("goal", "")
    tid = state.get("trace_id", "")

    node_step(state, "parallel_scrape", f"spawning {len(urls_data)} workers")

    # Guard against nested parallel execution (prevents ThreadPoolExecutor deadlock)
    if _is_nested_parallel():
        node_step(state, "parallel_scrape", "nested parallel scrape rejected")
        return {"search_results": ""}
    _set_parallel_active(True)
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

            # [Fix #4] Use wait() with global timeout instead of as_completed(timeout=).
            # as_completed timeout is for the FIRST future to complete, not a global cap.
            # wait() with timeout returns (done, not_done) — truly global timeout.
            done, not_done = wait(
                future_to_data.keys(),
                timeout=cfg.worker_timeout + 30,
                return_when=ALL_COMPLETED,
            )

            # [Fix #5] Cancel pending futures on timeout to prevent zombie threads.
            for future in not_done:
                future.cancel()

            for future in done:
                item = future_to_data[future]
                try:
                    res = future.result(timeout=1)  # Already done — just get result
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

            # Log cancelled futures
            if not_done:
                node_step(state, "parallel_scrape", f"{len(not_done)} futures cancelled (timeout)")

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
            return {"search_results": ""}

        dossier = "\n\n".join(dossier_parts)

        # Hard cap the dossier to prevent context explosion at synthesis time.
        max_dossier_chars = cfg.web_max_text_chars * 2
        if len(dossier) > max_dossier_chars:
            trunc_point = dossier.rfind("\n\n", 0, max_dossier_chars)
            if trunc_point == -1:
                trunc_point = dossier.rfind("\n", 0, max_dossier_chars)
            if trunc_point == -1:
                trunc_point = max_dossier_chars
            dossier = dossier[:trunc_point] + "\n\n[... dossier truncated: " + str(len(dossier) - trunc_point) + " chars omitted ...]"

        node_step(state, "parallel_scrape", f"built dossier with {citation_idx-1} sources ({len(dossier)} chars)")
        return {"search_results": dossier}
    finally:
        _set_parallel_active(False)
