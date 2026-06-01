"""
core/runtime/task_runner.py — Background task execution and timeout monitoring.

EXTRACTION NOTE (Gateway Phase 1): Extracted from core/gateway.py.
Process governance (thread pools, timeouts) belongs in the runtime domain.
To prevent circular imports (runtime -> gateway_backend), this module does NOT
import the dispatcher or store. Instead, it accepts the execution callable.
"""
from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable

_TASK_EXECUTOR = None

def init_executor() -> ThreadPoolExecutor:
    """Initialize the global ThreadPoolExecutor. Called during app startup."""
    global _TASK_EXECUTOR
    if _TASK_EXECUTOR is None:
        _TASK_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="gw-task")
    return _TASK_EXECUTOR

def shutdown_executor() -> None:
    """Gracefully shutdown the executor. Called during app shutdown."""
    global _TASK_EXECUTOR
    if _TASK_EXECUTOR is not None:
        # wait=True ensures pending tasks finish or are cancelled cleanly
        # cancel_futures=True prevents new tasks from starting during shutdown
        _TASK_EXECUTOR.shutdown(wait=True, cancel_futures=True)
        _TASK_EXECUTOR = None

def get_executor() -> ThreadPoolExecutor:
    """
    Return the global ThreadPoolExecutor.
    Initializes lazily if lifespan hasn't run (e.g., in isolated unit tests).
    """
    global _TASK_EXECUTOR
    if _TASK_EXECUTOR is None:
        return init_executor()
    return _TASK_EXECUTOR

def run_background_task(
    trace_id: str,
    execute_fn: Callable[[], None],
    timeout: float = 300,
    on_timeout_fn: Callable[[str], None] | None = None
) -> None:
    """
    Submit a task to the executor and monitor its timeout in a background thread.
    
    execute_fn: The function that actually runs the task (e.g., dispatch + update store).
    on_timeout_fn: Optional callback if the task exceeds the timeout.
    """
    executor = get_executor()
    future = executor.submit(execute_fn)

    def _monitor_timeout():
        try:
            future.result(timeout=timeout)
        except FuturesTimeoutError:
            print(f"[gateway] ERROR: Task '{trace_id}' exceeded {timeout}s limit", file=sys.stderr)
            if on_timeout_fn:
                on_timeout_fn(trace_id)
            future.cancel()  # Best effort cancellation

    # Monitor runs in background so the HTTP endpoint returns immediately
    threading.Thread(target=_monitor_timeout, daemon=True).start()