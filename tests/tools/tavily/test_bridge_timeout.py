"""tests/tools/tavily/test_bridge_timeout.py — Bridge timeout regression test.

v1.1: Added to verify that _run_async() actually respects the configured
timeout and returns control to the caller promptly. The pre-v1.1 bug used
'with ThreadPoolExecutor() as ex:' which called shutdown(wait=True) on exit,
blocking the caller until the coroutine finished regardless of timeout.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from tools.tavily_ops.bridge import _run_async


class TestBridgeTimeout:
    """Verify timeout behavior in bridge._run_async()."""

    def test_timeout_actually_fires(self):
        """A slow coroutine against a short timeout must raise within ~2x timeout."""
        import asyncio

        async def slow_coro():
            # Sleep much longer than the timeout window to ensure timeout fires
            await asyncio.sleep(30)
            return "should not reach here"

        start = time.time()
        # Patch to a very short timeout so the test doesn't take 60+ seconds
        with patch("tools.tavily_ops.bridge.cfg.tavily_timeout", 1):
            # future.result(timeout=cfg.tavily_timeout + 10) = 11 seconds
            # The coroutine sleeps 30s, so it MUST timeout at ~11s
            with pytest.raises(Exception):
                _run_async(slow_coro())
        elapsed = time.time() - start

        # Must raise BEFORE the coroutine finishes (i.e., < 15s, not 30s+)
        assert elapsed < 15, f"Timeout took {elapsed:.2f}s — bug still present"

    def test_fast_coroutine_succeeds(self):
        """A fast coroutine should return normally without timeout issues."""
        import asyncio

        async def fast_coro():
            await asyncio.sleep(0.1)
            return {"status": "ok"}

        result = _run_async(fast_coro())
        assert result == {"status": "ok"}
