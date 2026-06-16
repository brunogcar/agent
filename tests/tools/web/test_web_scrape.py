"""Unit tests for web scrape/read actions."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

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


class TestScrape:
    def test_scrape_success(self, mock_config, mock_httpx):
        """Test successful scrape."""
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="scrape", url="https://example.com")

        assert result["status"] == "success"
        assert result["data"]["title"] == "Test"
        assert "Content" in result["data"]["text"]

    def test_scrape_missing_url(self, mock_config):
        """Test scrape without URL parameter."""
        result = web(action="scrape", url="")

        assert result["status"] == "error"
        assert "requires url" in result["error"]

    def test_read_alias(self, mock_config, mock_httpx):
        """Test that 'read' is an alias for 'scrape'."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        result = web(action="read", url="https://example.com")

        assert result["status"] == "success"


class TestSSRFProtection:
    def test_blocks_localhost(self, mock_config, mock_httpx, monkeypatch):
        """Test that localhost URLs are blocked."""
        import tools.vision
        monkeypatch.setattr(tools.vision.cfg, "allowed_internal_hosts", frozenset())
        result = web(action="scrape", url="http://localhost:8080/admin")

        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_blocks_private_ip(self, mock_config, mock_httpx):
        """Test that private IP addresses are blocked."""
        result = web(action="scrape", url="http://192.168.1.1/config")

        assert result["status"] == "error"
        assert "private/internal" in result["error"].lower()

    def test_allows_public_url(self, mock_config, mock_httpx):
        """Test that public URLs are allowed."""
        mock_response = MagicMock()
        mock_response.text = "Public content"
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        # Patch _is_safe_url to return True for this test
        with patch("tools.web._is_safe_url", return_value=True):
            result = web(action="scrape", url="https://example.com")

        assert result["status"] == "success"
