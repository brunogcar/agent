"""Unit tests for web tool error handling."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import httpx

from tools.web import web


class TestErrorHandling:
    def test_unknown_action(self, mock_cfg_for_web):
        result = web(action="unknown_action")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_search_and_read_no_results(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response
        result = web(action="search_and_read", query="no results query", max_chars=8000)
        assert result["status"] == "error"
        assert "No search results" in result["error"]

    def test_scrape_http_error(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        mock_httpx.get.side_effect = error
        result = web(action="scrape", url="https://example.com/notfound", max_chars=8000)
        assert result["status"] == "error"
        assert "404" in result["error"]


class TestHelperFunctions:
    def test_is_safe_url_blocks_loopback(self):
        """_is_safe_url blocks loopback by delegating to is_safe_network_address."""
        from tools.web_ops import utils
        with patch("core.security.is_safe_network_address", return_value=False):
            assert utils._is_safe_url("http://127.0.0.1/admin") is False
            assert utils._is_safe_url("http://localhost/admin") is False

    def test_is_safe_url_allows_public(self):
        """_is_safe_url allows public addresses when is_safe_network_address returns True."""
        from tools.web_ops import utils
        with patch("core.security.is_safe_network_address", return_value=True):
            assert utils._is_safe_url("http://example.com") is True
            assert utils._is_safe_url("https://docs.python.org") is True

    def test_is_safe_url_blocks_private(self):
        from tools.web_ops import utils
        with patch("core.security.is_safe_network_address", return_value=False):
            assert utils._is_safe_url("http://192.168.1.1") is False
            assert utils._is_safe_url("http://10.0.0.1") is False
            assert utils._is_safe_url("http://172.16.0.1") is False

    def test_is_safe_url_invalid_hostname(self):
        from tools.web_ops import utils
        # Invalid URLs have no hostname, so _is_safe_url returns False
        # without ever calling is_safe_network_address
        assert utils._is_safe_url("not-a-url") is False
        assert utils._is_safe_url("") is False

    def test_is_safe_url_blocks_non_http_schemes(self):
        """file://, ftp://, etc. are rejected regardless of hostname."""
        from tools.web_ops import utils
        # Even with is_safe_network_address returning True, non-http schemes are blocked
        with patch("core.security.is_safe_network_address", return_value=True):
            assert utils._is_safe_url("file:///etc/passwd") is False
            assert utils._is_safe_url("ftp://example.com") is False
            assert utils._is_safe_url("javascript:alert(1)") is False
