"""Unit tests for web search action."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import httpx

from tools.web import web


@pytest.fixture
def mock_config():
    """Mock configuration for web tool with explicit integer values."""
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


class TestSearch:
    def test_search_success(self, mock_config, mock_httpx):
        """Test successful search."""
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

    def test_search_missing_query(self, mock_config):
        """Test search without query parameter."""
        result = web(action="search", query="")

        assert result["status"] == "error"
        assert "requires query" in result["error"]

    def test_search_timeout(self, mock_config, mock_httpx):
        """Test search timeout handling."""
        mock_httpx.get.side_effect = httpx.TimeoutException("Timeout")

        result = web(action="search", query="test")

        assert result["status"] == "error"
        assert "timeout" in result["error"].lower()

    def test_search_connection_error(self, mock_config, mock_httpx):
        """Test search connection error."""
        mock_httpx.get.side_effect = httpx.ConnectError("Connection failed")

        result = web(action="search", query="test")

        assert result["status"] == "error"
        assert "Cannot reach" in result["error"]
