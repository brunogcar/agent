"""Unit tests for web search action."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import httpx

from tools.web import web


class TestSearch:
    def test_search_success(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"url": "https://example.com", "title": "Example", "content": "Test snippet", "engine": "google"}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response
        result = web(action="search", query="test query")
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert result["data"]["results"][0]["url"] == "https://example.com"

    def test_search_missing_query(self, mock_cfg_for_web):
        result = web(action="search", query="")
        assert result["status"] == "error"
        assert "requires query" in result["error"]

    def test_search_timeout(self, mock_cfg_for_web, mock_httpx):
        mock_httpx.get.side_effect = httpx.TimeoutException("Timeout")
        result = web(action="search", query="test")
        assert result["status"] == "error"
        assert "timeout" in result["error"].lower()

    def test_search_connection_error(self, mock_cfg_for_web, mock_httpx):
        mock_httpx.get.side_effect = httpx.ConnectError("Connection failed")
        result = web(action="search", query="test")
        assert result["status"] == "error"
        assert "CONNECT_ERROR" in result.get("error_code", "") or "Cannot reach" in result["error"] or "ConnectError" in result["error"]  # v1.4: error shape changed

    def test_search_ssrf_blocked_searxng_url(self, mock_cfg_for_web, mock_httpx):
        mock_cfg_for_web.searxng_url = "http://192.168.1.1:8080"
        with patch("tools.web_ops.actions.search._is_safe_url", return_value=False):
            result = web(action="search", query="test")
        assert result["status"] == "error"
        assert "SSRF blocked" in result["error"]
