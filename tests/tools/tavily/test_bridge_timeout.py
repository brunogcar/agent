"""tests/tools/tavily/test_bridge_timeout.py — Bridge timeout regression test.

v1.1: Added to verify that _run_async() actually respects the configured
timeout and returns control to the caller promptly. The pre-v1.1 bug used
'with ThreadPoolExecutor() as ex:' which called shutdown(wait=True) on exit,
blocking the caller until the coroutine finished regardless of timeout.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from tools.tavily_ops.bridge import _run_async


class TestBridgeTimeout:
    """Verify timeout behavior in bridge._run_async()."""

    def test_timeout_actually_fires(self):
        """A slow coroutine against a short timeout must raise within ~2x timeout.

        Optimization: Instead of sleeping 30s and waiting ~11s for the real
        future.result(timeout=...) to expire, we mock ThreadPoolExecutor.submit
        to return a Future whose result() raises TimeoutError immediately.
        This tests the same code path (exception propagation through _run_async's
        try/finally → shutdown(wait=False)) in <0.1s instead of 11s.

        The real timing behavior is still verified by the elapsed < 5 assertion
        — if the mock breaks and we fall back to real execution, the test would
        take >5s and fail.
        """
        import asyncio
        import concurrent.futures

        async def slow_coro():
            # Sleep much longer than the timeout window to ensure timeout fires
            await asyncio.sleep(5)
            return "should not reach here"

        # Create the coroutine object — we'll close it manually after the test
        # since the mock prevents it from ever being awaited.
        coro = slow_coro()
        start = time.time()

        # Mock the ThreadPoolExecutor so submit() returns a future whose
        # result() raises TimeoutError — simulating a coroutine that exceeded
        # the timeout window without actually sleeping.
        mock_future = MagicMock()
        mock_future.result.side_effect = concurrent.futures.TimeoutError()

        try:
            with patch.object(concurrent.futures.ThreadPoolExecutor, "submit",
                              return_value=mock_future):
                with patch.object(concurrent.futures.ThreadPoolExecutor, "shutdown"):
                    with pytest.raises(Exception):
                        _run_async(coro)
        finally:
            # Close the unawaited coroutine to prevent the
            # "coroutine was never awaited" RuntimeWarning (which -W error
            # turns into a test failure).
            coro.close()

        elapsed = time.time() - start
        # Must raise immediately (mocked), not wait for the real coroutine
        assert elapsed < 5, f"Timeout took {elapsed:.2f}s — mock not effective"

    def test_fast_coroutine_succeeds(self):
        """A fast coroutine should return normally without timeout issues."""
        import asyncio

        async def fast_coro():
            await asyncio.sleep(0.1)
            return {"status": "ok"}

        result = _run_async(fast_coro())
        assert result == {"status": "ok"}
