"""Unit tests for web tool error handling."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import httpx

from tools.web import web


@pytest.fixture
def mock_config():
    """Mock configuration for web tool."""
    with patch("tools.web.cfg") as mock_cfg:
        mock_cfg.web_max_text_chars = 8000
        mock_cfg.web_snippet_chars = 300
        mock_cfg.web_max_search_results = 10
        mock_cfg.searxng_url = "http://localhost:8080"
        yield mock_cfg


@pytest.fixture
def mock_httpx():
    """Mock httpx.Client for network isolation."""
    with patch("tools.web._make_client") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value.__enter__.return_value = client_instance
        yield client_instance


class TestErrorHandling:
    def test_unknown_action(self, mock_config):
        """Test unknown action returns error."""
        result = web(action="unknown_action")

        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_search_and_read_no_results(self, mock_config, mock_httpx):
        """Test search_and_read with no search results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="search_and_read", query="no results query")

        assert result["status"] == "error"
        assert "No search results" in result["error"]

    def test_scrape_http_error(self, mock_config, mock_httpx):
        """Test scrape with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        mock_httpx.get.side_effect = error

        with patch("tools.web._is_safe_url", return_value=True):
            result = web(action="scrape", url="https://example.com/notfound")

        assert result["status"] == "error"
        assert "404" in result["error"]


class TestHelperFunctions:
    def test_is_safe_url_blocks_loopback(self, monkeypatch):
        """Test _is_safe_url blocks loopback addresses."""
        import tools.vision
        monkeypatch.setattr(tools.vision.cfg, "allowed_internal_hosts", frozenset())
        from tools.web import _is_safe_url
        assert _is_safe_url("http://127.0.0.1/admin") is False
        assert _is_safe_url("http://localhost/admin") is False

    def test_is_safe_url_blocks_private(self):
        """Test _is_safe_url blocks private networks."""
        from tools.web import _is_safe_url
        assert _is_safe_url("http://192.168.1.1") is False
        assert _is_safe_url("http://10.0.0.1") is False
        assert _is_safe_url("http://172.16.0.1") is False

    def test_is_safe_url_invalid_hostname(self):
        """Test _is_safe_url handles invalid hostnames."""
        from tools.web import _is_safe_url
        assert _is_safe_url("not-a-url") is False
        assert _is_safe_url("") is False
