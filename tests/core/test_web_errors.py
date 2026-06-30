"""tests/core/test_web_errors.py — Tests for core.web_errors helpers.

v1.1: Added to verify classify_http_error and is_retryable_error behavior.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from core.web_errors import classify_http_error, is_retryable_error


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

    def test_404_is_not_retryable(self):
        resp = MagicMock()
        resp.status_code = 404
        e = httpx.HTTPStatusError("not found", request=MagicMock(), response=resp)
        assert is_retryable_error(e) is False

    def test_random_exception_is_not_retryable(self):
        assert is_retryable_error(ValueError("random")) is False
