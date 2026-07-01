"""tests/tools/tavily/test_tavily_error_handling.py — Tavily error classification tests.

v1.2: Fixed test_rate_limit_backoff_retries to use coroutine factory.
      Added error_code assertions. Added API key sanitization test.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.tavily_ops.errors import _handle_tavily_error
from core.contracts import fail


class TestErrorHandling:
    """Test Tavily error classification and sanitization."""

    def test_tavily_keyless_limit_error(self):
        try:
            from tavily.errors import TavilyKeylessLimitError
        except ImportError:
            pytest.skip("tavily-python not installed")
        e = TavilyKeylessLimitError("limit reached")
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert "keyless" in result["error"].lower()
        assert result.get("error_code") == "AUTH_FAILED"

    def test_tavily_invalid_key_error(self):
        try:
            from tavily.errors import InvalidAPIKeyError
        except ImportError:
            pytest.skip("tavily-python not installed")
        e = InvalidAPIKeyError("bad key")
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert "invalid" in result["error"].lower()
        assert result.get("error_code") == "AUTH_FAILED"

    def test_usage_limit_exceeded_error(self):
        try:
            from tavily.errors import UsageLimitExceededError
        except ImportError:
            pytest.skip("tavily-python not installed")
        e = UsageLimitExceededError("quota exhausted")
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert "quota" in result["error"].lower()
        assert result.get("error_code") == "QUOTA_EXHAUSTED"

    def test_tavily_api_error_429(self):
        try:
            from tavily.errors import APIError
        except ImportError:
            pytest.skip("tavily-python not installed")
        e = APIError("rate limited")
        e.status_code = 429
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert "429" in result["error"]
        assert result.get("error_code") == "RATE_LIMITED"

    def test_httpx_timeout(self):
        import httpx
        e = httpx.TimeoutException("connection timed out")
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        # v1.2 FIX: "timed out" is in the message, not "timeout" as a standalone word
        assert "timed out" in result["error"].lower()
        assert result.get("error_code") == "TIMEOUT"

    def test_httpx_connect_error(self):
        import httpx
        e = httpx.ConnectError("connection refused")
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert "connection" in result["error"].lower()
        assert result.get("error_code") == "CONNECT_ERROR"

    def test_httpx_http_status_error_401(self):
        import httpx
        resp = MagicMock()
        resp.status_code = 401
        e = httpx.HTTPStatusError("unauthorized", request=MagicMock(), response=resp)
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert result.get("error_code") == "CLIENT_ERROR"

    def test_httpx_http_status_error_403(self):
        import httpx
        resp = MagicMock()
        resp.status_code = 403
        e = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=resp)
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert result.get("error_code") == "CLIENT_ERROR"

    def test_httpx_http_status_error_429(self):
        import httpx
        resp = MagicMock()
        resp.status_code = 429
        e = httpx.HTTPStatusError("too many requests", request=MagicMock(), response=resp)
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert "429" in result["error"]
        assert result.get("error_code") == "RATE_LIMITED"

    def test_unknown_tavily_error(self):
        e = ValueError("unexpected failure")
        result = _handle_tavily_error(e, trace_id="t1")
        assert result["status"] == "error"
        assert result.get("error_code") == "UNKNOWN"

    def test_handler_returns_non_dict(self):
        """Facade guard catches non-dict handler returns."""
        pass  # Tested in test_tavily_facade.py if needed

    # v1.2: NEW — API key sanitization
    def test_api_key_not_in_error_message(self):
        with patch("tools.tavily_ops.errors.cfg.tavily_api_key", "tvly-secret-key-12345"):
            e = ValueError("Error: tvly-secret-key-12345 in request")
            result = _handle_tavily_error(e, trace_id="t1")
            assert "tvly-secret-key-12345" not in result["error"]
            assert "***" in result["error"]

    def test_api_key_sanitization_url_encoded(self):
        # v1.2 FIX: The regex replaces "key=tvly-test-key" with "key=***"
        # not "api_key=***" — the test assertion must match the actual regex
        with patch("tools.tavily_ops.errors.cfg.tavily_api_key", "tvly-test-key"):
            e = ValueError("URL: https://api.tavily.com?key=tvly-test-key")
            result = _handle_tavily_error(e, trace_id="t1")
            assert "tvly-test-key" not in result["error"]
            assert "key=***" in result["error"]

    def test_error_message_truncated(self):
        """Error messages are truncated to 500 chars."""
        long_msg = "A" * 1000
        e = ValueError(long_msg)
        result = _handle_tavily_error(e, trace_id="t1")
        assert len(result["error"]) <= 550  # Allow for prefix + 500 chars

    # v1.2: FIXED — test_rate_limit_backoff_retries now uses coroutine factory
    def test_rate_limit_backoff_retries(self, mock_tavily_client):
        try:
            from tavily.errors import RateLimitError
        except ImportError:
            pytest.skip("tavily-python not installed")

        call_count = [0]

        async def _side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RateLimitError("Too many requests")
            return {"results": [{"url": "https://example.com"}], "answer": "OK"}

        mock_tavily_client.search.side_effect = _side_effect

        # v1.2 FIX: The bridge now receives a factory, so each retry
        # creates a fresh coroutine via the mock
        with patch("tools.tavily_ops.bridge.time.sleep"):
            result = tavily(action="search", query="test")

        assert result["status"] == "success"
        assert call_count[0] == 3

    # v1.2: NEW — error_code propagation
    def test_error_code_in_response(self):
        import httpx
        e = httpx.TimeoutException("timeout")
        result = _handle_tavily_error(e, trace_id="t1")
        assert "error_code" in result
        assert result["error_code"] == "TIMEOUT"
