"""Helpers for research workflow.

Contains worker functions and thread-safety guards used by the
parallel_scrape node.
"""
from __future__ import annotations

import threading
import uuid

# [Fix #9] Thread-local guard to prevent nested parallel scrape (deadlock prevention).
# Uses threading.local() which is per-thread, not per-process. Worker threads
# in ThreadPoolExecutor each get their own copy — so a worker that calls
# parallel_scrape recursively won't see the parent's "active" flag.
_parallel_scrape_active = threading.local()


def _is_nested_parallel() -> bool:
    """Check if node_parallel_scrape is already active in this thread.

    Prevents deadlock when a worker thread calls node_parallel_scrape
    recursively (e.g., via autocode tool invocation).

    [Fix #9] threading.local() is per-thread — worker threads in the
    ThreadPoolExecutor get their own copy. The guard correctly blocks
    recursion within the SAME thread (the coordinator), not across
    different worker threads.
    """
    return getattr(_parallel_scrape_active, "active", False)


def _set_parallel_active(value: bool) -> None:
    """Set the parallel scrape active flag for the current thread."""
    _parallel_scrape_active.active = value


def _scrape_and_summarize(url: str, title: str, goal: str, trace_id: str) -> dict:
    """Worker function: scrape URL and summarize with Executor.

    Called in parallel by node_parallel_scrape via ThreadPoolExecutor.
    Returns a dict with status: "success", "needs_browser", or "failed".
    """
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
    except Exception as e:
        return {"url": url, "title": title, "status": "failed", "error": str(e)}


def _browser_fallback_scrape(url: str, title: str, goal: str, trace_id: str) -> dict:
    """Sequential browser fallback for JS-heavy pages.

    Called outside the thread pool (browser is NOT_PARALLEL_SAFE).
    Uses a stable trace ID for navigate + text_content to share browser context.
    """
    from tools.browser import browser
    from core.llm import llm
    from core.runtime.activity_tracker import tracker
    from core.config import cfg

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
        except Exception as e:
            return {"url": url, "title": title, "status": "failed", "error": str(e)}

    except Exception as e:
        return {"url": url, "title": title, "status": "failed", "error": f"browser fallback: {e}"}
