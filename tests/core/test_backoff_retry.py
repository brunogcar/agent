"""tests/core/test_backoff_retry.py — unit tests for core/backoff_retry.py.

6 tests covering:
  - succeeds_first_try (no retry needed)
  - succeeds_after_failure (one failure, then success)
  - exhausted_raises (all attempts fail — last exception re-raised)
  - backoff_is_exponential (mock time.sleep, verify delay sequence)
  - cancellation_during_backoff (cancellation_check returns True during sleep)
  - no_cancellation_check (None — normal retry, no cancellation integration)

Phase C of the centralize-workflow-utils refactor (v1.5 of core/standalone).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_succeeds_first_try():
    """fn succeeds on the first call — no retries, no backoff."""
    from core.backoff_retry import retry_with_backoff
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    with patch("core.backoff_retry.time.sleep") as mock_sleep:
        result = retry_with_backoff(fn, retries=2, base_delay=2.0)
    assert result == "ok"
    assert len(calls) == 1  # only one call
    assert mock_sleep.call_count == 0  # no backoff slept


def test_succeeds_after_failure():
    """fn raises once, then succeeds on the second attempt."""
    from core.backoff_retry import retry_with_backoff
    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient")
        return "ok"

    with patch("core.backoff_retry.time.sleep") as mock_sleep:
        result = retry_with_backoff(fn, retries=2, base_delay=2.0)
    assert result == "ok"
    assert len(calls) == 2  # one failure + one success
    assert mock_sleep.call_count == 1  # backoff before the retry


def test_exhausted_raises():
    """All attempts fail — the LAST exception is re-raised."""
    from core.backoff_retry import retry_with_backoff
    calls = []

    def fn():
        calls.append(1)
        raise RuntimeError(f"attempt {len(calls)} failed")

    with patch("core.backoff_retry.time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError, match="attempt 3 failed"):
            retry_with_backoff(fn, retries=2, base_delay=2.0)
    # 1 initial + 2 retries = 3 total attempts.
    assert len(calls) == 3
    # 2 backoffs (between the 3 attempts).
    assert mock_sleep.call_count == 2


def test_backoff_is_exponential():
    """Verify backoff delays follow base_delay * 2^attempt (2s, 4s, 8s, ...).

    Mock time.sleep so we capture the delays without actually sleeping. Use
    a fn that always fails so we hit all retry backoffs.
    """
    from core.backoff_retry import retry_with_backoff

    def fn():
        raise RuntimeError("always fails")

    # No cancellation_check — uses time.sleep directly.
    with patch("core.backoff_retry.time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError):
            retry_with_backoff(fn, retries=3, base_delay=2.0)

    # With retries=3, we get 3 backoff sleeps: 2s, 4s, 8s (base * 2^attempt).
    delays = [call.args[0] if call.args else call[0][0] for call in mock_sleep.call_args_list]
    assert delays == [2.0, 4.0, 8.0], f"expected exponential backoff [2.0, 4.0, 8.0], got {delays}"


def test_cancellation_during_backoff():
    """cancellation_check returns True during backoff — immediate RuntimeError.

    fn fails on first attempt → backoff begins → cancellation_check returns
    True → retry_with_backoff raises RuntimeError("cancelled during backoff")
    immediately (doesn't finish the backoff sleep, doesn't retry).
    """
    from core.backoff_retry import retry_with_backoff

    call_count = [0]

    def fn():
        call_count[0] += 1
        raise RuntimeError("transient")

    # cancellation_check returns True on the SECOND call (during backoff).
    # First call (before attempt 1) returns False so the attempt happens.
    check_calls = [0]

    def cancellation_check():
        check_calls[0] += 1
        # Return False for the first few checks (before the attempt + start
        # of backoff), then True (cancellation signaled during backoff).
        return check_calls[0] > 2

    # Patch time.sleep so the polling slices don't actually sleep (otherwise
    # the test would wait 0.1s per slice). The polling loop still runs —
    # cancellation_check is called every slice.
    with patch("core.backoff_retry.time.sleep"):
        with pytest.raises(RuntimeError, match="cancelled during backoff"):
            retry_with_backoff(
                fn, retries=2, base_delay=2.0,
                cancellation_check=cancellation_check,
            )
    # Only one fn call (the first attempt) — cancellation fired during the
    # backoff AFTER attempt 1, before attempt 2.
    assert call_count[0] == 1
    # cancellation_check was called more than once (before attempt 1 + during
    # backoff polling).
    assert check_calls[0] > 1


def test_no_cancellation_check():
    """cancellation_check=None — normal retry, uses time.sleep (no Event.wait)."""
    from core.backoff_retry import retry_with_backoff

    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient")
        return "ok"

    # cancellation_check=None — should use time.sleep, NOT threading.Event.
    with patch("core.backoff_retry.time.sleep") as mock_sleep:
        result = retry_with_backoff(fn, retries=2, base_delay=1.0, cancellation_check=None)
    assert result == "ok"
    assert len(calls) == 2
    # time.sleep called once (between attempt 1 failure + attempt 2 success).
    assert mock_sleep.call_count == 1
    # Delay = base_delay * 2^0 = 1.0 (first backoff).
    delay = mock_sleep.call_args[0][0]
    assert delay == 1.0


# ===========================================================================
# [v1.6 / autoresearch v1.11 A4] non_retryable exception types
# ===========================================================================


def test_non_retryable_propagates_immediately():
    """[v1.6 A4] When fn raises an exception in the non_retryable tuple,
    it propagates IMMEDIATELY — no sleep, no retry, no tracer.error log.

    This is the core A4 fix: pre-v1.6, retry_with_backoff caught bare
    `except Exception` and retried EVERYTHING. autoresearch's _call_planner
    wrapped non-transient exceptions (ImportError, AttributeError) in
    _PropagateError(Exception) — but _PropagateError IS an Exception, so
    retry_with_backoff caught + retried it 3× (6s wasted backoff + up to 2
    extra LLM API hits) before the caller could unwrap it.
    """
    from core.backoff_retry import retry_with_backoff

    class _PropagateError(Exception):
        pass

    calls = []

    def fn():
        calls.append(1)
        raise _PropagateError("real bug — don't retry")

    # Mock time.sleep so we can assert it was NEVER called (no backoff).
    with patch("core.backoff_retry.time.sleep") as mock_sleep, \
         patch("core.backoff_retry.tracer.error") as mock_error:
        with pytest.raises(_PropagateError, match="real bug"):
            retry_with_backoff(
                fn, retries=2, base_delay=2.0,
                non_retryable=(_PropagateError,),
            )

    # Only ONE call — no retry.
    assert len(calls) == 1
    # NO sleep — propagated immediately.
    assert mock_sleep.call_count == 0
    # NO tracer.error log — non_retryable doesn't reach the final-attempt log.
    assert mock_error.call_count == 0


def test_non_retryable_none_retries_everything():
    """[v1.6 A4] non_retryable=None (default) = retry every Exception
    (backward-compatible v1.5 behavior)."""
    from core.backoff_retry import retry_with_backoff

    calls = []

    class CustomError(Exception):
        pass

    def fn():
        calls.append(1)
        raise CustomError("would be non-retryable if registered")

    with patch("core.backoff_retry.time.sleep") as mock_sleep:
        with pytest.raises(CustomError):
            retry_with_backoff(
                fn, retries=2, base_delay=2.0,
                non_retryable=None,  # default — retry everything
            )

    # 3 total attempts (1 initial + 2 retries).
    assert len(calls) == 3
    # 2 backoff sleeps (between the 3 attempts).
    assert mock_sleep.call_count == 2
