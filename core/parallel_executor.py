"""core/parallel_dispatcher.py — Parallel tool execution engine.

No dependency on registry.py. Pure execution logic.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Callable

from core.contracts import ok, fail

# Tools that are safe to run in parallel (conservative default)
PARALLEL_SAFE = frozenset({
    "web", "git", "file", "python", "python_exec", "notify",
    "memory", "memory_tool", "cli",
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

    results = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for name, fn, args in calls:
            future = executor.submit(_safe_run, name, fn, args)
            futures[future] = name

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result(timeout=30)
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

    return ok({
        "results": results,
        "errors": errors,
        "completed": len(results),
        "failed": len(errors),
    }, trace_id=trace_id)


def _safe_run(name: str, fn: Callable, args: dict) -> Any:
    """Run a single tool call safely."""
    return fn(**args)
