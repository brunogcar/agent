"""Unit tests for web scrape action."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.web import web


class TestScrape:
    def test_scrape_success(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
        assert result["data"]["title"] == "Test"
        assert "Content" in result["data"]["text"]

    def test_scrape_missing_url(self, mock_cfg_for_web):
        result = web(action="scrape", url="")
        assert result["status"] == "error"
        assert "requires url" in result["error"]

    def test_scrape_no_text_content(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = "<html><head></head><body><script>alert(1)</script></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "error"
        assert "No text content extracted" in result["error"]


class TestSSRFProtection:
    def test_blocks_localhost(self, mock_cfg_for_web, mock_httpx):
        with patch("tools.web_ops.actions.scrape._is_safe_url", return_value=False):
            result = web(action="scrape", url="http://localhost:8080/admin", max_chars=8000)
        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_blocks_private_ip(self, mock_cfg_for_web, mock_httpx):
        with patch("tools.web_ops.actions.scrape._is_safe_url", return_value=False):
            result = web(action="scrape", url="http://192.168.1.1/config", max_chars=8000)
        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_allows_public_url(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = "<html><body>Public content</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response
        result = web(action="scrape", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
