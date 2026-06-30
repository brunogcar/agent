"""Unit tests for web read action (scrape + prune alias)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.web import web


class TestRead:
    def test_read_alias_success(self, mock_cfg_for_web, mock_httpx):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_httpx.get.return_value = mock_response
        with patch("core.memory_backend.pruner.prune_tool_dict") as mock_prune:
            mock_prune.return_value = {"status": "success", "data": {"pruned": True}}
            result = web(action="read", url="https://example.com", max_chars=8000)
        assert result["status"] == "success"
        mock_prune.assert_called_once()

    def test_read_missing_url(self, mock_cfg_for_web):
        result = web(action="read", url="")
        assert result["status"] == "error"
        assert "requires url" in result["error"]
