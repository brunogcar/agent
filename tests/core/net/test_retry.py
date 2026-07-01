"""tests/core/test_retry.py — Unified retry/backoff policy tests.

v1.2: Added for core.net.retry module.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.net.retry import retry_sync


class TestRetrySync:
    """Test synchronous retry decorator."""

    def test_success_no_retry(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            return "success"

        result = retry_sync(fn, max_retries=3)
        assert result == "success"
        assert call_count[0] == 1

    def test_retry_on_retryable_error(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("transient")
            return "success"

        with patch("core.net.retry.time.sleep"):
            result = retry_sync(fn, max_retries=3)

        assert result == "success"
        assert call_count[0] == 3

    def test_exhaust_retries_raises(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise ConnectionError("always fails")

        with patch("core.net.retry.time.sleep"):
            with pytest.raises(ConnectionError):
                retry_sync(fn, max_retries=2)

        assert call_count[0] == 3  # Initial + 2 retries

    def test_no_retry_on_non_retryable(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            retry_sync(fn, max_retries=3)

        assert call_count[0] == 1  # No retry

    def test_custom_is_retryable(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("retry me")
            return "ok"

        def custom_retryable(e):
            return isinstance(e, RuntimeError)

        with patch("core.net.retry.time.sleep"):
            result = retry_sync(fn, max_retries=3, is_retryable=custom_retryable)

        assert result == "ok"
        assert call_count[0] == 2

    def test_backoff_delays(self):
        call_count = [0]
        delays = []

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("fail")
            return "ok"

        with patch("core.net.retry.time.sleep") as mock_sleep:
            retry_sync(fn, max_retries=3, base_delay=1.0, jitter=False)
            delays = [call.args[0] for call in mock_sleep.call_args_list]

        assert delays[0] == 1.0  # 1.0 * 2^0
        assert delays[1] == 2.0  # 1.0 * 2^1
