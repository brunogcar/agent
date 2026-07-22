"""core/backoff_retry.py — Retry with exponential backoff for transient failures.

Single function: `retry_with_backoff(fn, retries=2, base_delay=2.0,
cancellation_check=None, tid="") -> Any`.

Pattern: call `fn()` with no args. If it raises, retry up to `retries`
times. Backoff is `base_delay * 2^attempt` (exponential). Sleep is
interruptible: `threading.Event().wait(delay)` if `cancellation_check` is
provided (the callable is polled DURING the wait, allowing immediate exit on
cancellation); `time.sleep(delay)` otherwise.

If `cancellation_check()` returns True DURING backoff, raise
`RuntimeError("cancelled during backoff")` immediately (don't finish sleeping,
don't retry).

WHY THIS EXISTS
---------------
Extracted from two duplicated retry loops (Phase C of the centralize-workflow-
utils refactor — v1.5 of `core/standalone`):

1. `workflows/autocode_impl/helpers.py::_call` — manual retry with
   `threading.Event().wait()` interruptible backoff + the autocode
   module-global `_cancellation_requested` flag.
2. `workflows/autoresearch_impl/nodes/propose.py::_call_planner` — manual
   retry with `time.sleep()` (non-interruptible) + no cancellation flag
   (autoresearch has no in-loop cancellation pre-Phase B).

Both loops had the same structure (call + catch + sleep + retry) but
differed in cancellation integration + return type. This helper shares the
retry logic WITHOUT trying to unify the return types — `retry_with_backoff`
returns whatever `fn` returns, so each caller wraps its own LLM-call shape
in a lambda/closure.

IMPORTANT — return types are NOT unified:
  - autocode `_call` returns `str` (the LLM response text)
  - autoresearch `_call_planner` returns `tuple[str, dict]` (response + usage)
  - `retry_with_backoff` returns whatever `fn` returns — works for both.

The `cancellation_check` callable is called BEFORE each attempt AND polled
during backoff sleep. Caller-supplied — each caller passes its own
cancellation primitive (autocode passes its module-global
`is_cancellation_requested`; autoresearch passes a lambda wrapping
`workflows.base.is_workflow_cancelled(tid)`).
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from core.tracer import tracer


def retry_with_backoff(
    fn: Callable[[], Any],
    retries: int = 2,
    base_delay: float = 2.0,
    cancellation_check: Optional[Callable[[], bool]] = None,
    tid: str = "",
    non_retryable: Optional[tuple] = None,
) -> Any:
    """Call `fn()` with retry + exponential backoff.

    Args:
        fn: Zero-arg callable. Called up to `retries + 1` times. Should
            raise on failure (the exception triggers a retry).
        retries: Max number of RETRIES (so total attempts = `retries + 1`).
            Default 2 (3 total attempts).
        base_delay: Base backoff delay in seconds. Actual delay between
            attempts is `base_delay * 2^attempt` (exponential). Default 2.0
            (delays: 2s, 4s, 8s, ...).
        cancellation_check: Optional zero-arg callable returning bool. If
            provided, called BEFORE each attempt AND polled during backoff
            sleep (in 0.1s slices via `time.sleep`). If it returns True at
            any point, raises `RuntimeError("cancelled during backoff")`
            immediately. When None, backoff uses a single non-interruptible
            `time.sleep(delay)` call.
        tid: Trace ID for observability. Passed to `tracer.error` on the
            final-attempt failure.
        non_retryable: Optional tuple of exception types that should
            propagate IMMEDIATELY without any retry or backoff sleep.
            When `fn()` raises an exception matching `isinstance(e,
            non_retryable)`, the exception is re-raised on the spot (no sleep,
            no retry, no `tracer.error` log). Default None = retry every
            `Exception` (backward-compatible v1.5 behavior). [v1.6] Added so
            callers can distinguish transient failures (network blips, rate
            limits — worth retrying) from real bugs (ImportError,
            AttributeError — never worth retrying; each retry is a wasted LLM
            API hit + backoff sleep).

    Returns:
        Whatever `fn()` returns on the first successful attempt.

    Raises:
        RuntimeError("cancelled during backoff") — if `cancellation_check()`
            returns True during backoff (between attempts).
        RuntimeError("LLM call cancelled — graph timeout exceeded") — if
            `cancellation_check()` returns True BEFORE an attempt.
        Any exception in `non_retryable` — re-raised immediately on the
            first occurrence (no retry, no backoff sleep). [v1.6]
        Whatever exception `fn` raised on the final attempt — re-raised after
            the last retry fails. Logged via `tracer.error` first.
    """
    last_error: Optional[BaseException] = None
    for attempt in range(retries + 1):
        # Check cancellation BEFORE each attempt — if the graph timed out
        # during a previous retry's backoff sleep, bail immediately.
        if cancellation_check is not None and cancellation_check():
            raise RuntimeError("LLM call cancelled — graph timeout exceeded")

        try:
            return fn()
        except Exception as e:
            last_error = e
            # [v1.6] non_retryable exception types propagate immediately —
            # no sleep, no retry, no tracer.error log. These are real bugs
            # (ImportError, AttributeError, caller-wrapped _PropagateError,
            # etc.) where retrying just wastes LLM API budget + backoff time.
            if non_retryable and isinstance(e, non_retryable):
                raise
            if attempt < retries:
                # Exponential backoff: base_delay * 2^attempt.
                delay = base_delay * (2 ** attempt)
                if cancellation_check is not None:
                    # Interruptible sleep — poll cancellation_check in 0.1s
                    # slices. Bounded cancellation latency (0.1s) without the
                    # overhead of threading.Event coordination (the caller
                    # supplies a callable, not an Event — we can't hook into
                    # the Event.set() pattern without imposing that contract).
                    slice_duration = 0.1
                    elapsed = 0.0
                    while elapsed < delay:
                        if cancellation_check():
                            raise RuntimeError("cancelled during backoff")
                        sleep_slice = min(slice_duration, delay - elapsed)
                        time.sleep(sleep_slice)
                        elapsed += sleep_slice
                else:
                    # No cancellation_check — non-interruptible sleep (caller
                    # doesn't care about cancellation during backoff).
                    time.sleep(delay)
                continue
            # Final attempt failed — log + re-raise.
            tracer.error(
                tid, "backoff_retry",
                f"Failed after {retries + 1} attempts: {e}",
            )
            raise

    # Unreachable — the loop either returns on success or raises on the last
    # attempt. Defensive: re-raise the last error if we somehow exit the loop.
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_with_backoff exited loop without success or final raise")


__all__ = ["retry_with_backoff"]
