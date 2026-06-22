"""core/parallel_dispatcher.py — Parallel tool execution engine.

No dependency on registry.py. Pure execution logic.
"""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Any, Callable

from core.contracts import ok, fail
from core.config import cfg

# Tools that are safe to run in parallel (conservative default)
_parallel_depth = threading.local()

PARALLEL_SAFE = frozenset({
    "web", "file", "python", "python_exec", "notify",
})

def dispatch_parallel(
    calls: list[tuple[str, Callable, dict]],
    max_workers: int = 4,
    trace_id: str = "",
) -> dict:
    """Execute multiple tool calls in parallel."""
    if not calls:
        return fail("No calls provided for parallel execution", trace_id=trace_id)

    if max_workers < 1:
        max_workers = 1
    if max_workers > 8:
        max_workers = 8

    # Prevent nested parallel calls
    if getattr(_parallel_depth, "value", 0) > 0:
        return fail("Nested parallel calls are not allowed", trace_id=trace_id)

    # [P3 FIX] Use configured worker timeout instead of hardcoded 30s.
    # Respects cfg.worker_timeout (default 60s per config.py) so users can adjust via .env.
    timeout = cfg.worker_timeout  # Guaranteed to exist in Config

    results = []
    errors = []

    _parallel_depth.value = getattr(_parallel_depth, "value", 0) + 1
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for name, fn, args in calls:
                future = executor.submit(_safe_run, name, fn, args)
                futures[future] = name

            # Enforce real global timeout using wait(), not as_completed()
            done, not_done = concurrent.futures.wait(futures, timeout=timeout)

            for future in done:
                name = futures[future]
                try:
                    result = future.result()
                    results.append({
                        "tool": name,
                        "status": result.get("status", "success") if isinstance(result, dict) else "success",
                        "result": result,
                    })
                except Exception as e:
                    errors.append({
                        "tool": name,
                        "error": f"{type(e).__name__}: {e}",
                    })

            for future in not_done:
                name = futures[future]
                errors.append({
                    "tool": name,
                    "error": f"Timed out after {timeout} seconds",
                })
    finally:
        _parallel_depth.value -= 1

    return ok({
        "results": results,
        "errors": errors,
        "completed": len(results),
        "failed": len(errors),
    }, trace_id=trace_id)

def _safe_run(name: str, fn: Callable, args: dict) -> Any:
    """Run a single tool call safely."""
    return fn(**args)
