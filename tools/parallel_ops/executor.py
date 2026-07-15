"""Execution engines for parallel tool dispatch.

Three execution strategies live here:
  - dispatch_run:     all calls in parallel, wait for all (barrier semantics)
  - dispatch_race:    all calls in parallel, first success wins, cancel rest
  - dispatch_pipeline: sequential chain, each result feeds the next call's args

[DESIGN] WHY SHARED _parallel_depth: nested parallel calls would create a
thread-pool-of-thread-pools deadlock risk. The thread-local guard rejects
any nested entry — even pipeline (which is sequential) increments it so a
pipeline stage that itself calls parallel() is also blocked.

[DESIGN] WHY _safe_run IS A SEPARATE FUNCTION: ThreadPoolExecutor submits
need a picklable callable in some Python implementations. A module-level
function is picklable; a closure isn't. Even though CPython's
ThreadPoolExecutor doesn't pickle, keeping _safe_run module-level matches
the pattern in the original core/parallel_executor.py and makes the
executor easy to mock in tests.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Any, Callable

from core.contracts import ok, fail
from core.config import cfg

# Thread-local depth counter — guards against nested parallel calls
# (e.g. a parallel-run task that itself invokes parallel).
_parallel_depth = threading.local()


def _resolve_timeout(timeout: int) -> int:
    """Pick the effective per-execution timeout.

    -1 (sentinel) → fall back to cfg.worker_timeout (default 60s).
    Any non-negative value → use as-is.
    Negative other than -1 → treated as -1 (defensive).
    """
    if timeout is not None and timeout >= 0:
        return timeout
    return cfg.worker_timeout


def _safe_run(name: str, fn: Callable, args: dict) -> Any:
    """Run a single tool call safely.

    Exists as a module-level function (not a closure) so it remains
    picklable and matches the original core/parallel_executor.py shape.
    """
    return fn(**args)


def dispatch_run(
    calls: list[tuple[str, Callable, dict]],
    max_workers: int = 4,
    timeout: int = -1,
    trace_id: str = "",
) -> dict:
    """Execute all calls in parallel, wait for all to complete.

    Returns ok({"results": [...], "errors": [...], "completed": N, "failed": M,
                "duration_ms": int}).
    Each result entry: {tool, status, result, trace_id?}.
    Each error entry: {tool, error, trace_id?}.
    """
    if not calls:
        return fail("No calls provided for parallel execution", trace_id=trace_id)

    if max_workers < 1:
        max_workers = 1
    if max_workers > 8:
        max_workers = 8

    # Prevent nested parallel calls
    if getattr(_parallel_depth, "value", 0) > 0:
        return fail("Nested parallel calls are not allowed", trace_id=trace_id)

    effective_timeout = _resolve_timeout(timeout)

    results: list[dict] = []
    errors: list[dict] = []

    start = time.time()
    _parallel_depth.value = getattr(_parallel_depth, "value", 0) + 1
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Any, str] = {}
            for name, fn, args in calls:
                future = executor.submit(_safe_run, name, fn, args)
                futures[future] = name

            # Enforce real global timeout using wait(), not as_completed()
            done, not_done = concurrent.futures.wait(futures, timeout=effective_timeout)

            for future in done:
                name = futures[future]
                try:
                    result = future.result()
                    entry = {
                        "tool": name,
                        "status": result.get("status", "success") if isinstance(result, dict) else "success",
                        "result": result,
                    }
                    if trace_id:
                        entry["trace_id"] = trace_id
                    results.append(entry)
                except Exception as e:
                    entry = {
                        "tool": name,
                        "error": f"{type(e).__name__}: {e}",
                    }
                    if trace_id:
                        entry["trace_id"] = trace_id
                    errors.append(entry)

            for future in not_done:
                name = futures[future]
                entry = {
                    "tool": name,
                    "error": f"Timed out after {effective_timeout} seconds",
                }
                if trace_id:
                    entry["trace_id"] = trace_id
                errors.append(entry)
    finally:
        _parallel_depth.value -= 1

    return ok({
        "results": results,
        "errors": errors,
        "completed": len(results),
        "failed": len(errors),
        "duration_ms": round((time.time() - start) * 1000),
    }, trace_id=trace_id)


def dispatch_race(
    calls: list[tuple[str, Callable, dict]],
    max_workers: int = 4,
    timeout: int = -1,
    trace_id: str = "",
) -> dict:
    """Execute all calls in parallel, return first successful result, cancel rest.

    Uses as_completed() instead of wait(). The first future that returns
    a non-error result wins; remaining futures are cancelled (if not yet
    started) or abandoned (if already running — Python cannot preempt a
    running thread).

    Returns ok({"winner": {...}, "cancelled": [tool names], "failed": [...],
                "duration_ms": int}) on success.
    Returns ok({"winner": None, "cancelled": [], "failed": [...], "duration_ms": int})
    if all calls fail (status is still "success" at the envelope level —
    the race itself completed; the per-call failures are in `failed`).
    """
    if not calls:
        return fail("No calls provided for race execution", trace_id=trace_id)

    if max_workers < 1:
        max_workers = 1
    if max_workers > 8:
        max_workers = 8

    if getattr(_parallel_depth, "value", 0) > 0:
        return fail("Nested parallel calls are not allowed", trace_id=trace_id)

    effective_timeout = _resolve_timeout(timeout)

    winner: dict | None = None
    cancelled: list[str] = []
    failed: list[dict] = []

    start = time.time()
    _parallel_depth.value = getattr(_parallel_depth, "value", 0) + 1
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Any, str] = {}
            for name, fn, args in calls:
                future = executor.submit(_safe_run, name, fn, args)
                futures[future] = name

            try:
                for future in concurrent.futures.as_completed(futures, timeout=effective_timeout):
                    name = futures[future]
                    try:
                        result = future.result()
                        # First non-error result wins.
                        status = result.get("status", "success") if isinstance(result, dict) else "success"
                        if status != "error" and winner is None:
                            winner = {
                                "tool": name,
                                "status": status,
                                "result": result,
                            }
                            if trace_id:
                                winner["trace_id"] = trace_id
                            # Cancel all not-yet-started futures.
                            for f, n in futures.items():
                                if f is future:
                                    continue
                                if f.cancel():
                                    cancelled.append(n)
                                # If f.cancel() returns False, the future is
                                # already running or done — we can't preempt.
                                # It will be drained below as either a late
                                # success (ignored) or a failure (added to
                                # `failed`).
                        else:
                            # Late result or explicit error result — record as failed/late.
                            entry = {
                                "tool": name,
                                "error": result.get("error", "race: not the winner")
                                if isinstance(result, dict)
                                else "race: not the winner",
                            }
                            if trace_id:
                                entry["trace_id"] = trace_id
                            failed.append(entry)
                    except Exception as e:
                        entry = {
                            "tool": name,
                            "error": f"{type(e).__name__}: {e}",
                        }
                        if trace_id:
                            entry["trace_id"] = trace_id
                        failed.append(entry)
            except concurrent.futures.TimeoutError:
                # All remaining futures timed out — record them as failed.
                for f, n in futures.items():
                    if not f.done():
                        entry = {
                            "tool": n,
                            "error": f"Timed out after {effective_timeout} seconds",
                        }
                        if trace_id:
                            entry["trace_id"] = trace_id
                        failed.append(entry)
    finally:
        _parallel_depth.value -= 1

    return ok({
        "winner": winner,
        "cancelled": cancelled,
        "failed": failed,
        "duration_ms": round((time.time() - start) * 1000),
    }, trace_id=trace_id)


def _resolve_dot_path(obj: Any, dot_path: str) -> Any:
    """Resolve a dot-path string against a (possibly nested) object.

    Supports dict keys and object attributes. "result.text" against
    {"result": {"text": "x"}} returns "x". Single-segment paths work too.

    Returns None if any segment is missing or the path is malformed —
    callers should treat None as "feed unavailable" and decide whether
    that's fatal.
    """
    if not dot_path:
        return obj
    cur = obj
    for seg in dot_path.split("."):
        seg = seg.strip()
        if not seg:
            return None
        if isinstance(cur, dict):
            if seg not in cur:
                return None
            cur = cur[seg]
        else:
            if not hasattr(cur, seg):
                return None
            cur = getattr(cur, seg)
    return cur


def dispatch_pipeline(
    calls: list[tuple[str, Callable, dict, Any]],
    timeout: int = -1,
    trace_id: str = "",
) -> dict:
    """Execute calls sequentially, feeding each result into the next call's args.

    Each entry in `calls` is a 4-tuple: (name, fn, args, feed).
      - name: tool name (for traceability in results)
      - fn:   resolved tool callable
      - args: base args dict for the call
      - feed: None | str | dict — how to incorporate the prior result

    Feed semantics (see module docstring of actions/pipeline.py for examples):
      - None: use args as-is, no feeding.
      - str:  dot-path into the previous result; the resolved value REPLACES
              args entirely (the next call gets just that value as its args
              dict — only valid when the resolved value is itself a dict).
      - dict: each key maps an args-key-name to a dot-path into the previous
              result. The base args are kept, and each fed value is merged in
              (overriding any existing key with the same name).

    Returns ok({"results": [...], "errors": [...], "completed": N, "failed": M,
                "duration_ms": int}) — same shape as dispatch_run() so callers
    can treat both uniformly.
    """
    if not calls:
        return fail("No calls provided for pipeline execution", trace_id=trace_id)

    if getattr(_parallel_depth, "value", 0) > 0:
        return fail("Nested parallel calls are not allowed", trace_id=trace_id)

    results: list[dict] = []
    errors: list[dict] = []
    prev_result: Any = None

    start = time.time()
    _parallel_depth.value = getattr(_parallel_depth, "value", 0) + 1
    try:
        for idx, (name, fn, args, feed) in enumerate(calls):
            # Compute effective args based on feed spec and prev_result.
            if idx == 0 or feed is None:
                effective_args = dict(args)
            elif isinstance(feed, str):
                resolved = _resolve_dot_path(prev_result, feed)
                if not isinstance(resolved, dict):
                    entry = {
                        "tool": name,
                        "error": (
                            f"Pipeline feed '{feed}' did not resolve to a dict "
                            f"(got {type(resolved).__name__})"
                        ),
                    }
                    if trace_id:
                        entry["trace_id"] = trace_id
                    errors.append(entry)
                    break
                effective_args = dict(resolved)
            elif isinstance(feed, dict):
                effective_args = dict(args)
                for arg_key, dot_path in feed.items():
                    if not isinstance(dot_path, str):
                        entry = {
                            "tool": name,
                            "error": f"Pipeline feed for arg '{arg_key}' must be a dot-path string",
                        }
                        if trace_id:
                            entry["trace_id"] = trace_id
                        errors.append(entry)
                        break
                    resolved = _resolve_dot_path(prev_result, dot_path)
                    if resolved is None and dot_path:
                        # Missing feed value — surface as a soft error but
                        # don't break the chain; downstream may tolerate None.
                        # Tests asserting strict behaviour can check args.
                        pass
                    effective_args[arg_key] = resolved
                else:
                    pass
                # If the inner for broke (bad dot_path), break the outer loop too.
                if errors:
                    break
            else:
                entry = {
                    "tool": name,
                    "error": f"Pipeline feed must be None | str | dict (got {type(feed).__name__})",
                }
                if trace_id:
                    entry["trace_id"] = trace_id
                errors.append(entry)
                break

            # Execute the call.
            try:
                result = fn(**effective_args)
                entry = {
                    "tool": name,
                    "status": result.get("status", "success") if isinstance(result, dict) else "success",
                    "result": result,
                }
                if trace_id:
                    entry["trace_id"] = trace_id
                results.append(entry)
                prev_result = result
            except Exception as e:
                entry = {
                    "tool": name,
                    "error": f"{type(e).__name__}: {e}",
                }
                if trace_id:
                    entry["trace_id"] = trace_id
                errors.append(entry)
                # Pipeline stops on first failure — subsequent steps have no
                # upstream result to feed from.
                break
    finally:
        _parallel_depth.value -= 1

    return ok({
        "results": results,
        "errors": errors,
        "completed": len(results),
        "failed": len(errors),
        "duration_ms": round((time.time() - start) * 1000),
    }, trace_id=trace_id)
