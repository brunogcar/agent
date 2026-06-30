from __future__ import annotations
import asyncio
import concurrent.futures

from core.config import cfg


def _run_async(coro):
    """
    Run an async coroutine from a sync context.
    Handles the case where a thread may or may not have a running event loop.
    Deliberately uses per-call ThreadPoolExecutor instead of a persistent
    background loop — Tavily calls are short network requests, not long
    Playwright sessions, so loop-reuse overhead isn't worth the complexity.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Running loop exists — run in fresh thread to avoid nested loop error
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(asyncio.run, coro)
        return future.result(timeout=cfg.tavily_timeout + 10)
