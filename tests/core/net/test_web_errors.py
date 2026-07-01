"""tests/core/net/test_web_errors.py — Tests for core.net.errors helpers.

v1.2: Added BOT_BLOCKED, get_retry_delay, SDK exception registry tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.net.errors import (
    classify_http_error,
    is_retryable_error,
    get_retry_delay,
    register_retryable_exception,
    RETRYABLE_STATUS_CODES,
    RETRYABLE_EXCEPTIONS,
)


class TestClassifyHttpError:
    """Test HTTP error classification."""

    def test_timeout(self):
        e = httpx.TimeoutException("timeout")
        assert classify_http_error(e) == "TIMEOUT"

    def test_connect_error(self):
        e = httpx.ConnectError("refused")
        assert classify_http_error(e) == "CONNECT_ERROR"

    def test_network_error(self):
        e = httpx.NetworkError("network down")
        assert classify_http_error(e) == "NETWORK_ERROR"

    def test_rate_limited(self):
        resp = MagicMock()
        resp.status_code = 429
        e = httpx.HTTPStatusError("too many", request=MagicMock(), response=resp)
        assert classify_http_error(e) == "RATE_LIMITED"

    def test_server_error(self):
        resp = MagicMock()
        resp.status_code = 503
        e = httpx.HTTPStatusError("unavailable", request=MagicMock(), response=resp)
        assert classify_http_error(e) == "SERVER_ERROR"

    def test_client_error(self):
        resp = MagicMock()
        resp.status_code = 404
        e = httpx.HTTPStatusError("not found", request=MagicMock(), response=resp)
        assert classify_http_error(e) == "CLIENT_ERROR"

    def test_unknown(self):
        e = ValueError("random")
        assert classify_http_error(e) == "UNKNOWN"

    # v1.2: NEW — BOT_BLOCKED detection
    def test_bot_blocked_cloudflare(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "<html>cloudflare challenge</html>"
        e = httpx.HTTPStatusError("blocked", request=MagicMock(), response=resp)
        assert classify_http_error(e) == "BOT_BLOCKED"

    def test_bot_blocked_cf_ray(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "error code: 1020 cf-ray: abc123"
        e = httpx.HTTPStatusError("blocked", request=MagicMock(), response=resp)
        assert classify_http_error(e) == "BOT_BLOCKED"

    # v1.2: NEW — 408 Request Timeout
    def test_408_timeout(self):
        resp = MagicMock()
        resp.status_code = 408
        e = httpx.HTTPStatusError("request timeout", request=MagicMock(), response=resp)
        assert classify_http_error(e) == "RATE_LIMITED"  # 408 is in RETRYABLE_STATUS_CODES

    # v1.2: NEW — SDK exception with status_code attribute
    def test_sdk_exception_with_status_code(self):
        """Tavily APIError has status_code but is not httpx.HTTPStatusError."""
        class FakeAPIError(Exception):
            def __init__(self, msg, status_code):
                super().__init__(msg)
                self.status_code = status_code

        e = FakeAPIError("rate limited", 429)
        assert classify_http_error(e) == "RATE_LIMITED"

    # v1.2: NEW — ReadError / WriteError / RemoteProtocolError
    def test_read_error(self):
        e = httpx.ReadError("connection reset")
        assert classify_http_error(e) == "NETWORK_ERROR"

    def test_write_error(self):
        e = httpx.WriteError("broken pipe")
        assert classify_http_error(e) == "NETWORK_ERROR"


class TestIsRetryableError:
    """Test retryable error detection."""

    def test_timeout_is_retryable(self):
        assert is_retryable_error(httpx.TimeoutException("timeout")) is True

    def test_connect_error_is_retryable(self):
        assert is_retryable_error(httpx.ConnectError("refused")) is True

    def test_429_is_retryable(self):
        resp = MagicMock()
        resp.status_code = 429
        e = httpx.HTTPStatusError("too many", request=MagicMock(), response=resp)
        assert is_retryable_error(e) is True

    def test_500_is_retryable(self):
        resp = MagicMock()
        resp.status_code = 500
        e = httpx.HTTPStatusError("server error", request=MagicMock(), response=resp)
        assert is_retryable_error(e) is True

    def test_408_is_retryable(self):
        resp = MagicMock()
        resp.status_code = 408
        e = httpx.HTTPStatusError("request timeout", request=MagicMock(), response=resp)
        assert is_retryable_error(e) is True

    def test_404_is_not_retryable(self):
        resp = MagicMock()
        resp.status_code = 404
        e = httpx.HTTPStatusError("not found", request=MagicMock(), response=resp)
        assert is_retryable_error(e) is False

    def test_random_exception_is_not_retryable(self):
        assert is_retryable_error(ValueError("random")) is False

    # v1.2: NEW — SDK exception registry
    def test_registered_sdk_exception_is_retryable(self):
        class FakeRateLimitError(Exception):
            pass

        register_retryable_exception(FakeRateLimitError)
        assert is_retryable_error(FakeRateLimitError("too many")) is True

    def test_read_error_is_retryable(self):
        assert is_retryable_error(httpx.ReadError("reset")) is True

    def test_write_error_is_retryable(self):
        assert is_retryable_error(httpx.WriteError("broken")) is True


class TestGetRetryDelay:
    """Test unified retry delay calculation."""

    def test_base_delay(self):
        delay = get_retry_delay(0, base_delay=2.0, max_delay=30.0, jitter=False)
        assert delay == 2.0

    def test_exponential_growth(self):
        assert get_retry_delay(0, base_delay=2.0, jitter=False) == 2.0
        assert get_retry_delay(1, base_delay=2.0, jitter=False) == 4.0
        assert get_retry_delay(2, base_delay=2.0, jitter=False) == 8.0
        assert get_retry_delay(3, base_delay=2.0, jitter=False) == 16.0

    def test_max_delay_cap(self):
        delay = get_retry_delay(10, base_delay=2.0, max_delay=30.0, jitter=False)
        assert delay == 30.0

    def test_jitter_adds_variance(self):
        with patch("core.net.errors.random.random", return_value=0.5):
            delay = get_retry_delay(0, base_delay=2.0, jitter=True)
            assert delay == 2.0 * 1.125  # 2.0 * (1 + 0.5 * 0.25)

    def test_jitter_range(self):
        """Jitter adds 0-25% to the base delay."""
        for _ in range(20):
            delay = get_retry_delay(0, base_delay=2.0, jitter=True)
            assert 2.0 <= delay <= 2.5
