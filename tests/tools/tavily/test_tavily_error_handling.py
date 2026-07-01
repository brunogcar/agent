"""Tests for tools/tavily_ops/errors.py — error classification and sanitization.

v1.3: Implemented test_handler_returns_non_dict.
      Added CircuitBreakerOpen test.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from tools.tavily_ops.errors import _handle_tavily_error
from tools.tavily_ops.bridge import CircuitBreakerOpen


class TestTavilyErrorHandling:
    """Tests for _handle_tavily_error()."""

    def test_api_key_not_in_error_message(self):
        """API key is sanitized from error messages."""
        with patch("tools.tavily_ops.errors.cfg.tavily_api_key", "tvly-secret-key-123"):
            e = Exception("Request failed with api_key=tvly-secret-key-123")
            result = _handle_tavily_error(e, trace_id="test")
        assert result["status"] == "error"
        assert "tvly-secret-key-123" not in result["error"]
        assert "***" in result["error"]

    def test_api_key_sanitization_url_encoded(self):
        with patch("tools.tavily_ops.errors.cfg.tavily_api_key", "tvly-abc"):
            e = Exception("url?api_key=tvly-abc")
            result = _handle_tavily_error(e, trace_id="test")
        assert "tvly-abc" not in result["error"]

    def test_error_message_truncated(self):
        long_msg = "x" * 1000
        e = Exception(long_msg)
        result = _handle_tavily_error(e, trace_id="test")
        assert len(result["error"]) <= 520  # 500 + "Tavily error: " prefix

    def test_rate_limit_error(self):
        e = httpx.HTTPStatusError(
            "Rate limited",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )
        result = _handle_tavily_error(e, trace_id="test")
        assert result["error_code"] == "RATE_LIMITED"

    def test_server_error(self):
        e = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        result = _handle_tavily_error(e, trace_id="test")
        assert result["error_code"] == "SERVER_ERROR"

    def test_timeout_error(self):
        e = httpx.TimeoutException("Connection timed out")
        result = _handle_tavily_error(e, trace_id="test")
        assert result["error_code"] == "TIMEOUT"

    def test_connect_error(self):
        e = httpx.ConnectError("Connection refused")
        result = _handle_tavily_error(e, trace_id="test")
        assert result["error_code"] == "CONNECT_ERROR"

    def test_circuit_breaker_open(self):
        """v1.3: CircuitBreakerOpen returns CB_OPEN error_code."""
        e = CircuitBreakerOpen("CB is open")
        result = _handle_tavily_error(e, trace_id="test")
        assert result["status"] == "error"
        assert result["error_code"] == "CB_OPEN"
        assert "CB is open" in result["error"]

    def test_handler_returns_non_dict(self):
        """Facade guard catches non-dict handler returns.

        v1.3: Actually tests the guard by mocking handler to return string.
        """
        from tools.tavily_ops._registry import DISPATCH
        original = DISPATCH["tavily"]["search"]["func"]
        try:
            DISPATCH["tavily"]["search"]["func"] = lambda **kw: "not a dict"
            from tools.tavily import tavily
            result = tavily(action="search", query="test")
            assert result["status"] == "error"
            assert "returned" in result["error"].lower() or "dict" in result["error"].lower()
        finally:
            DISPATCH["tavily"]["search"]["func"] = original
